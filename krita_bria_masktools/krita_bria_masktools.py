import os
import sys
import ssl
import json
import time
import tempfile
import urllib.request
import urllib.error
import threading
import multiprocessing
import subprocess
import uuid
import zipfile
import shutil
import base64
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import krita
from krita import Krita, DockWidgetFactory, DockWidgetFactoryBase, InfoObject
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLineEdit, QLabel, QDockWidget,
                             QApplication, QCheckBox, QSpinBox, QTextEdit, QProgressDialog,
                             QHBoxLayout, QMessageBox, QGroupBox, QRadioButton, QButtonGroup,
                             QDialog, QFormLayout, QDialogButtonBox)
from PyQt5.QtGui import QImage, QClipboard, qRgb
from PyQt5.QtCore import QRect, Qt

class BriaAISettingsDialog(QDialog):
    """Settings dialog for BriaAI API configuration"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure BriaAI Plugin")
        self.setModal(True)

        layout = QFormLayout()

        # API Key input
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        layout.addRow("API Key:", self.api_key_input)

        # Info label
        info_label = QLabel("Get your API key from <a href='https://www.bria.ai'>www.bria.ai</a>")
        info_label.setOpenExternalLinks(True)
        layout.addRow(info_label)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def set_api_key(self, key):
        self.api_key_input.setText(key)

    def get_api_key(self):
        return self.api_key_input.text()

class BackgroundRemover(QDockWidget):
    def __init__(self):
        try:
            super().__init__()
            self.setWindowTitle("Bria Mask Tools")

            widget = QWidget()
            layout = QVBoxLayout()
            widget.setLayout(layout)

            # Mode selection radio buttons
            mode_group = QGroupBox("Mode")
            mode_layout = QVBoxLayout()
            mode_group.setLayout(mode_layout)

            self.mode_button_group = QButtonGroup()

            self.remove_bg_radio = QRadioButton("Remove Background")
            self.remove_bg_radio.setChecked(True)
            self.mode_button_group.addButton(self.remove_bg_radio, 0)
            mode_layout.addWidget(self.remove_bg_radio)

            self.remove_bg_mask_radio = QRadioButton("Remove Background with Mask (Inpainting)")
            self.mode_button_group.addButton(self.remove_bg_mask_radio, 1)
            mode_layout.addWidget(self.remove_bg_mask_radio)

            self.generate_mask_radio = QRadioButton("Generate Mask")
            self.mode_button_group.addButton(self.generate_mask_radio, 2)
            mode_layout.addWidget(self.generate_mask_radio)

            layout.addWidget(mode_group)

            # Connect mode changes to update batch checkbox state
            self.mode_button_group.buttonClicked.connect(self.on_mode_changed)

            # API Key input (temporary until settings dialog is fixed)
            api_key_group = QGroupBox("API Key")
            api_key_layout = QVBoxLayout()
            api_key_group.setLayout(api_key_layout)

            self.api_key_input = QLineEdit()
            self.api_key_input.setPlaceholderText("Enter your BriaAI API key")
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.api_key_input.textChanged.connect(lambda text: self.save_api_key(text))
            api_key_layout.addWidget(self.api_key_input)

            # API key status label
            self.api_key_status = QLabel("")
            self.api_key_status.setWordWrap(True)
            api_key_layout.addWidget(self.api_key_status)

            layout.addWidget(api_key_group)

            # Store API key internally (loaded from settings)
            self.api_key = ""

            batch_layout = QHBoxLayout()
            self.batch_checkbox = QCheckBox("Batch (selected layers)")
            self.batch_checkbox.stateChanged.connect(self.toggle_batch_mode)
            batch_layout.addWidget(self.batch_checkbox)

            # Advanced options
            self.advanced_checkbox = QCheckBox("Advanced")
            self.advanced_checkbox.stateChanged.connect(self.toggle_advanced_options)
            batch_layout.addWidget(self.advanced_checkbox)

            layout.addLayout(batch_layout)

            self.advanced_group = QGroupBox("Advanced Options")
            advanced_layout = QVBoxLayout()
            self.advanced_group.setLayout(advanced_layout)
            self.advanced_group.setVisible(False)

            thread_layout = QHBoxLayout()
            self.auto_thread_checkbox = QCheckBox("Threads (AUTO)")
            self.auto_thread_checkbox.setChecked(True)  # Default is auto
            self.auto_thread_checkbox.stateChanged.connect(self.toggle_thread_count)
            thread_layout.addWidget(self.auto_thread_checkbox)

            self.thread_count_spinbox = QSpinBox()
            self.thread_count_spinbox.setMinimum(1)
            self.thread_count_spinbox.setValue(os.cpu_count() or multiprocessing.cpu_count())
            self.thread_count_spinbox.setVisible(False)
            thread_layout.addWidget(self.thread_count_spinbox)

            advanced_layout.addLayout(thread_layout)

            self.debug_checkbox = QCheckBox("Debug Mode")
            self.debug_checkbox.stateChanged.connect(self.toggle_debug_mode)
            advanced_layout.addWidget(self.debug_checkbox)

            self.masks_as_layers_checkbox = QCheckBox("Create masks as separate layers")
            self.masks_as_layers_checkbox.setToolTip(
                "If checked, masks will be created as separate paint layers instead of transparency masks")
            advanced_layout.addWidget(self.masks_as_layers_checkbox)

            # Prompt field for eraser/inpainting
            prompt_layout = QHBoxLayout()
            prompt_label = QLabel("Prompt (optional):")
            prompt_label.setToolTip("For Remove Background with Mask: guide the inpainting result")
            prompt_layout.addWidget(prompt_label)

            self.prompt_input = QLineEdit()
            self.prompt_input.setPlaceholderText("e.g., 'blue sky' or 'wooden floor'")
            prompt_layout.addWidget(self.prompt_input)

            advanced_layout.addLayout(prompt_layout)

            # Additional options for eraser
            self.preserve_alpha_checkbox = QCheckBox("Preserve Alpha Channel")
            self.preserve_alpha_checkbox.setChecked(True)
            self.preserve_alpha_checkbox.setToolTip("Maintain transparency in the original image")
            advanced_layout.addWidget(self.preserve_alpha_checkbox)

            layout.addWidget(self.advanced_group)

            button_layout = QHBoxLayout()

            # Temporarily disabled to debug
            # self.settings_button = QPushButton("Settings")
            # self.settings_button.clicked.connect(self.show_settings)
            # button_layout.addWidget(self.settings_button)

            self.action_button = QPushButton("Remove")
            self.action_button.clicked.connect(self.remove_background)
            button_layout.addWidget(self.action_button)

            self.open_temp_dir_button = QPushButton("Open Dir")
            self.open_temp_dir_button.clicked.connect(self.open_temp_directory)
            self.open_temp_dir_button.setVisible(False)
            button_layout.addWidget(self.open_temp_dir_button)

            self.copy_text_button = QPushButton("Copy Text")
            self.copy_text_button.clicked.connect(self.copy_status_text)
            self.copy_text_button.setVisible(False)
            button_layout.addWidget(self.copy_text_button)

            layout.addLayout(button_layout)

            self.status_label = QTextEdit()
            self.status_label.setReadOnly(True)
            self.status_label.setLineWrapMode(QTextEdit.WidgetWidth)
            self.status_label.setMinimumHeight(25)  # Set a default minimum height
            layout.addWidget(self.status_label)

            self.setWidget(widget)

            # Load saved API key
            self.load_api_key()

            # Create menu action for settings
            self.create_settings_menu()

        except Exception as e:
            import traceback
            QMessageBox.critical(None, "Error",
                                f"Failed to initialize Bria Mask Tools:\n{str(e)}\n\n{traceback.format_exc()}")
            raise

    def create_settings_menu(self):
        """Create menu action for BriaAI settings"""
        pass  # Will be implemented in the Extension class

    def on_mode_changed(self):
        """Handle mode changes and update UI accordingly"""
        mode = self.mode_button_group.checkedId()

        # Update button text based on mode
        if mode == 2:  # Generate Mask mode
            self.action_button.setText("Generate Mask")
        else:
            self.action_button.setText("Remove")

        # Disable batch for Remove Background with Mask mode
        if mode == 1:  # Remove Background with Mask
            self.batch_checkbox.setChecked(False)
            self.batch_checkbox.setEnabled(False)
            self.status_label.setText(
                "Batch processing is not supported when using manual masks or selections.")
        else:
            self.batch_checkbox.setEnabled(True)
            self.status_label.clear()

    def show_settings_dialog(self):
        """Show settings dialog for API key configuration"""
        dialog = BriaAISettingsDialog(self)
        dialog.set_api_key(self.api_key)
        if dialog.exec_() == QDialog.Accepted:
            new_key = dialog.get_api_key()
            self.save_api_key(new_key)

    def toggle_advanced_options(self):
        is_advanced = self.advanced_checkbox.isChecked()
        self.advanced_group.setVisible(is_advanced)
        self.update_debug_buttons_visibility()
        self.toggle_batch_mode()  # Update thread visibility

    def toggle_thread_count(self):
        self.thread_count_spinbox.setVisible(not self.auto_thread_checkbox.isChecked())

    def copy_status_text(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.status_label.toPlainText())
        QMessageBox.information(self, "Copied", "Status text copied to clipboard.", QMessageBox.Ok)

    def toggle_batch_mode(self):
        is_batch = self.batch_checkbox.isChecked()
        is_advanced = self.advanced_checkbox.isChecked()
        self.auto_thread_checkbox.setVisible(is_batch and is_advanced)
        self.thread_count_spinbox.setVisible(is_batch and is_advanced and not self.auto_thread_checkbox.isChecked())

    def toggle_debug_mode(self):
        self.update_debug_buttons_visibility()

    def update_debug_buttons_visibility(self):
        is_advanced = self.advanced_checkbox.isChecked()
        debug_mode = self.debug_checkbox.isChecked()
        self.open_temp_dir_button.setVisible(is_advanced and debug_mode)
        self.copy_text_button.setVisible(is_advanced and debug_mode)

    def open_temp_directory(self):
        temp_dir = tempfile.gettempdir()
        if sys.platform.startswith('darwin'):  # macOS
            subprocess.call(['open', temp_dir])
        elif sys.platform.startswith('win'):  # Windows
            os.startfile(temp_dir)
        else:  # Linux and other Unix-like
            subprocess.call(['xdg-open', temp_dir])

    def load_api_key(self):
        app = Krita.instance()

        # Check for the old API key setting
        old_api_key = app.readSetting("BackgroundRemoverBriaAI", "api_key", "")
        if old_api_key:
            # If the old key is found, save it to the new setting and delete the old setting
            app.writeSetting("AGD_BriaAI", "api_key", old_api_key)
            app.writeSetting("BackgroundRemoverBriaAI", "api_key", "")  # Clear the old key
            self.api_key = old_api_key
        else:
            # If no old key is found, just load the new key
            self.api_key = app.readSetting("AGD_BriaAI", "api_key", "")

        # Populate the input field with the loaded key
        if hasattr(self, 'api_key_input'):
            self.api_key_input.setText(self.api_key)

    def save_api_key(self, key):
        app = Krita.instance()
        app.writeSetting("AGD_BriaAI", "api_key", key)
        self.api_key = key
        self.status_label.setText("API Key saved")
        # Clear any API key error status
        if hasattr(self, 'api_key_status'):
            self.api_key_status.setText("")
            self.api_key_status.setStyleSheet("")
        if hasattr(self, 'api_key_input'):
            self.api_key_input.setStyleSheet("")  # Reset to default style

    def detect_mask(self, document, node):
        """Detect mask from various sources in priority order"""
        # 1. Check for any mask attached to the current layer
        if node.childNodes():
            for child in node.childNodes():
                if child.type() in ["transparencymask", "filtermask", "transformmask",
                                   "selectionmask", "colorizemask"]:
                    return child, f"{child.type()}"

        # 2. Check for active selection
        selection = document.selection()
        if selection is not None:
            # Check if selection has valid dimensions
            if selection.width() > 0 and selection.height() > 0:
                return selection, "selection"

        # 3. Check if there's another selected layer that could be used as mask
        # (user can select multiple layers - one for image, one for mask)
        window = Krita.instance().activeWindow()
        if window and window.activeView():
            selected_nodes = window.activeView().selectedNodes()
            if len(selected_nodes) > 1:
                # Find a layer that's not the current node
                for selected in selected_nodes:
                    if selected != node:
                        # Any layer can be used as a mask
                        return selected, "selected_layer"

        return None, None

    def show_settings(self):
        """Show the BriaAI settings dialog"""
        dialog = BriaAISettingsDialog(self)
        dialog.set_api_key(self.api_key)

        if dialog.exec_() == QDialog.Accepted:
            self.api_key = dialog.get_api_key()
            # Save to Krita settings
            app = Krita.instance()
            app.writeSetting("AGD_BriaAI", "api_key", self.api_key)
            self.status_label.setText("API key updated successfully")

    def remove_background(self):
        try:
            self.status_label.setText("Processing...")

            start_time = time.time()

            # Get selected mode
            mode = self.mode_button_group.checkedId()
            mode_names = ["Remove Background", "Remove Background with Mask", "Generate Mask"]
            mode_name = mode_names[mode]

            # Create a progress dialog
            try:
                progress = QProgressDialog(f"{mode_name}...", "Cancel", 0, 100,
                                          Krita.instance().activeWindow().qwindow())
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(0)
                progress.setValue(0)
                progress.show()
            except Exception as e:
                self.status_label.setText(f"Error creating progress dialog: {e}")
                return

            # Clear the status_label field
            self.status_label.setText("Preparing file(s) and request(s)...")

            # Disable UI during processing to prevent re-entrancy issues
            self.action_button.setEnabled(False)
            self.batch_checkbox.setEnabled(False)
            self.mode_button_group.setExclusive(False)
            for button in [self.remove_bg_radio, self.remove_bg_mask_radio, self.generate_mask_radio]:
                button.setEnabled(False)
            self.mode_button_group.setExclusive(True)

            # Get API key from input field
            self.api_key = self.api_key_input.text().strip()

            # Clean the API key - remove any quotes or extra whitespace
            self.api_key = self.api_key.strip('"\'').strip()

            # Check if API key is blank
            if self.api_key == "":
                self.status_label.setText("Error: API key is blank. Please enter your API key in the field above.")
                progress.close()
                # Re-enable UI
                self.enable_ui()
                return

            # Basic API key validation
            if len(self.api_key) < 10:
                self.status_label.setText("Error: API key appears too short. Please check your API key.")
                progress.close()
                # Re-enable UI
                self.enable_ui()
                return

            # Log API key info in debug mode
            if self.debug_checkbox and self.debug_checkbox.isChecked():
                self.log_error(f"Using API key starting with: {self.api_key[:5]}...")
                self.log_error(f"API key length: {len(self.api_key)}")


            application = Krita.instance()
            document = application.activeDocument()
            window = application.activeWindow()


            if not document:
                self.status_label.setText("No active document")
                progress.close()
                self.enable_ui()
                return

            if not window:
                self.status_label.setText("No active window")
                progress.close()
                self.enable_ui()
                return

            view = window.activeView()
            if not view:
                self.status_label.setText("No active view")
                progress.close()
                self.enable_ui()
                return

            nodes = [document.activeNode()] if not self.batch_checkbox.isChecked() else view.selectedNodes()
            if not nodes:
                self.status_label.setText("No active layer or no layers selected")
                progress.close()
                self.enable_ui()
                return

            # For Remove Background with Mask mode, validate mask availability
            if mode == 1:  # Remove Background with Mask
                mask, mask_type = self.detect_mask(document, nodes[0])
                if not mask:
                    self.status_label.setText(
                        "No mask found. Please:\n"
                        "• Create a selection, or\n"
                        "• Add a mask to your layer, or\n"
                        "• Select both image and mask layers")
                    progress.close()
                    self.enable_ui()
                    return

            # Check if we're on a Unix-like system (macOS or Linux)
            if sys.platform.startswith('darwin') or sys.platform.startswith('linux'):
                # Set the SSL certificate file path for macOS and Linux
                cert_file = '/etc/ssl/cert.pem'

                # Check if the certificate file exists
                if os.path.exists(cert_file):
                    os.environ['SSL_CERT_FILE'] = cert_file
                else:
                    self.status_label.setText(f"Warning: Certificate file {cert_file} not found.")

            try:
                context = ssl.create_default_context()
            except Exception as e:
                self.status_label.setText(f"Error creating SSL context: {str(e)}")
                progress.close()
                self.enable_ui()
                return

            # Setup for error handling
            processed_count = 0
            success_count = 0
            total_count = len(nodes)
            error_messages = []

            # Determine max_workers based on user selection
            if self.advanced_checkbox.isChecked() and not self.auto_thread_checkbox.isChecked():
                max_workers = self.thread_count_spinbox.value()
            else:
                max_workers = os.cpu_count() or multiprocessing.cpu_count()

            # Set batch mode
            try:
                document.setBatchmode(True)
            except Exception as e:
                # Continue anyway, batch mode is optional
                pass

            progress.setValue(10)

            # Process without threading to avoid QThread issues
            for node in nodes:
                try:
                    result = self.process_node(node, self.api_key, document, context, mode)
                    processed_count += 1
                    if "successfully" in result.lower():
                        success_count += 1
                    else:
                        error_messages.append(result)
                    self.status_label.append(f"Processed {processed_count}/{total_count}: {result}")
                    progress.setValue(10 + int(90 * processed_count / total_count))
                except Exception as e:
                    processed_count += 1
                    error_msg = f"Error processing node: {str(e)}"
                    error_messages.append(error_msg)
                finally:
                    pass  # Removed processEvents to prevent re-entrancy issues

            # Unset batch mode
            try:
                document.setBatchmode(False)
            except Exception:
                pass

            # End timing the process
            end_time = time.time()

            # Calculate the total time taken in milliseconds
            total_time_ms = int((end_time - start_time) * 1000)

            # Final status update
            final_status = f"Completed. Processed {success_count}/{total_count} successfully. ({total_time_ms}ms)"
            if error_messages:
                final_status += f"\nErrors:\n" + "\n".join(error_messages)

            self.status_label.setText(final_status)
            progress.setValue(100)
            progress.close()

            # Re-enable UI after processing
            self.enable_ui()
        except Exception as e:
            import traceback
            error_msg = f"ERROR in remove_background: {str(e)}\n{traceback.format_exc()}"
            self.status_label.setText(error_msg)
            try:
                progress.close()
            except:
                pass

            # Re-enable UI after error
            self.enable_ui()

    def process_node(self, node, api_key, document, context, mode):
        """Process node based on selected mode"""
        if mode == 0:  # Remove Background
            return self.process_background_removal(node, api_key, document, context)
        elif mode == 1:  # Remove Background with Mask
            return self.process_masked_removal(node, api_key, document, context)
        elif mode == 2:  # Generate Mask
            return self.process_mask_generation(node, api_key, document, context)

    def process_background_removal(self, node, api_key, document, context):
        """Process standard background removal"""
        # Prepare the temporary file path
        temp_dir = tempfile.gettempdir()
        unique_id = str(uuid.uuid4())[:8]
        temp_file = os.path.join(temp_dir, f"temp_layer_{unique_id}.jpg")
        result_file = None

        # Create an InfoObject for export configuration
        export_params = InfoObject()
        export_params.setProperty("quality", 100)  # Use maximum quality for JPEG
        export_params.setProperty("forceSRGB", True)  # Force sRGB color space
        export_params.setProperty("saveProfile", False)  # Don't save color profile
        export_params.setProperty("alpha", False)  # No alpha
        export_params.setProperty("flatten", True)  # Flatten the image for JPEG export

        # Save the active node as JPG
        try:
            # Simply save without checking return value like the original
            node.save(temp_file, 1.0, 1.0, export_params, node.bounds())
        except Exception as e:
            return f"Error exporting image: {str(e)}"

        # Prepare the API request
        url = "https://engine.prod.bria-api.com/v1/background/remove"

        try:
            # Prepare the multipart form data
            boundary = 'wL36Yn8afVp8Ag7AmP8qZ0SA4n1v9T'
            data = []
            data.append(f'--{boundary}'.encode())
            data.append(b'Content-Disposition: form-data; name="file"; filename="temp_layer.jpg"')
            data.append(b'Content-Type: image/jpg')
            data.append(b'')
            with open(temp_file, 'rb') as f:
                data.append(f.read())
            data.append(f'--{boundary}--'.encode())
            data.append(b'')
            body = b'\r\n'.join(data)

            # Create and send the request
            headers = {
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'api_token': api_key,
                'User-Agent': 'Krita-Bria-MaskTools/1.0'
            }
            req = urllib.request.Request(url, data=body, headers=headers, method='POST')

            # Log request details if debug mode
            if self.debug_checkbox.isChecked():
                self.log_error(f"Request URL: {url}")
                self.log_error(f"Request headers: {headers}")
                self.log_error(f"API key length: {len(api_key)}")
                if len(api_key) > 5:
                    self.log_error(f"API key first 5 chars: {api_key[:5]}...")
                else:
                    self.log_error(f"API key: {api_key}")

            with urllib.request.urlopen(req, timeout=30, context=context) as response:
                if response.status == 200:
                    # Parse the JSON response
                    try:
                        response_data = json.loads(response.read().decode('utf-8'))
                    except json.JSONDecodeError:
                        return "Error: Invalid JSON response from server"

                    result_url = response_data.get('result_url')

                    if self.debug_checkbox.isChecked():
                        self.log_error(f"Response data: {response_data}")

                    if result_url:
                        # Download the image from the URL
                        result_file = os.path.join(temp_dir, f"result_layer_{unique_id}.png")
                        try:
                            urllib.request.urlretrieve(result_url, result_file)
                        except Exception as e:
                            return f"Error downloading result: {str(e)}"

                        # Rename layer
                        new_layer_name = "Cutout"

                        # Get the color space of the original document
                        original_color_space = document.colorModel()

                        # Create a new layer in the document
                        new_layer = document.createNode(new_layer_name, "paintlayer")
                        if not new_layer:
                            return "Error: Failed to create new layer"

                        # Load the image
                        image = QImage(result_file)
                        if image.isNull():
                            return "Error: Failed to load result image"

                        # Convert image data to bytes
                        ptr = image.constBits()
                        ptr.setsize(image.byteCount())
                        new_layer.setPixelData(bytes(ptr), 0, 0, image.width(), image.height())

                        # Add the new layer to the document
                        document.rootNode().addChildNode(new_layer, node)

                        if original_color_space != "RGBA":
                            # For non-RGBA documents, the layer inherits the document's color space
                            result = (f"Background removed successfully for {node.name()} "
                                     f"(Working in {original_color_space} color space)")
                        else:
                            result = f"Background removed successfully for {node.name()}"

                        # Hide the original layer
                        try:
                            node.setVisible(False)
                        except Exception:
                            pass  # Not critical if hiding fails

                        try:
                            document.refreshProjection()
                        except Exception:
                            pass  # Non-critical if refresh fails

                        if self.debug_checkbox.isChecked():
                            result += f"\nDebug: Temporary files saved at {temp_file} and {result_file}"
                        else:
                            try:
                                os.remove(result_file)
                            except Exception:
                                pass

                        return result
                    else:
                        return "Error: No result URL in response"
                else:
                    return self.handle_error(response.status)

        except urllib.error.HTTPError as e:
            # Try to read the error response body for more details
            error_body = ""
            try:
                error_body = e.read().decode('utf-8')
                # Try to parse as JSON for better formatting
                try:
                    error_json = json.loads(error_body)
                    error_body = json.dumps(error_json, indent=2)
                except:
                    pass
            except:
                pass

            # Special handling for 401 errors
            if e.code == 401:
                error_msg = ("INVALID API KEY\n\n"
                           "Your API key was rejected by BriaAI.\n\n"
                           "Please check:\n"
                           "• You've entered the correct API key\n"
                           "• No extra spaces or quotes in the key\n"
                           "• The key hasn't expired\n\n"
                           "To get a valid API key:\n"
                           "1. Go to https://www.bria.ai\n"
                           "2. Sign up for a free account (no credit card)\n"
                           "3. Copy your API key from the dashboard\n"
                           "4. Paste it in the API Key field above\n\n"
                           f"Error details: {error_body}")
                # Highlight the API key field with error
                self.highlight_invalid_api_key()
            else:
                error_msg = f"{self.handle_error(e.code)} - Details: {error_body}"

            self.log_error(f"HTTPError in background removal: Status {e.code}")
            self.log_error(f"URL: {url}")
            self.log_error(f"Response headers: {dict(e.headers)}")
            self.log_error(f"Response body: {error_body}")
            return error_msg
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                error_msg = "SSL Certificate verification failed. You may need to update your certificates."
            else:
                error_msg = f"URLError: {str(e)}"
            self.log_error(f"URLError in background removal: {error_msg}")
            return error_msg
        except json.JSONDecodeError as e:
            self.log_error(f"JSON decode error: {str(e)}")
            return "Error: Invalid JSON response"
        except Exception as e:
            self.log_error(f"Unexpected error in background removal: {str(e)}")
            import traceback
            self.log_error(traceback.format_exc())
            return f"Unexpected error: {str(e)}"

        finally:
            if temp_file and os.path.exists(temp_file) and not self.debug_checkbox.isChecked():
                try:
                    os.remove(temp_file)
                except Exception:
                    pass  # Ignore cleanup errors

    def process_masked_removal(self, node, api_key, document, context):
        """Process background removal with mask using /eraser endpoint"""
        # Detect mask
        mask, mask_type = self.detect_mask(document, node)
        if not mask:
            return ("Error: No mask detected. Try: creating a selection, "
                    "adding a mask to your layer, or selecting multiple layers.")

        # Log mask detection if debug mode
        if self.debug_checkbox.isChecked():
            self.log_error(f"Detected mask type: {mask_type}")
            if hasattr(mask, 'name'):
                self.log_error(f"Mask name: {mask.name()}")
            if hasattr(mask, 'bounds'):
                bounds = mask.bounds()
                self.log_error(f"Mask bounds: {bounds.x()}, {bounds.y()}, {bounds.width()}, {bounds.height()}")

        # Prepare temporary files
        temp_dir = tempfile.gettempdir()
        unique_id = str(uuid.uuid4())[:8]
        temp_image_file = os.path.join(temp_dir, f"temp_image_{unique_id}.png")
        temp_mask_file = os.path.join(temp_dir, f"temp_mask_{unique_id}.png")
        result_file = None

        try:
            # Export image as PNG
            export_params = InfoObject()
            export_params.setProperty("alpha", True)
            export_params.setProperty("compression", 6)
            export_params.setProperty("indexed", False)
            try:
                # Log export attempt if debug mode
                if self.debug_checkbox.isChecked():
                    self.log_error(f"Exporting image to: {temp_image_file}")
                    bounds = node.bounds()
                    self.log_error(f"Node bounds: {bounds.x()}, {bounds.y()}, {bounds.width()}, {bounds.height()}")

                # Simply save without checking return value like the original
                node.save(temp_image_file, 1.0, 1.0, export_params, node.bounds())

                # Verify file was created
                if not os.path.exists(temp_image_file):
                    return "Error: Export file was not created"

                file_size = os.path.getsize(temp_image_file)
                if file_size == 0:
                    return "Error: Export file is empty"

                if self.debug_checkbox.isChecked():
                    self.log_error(f"Export successful, file size: {file_size} bytes")

            except Exception as e:
                return f"Error exporting image: {str(e)}"

            # Export mask based on type
            if mask_type == "selection":
                # Get the bounds of the full image
                full_bounds = document.bounds()
                if not full_bounds or full_bounds.width() <= 0 or full_bounds.height() <= 0:
                    return "Error: Invalid document bounds"

                # Create white on black mask image
                try:
                    # Check for reasonable image size to prevent memory issues
                    if full_bounds.width() * full_bounds.height() > 100000000:  # 100 megapixels
                        return "Error: Image too large for mask processing"

                    mask_image = QImage(full_bounds.width(), full_bounds.height(), QImage.Format_ARGB32)
                    if mask_image.isNull():
                        return "Error: Failed to allocate mask image"
                    mask_image.fill(Qt.black)
                except Exception as e:
                    return f"Error creating mask image: {str(e)}"

                # Get selection bounds and data
                sel_bounds = mask.bounds()
                if sel_bounds and sel_bounds.width() > 0 and sel_bounds.height() > 0:
                    sel_data = mask.pixelData(sel_bounds.x(), sel_bounds.y(),
                                             sel_bounds.width(), sel_bounds.height())

                    # Paint white where selection exists
                    if sel_data and len(sel_data) > 0:
                        for y in range(sel_bounds.height()):
                            for x in range(sel_bounds.width()):
                                try:
                                    idx = (y * sel_bounds.width() + x)
                                    if idx >= len(sel_data):
                                        continue

                                    value = sel_data[idx] & 0xFF
                                    if value > 0:
                                        px = sel_bounds.x() + x
                                        py = sel_bounds.y() + y
                                        if 0 <= px < full_bounds.width() and 0 <= py < full_bounds.height():
                                            gray = qRgb(value, value, value)
                                            mask_image.setPixel(px, py, gray)
                                except (IndexError, OverflowError):
                                    # Skip this pixel if there's an error
                                    continue

                mask_image.save(temp_mask_file, "PNG")
            else:
                # Export mask layer/transparency mask
                try:
                    # Simply save without checking return value like the original
                    mask.save(temp_mask_file, 1.0, 1.0, export_params, mask.bounds())
                except Exception as e:
                    return f"Error exporting mask: {str(e)}"

            # Prepare API request for /erase_foreground endpoint
            url = "https://engine.prod.bria-api.com/v1/erase_foreground"

            # Read and encode both files as base64
            try:
                with open(temp_image_file, 'rb') as f:
                    encoded_image = base64.b64encode(f.read()).decode('utf-8')

                with open(temp_mask_file, 'rb') as f:
                    encoded_mask = base64.b64encode(f.read()).decode('utf-8')

                if self.debug_checkbox.isChecked():
                    self.log_error(f"Encoded image size: {len(encoded_image)} bytes")
                    self.log_error(f"Encoded mask size: {len(encoded_mask)} bytes")
            except Exception as e:
                return f"Error encoding files: {str(e)}"

            # Prepare JSON request
            request_data = {
                "file": encoded_image,
                "mask_file": encoded_mask,
                "mask_type": "manual",
                "sync": True,
                "preserve_alpha": self.preserve_alpha_checkbox.isChecked(),
                "content_moderation": False
            }

            # Add prompt if provided
            prompt_text = self.prompt_input.text().strip()
            if prompt_text:
                request_data["prompt"] = prompt_text
                if self.debug_checkbox.isChecked():
                    self.log_error(f"Using prompt: {prompt_text}")

            body = json.dumps(request_data).encode('utf-8')

            # Create and send request with retry
            headers = {
                'Content-Type': 'application/json',
                'api_token': api_key,
                'User-Agent': 'Krita-Bria-MaskTools/1.0'
            }

            for attempt in range(2):  # Try twice
                try:
                    req = urllib.request.Request(url, data=body, headers=headers, method='POST')

                    # Log request details if debug mode
                    if self.debug_checkbox.isChecked():
                        self.log_error(f"Masked removal request URL: {url}")
                        self.log_error(f"Request headers: {headers}")
                        self.log_error(f"Image file size: {os.path.getsize(temp_image_file)} bytes")
                        self.log_error(f"Mask file size: {os.path.getsize(temp_mask_file)} bytes")

                    with urllib.request.urlopen(req, timeout=30, context=context) as response:
                        if response.status == 200:
                            try:
                                response_data = json.loads(response.read().decode('utf-8'))
                            except json.JSONDecodeError:
                                return "Error: Invalid JSON response from server"

                            result_url = response_data.get('result_url')

                            if result_url:
                                # Download result
                                result_file = os.path.join(temp_dir, f"result_masked_{unique_id}.png")
                                try:
                                    urllib.request.urlretrieve(result_url, result_file)
                                except Exception as e:
                                    return f"Error downloading result: {str(e)}"

                                # Create new layer with descriptive name
                                layer_name = "Inpainted"
                                if prompt_text:
                                    # Include prompt in layer name if it's short enough
                                    if len(prompt_text) <= 20:
                                        layer_name = f"Inpainted ({prompt_text})"
                                    else:
                                        layer_name = f"Inpainted ({prompt_text[:17]}...)"
                                new_layer = document.createNode(layer_name, "paintlayer")
                                if not new_layer:
                                    return "Error: Failed to create new layer"
                                image = QImage(result_file)
                                if image.isNull():
                                    return "Error: Failed to load result image"

                                # Convert image data to bytes
                                ptr = image.constBits()
                                ptr.setsize(image.byteCount())
                                new_layer.setPixelData(bytes(ptr), 0, 0, image.width(), image.height())

                                # Add layer above original
                                parent = node.parentNode()
                                if not parent:
                                    parent = document.rootNode()
                                parent.addChildNode(new_layer, node)

                                # Hide original
                                try:
                                    node.setVisible(False)
                                except Exception:
                                    pass  # Not critical if hiding fails
                                try:
                                    document.refreshProjection()
                                except Exception:
                                    pass  # Non-critical if refresh fails

                                result_msg = f"Inpainting completed successfully for {node.name()}"
                                if prompt_text:
                                    result_msg += f" with prompt: '{prompt_text}'"
                                return result_msg
                            else:
                                return "Error: No result URL in response"
                        else:
                            return self.handle_error(response.status)

                except urllib.error.HTTPError as e:
                    if attempt == 0:  # First attempt failed, retry
                        self.log_error(f"First attempt failed for masked removal: {e.code}")
                        time.sleep(1)
                        continue
                    error_body = ""
                    try:
                        error_body = e.read().decode('utf-8')
                        # Try to parse as JSON for better formatting
                        try:
                            error_json = json.loads(error_body)
                            error_body = json.dumps(error_json, indent=2)
                        except:
                            pass
                    except:
                        pass

                    # Special handling for 401 errors
                    if e.code == 401:
                        error_msg = ("INVALID API KEY\n\n"
                                   "Your API key was rejected by BriaAI.\n\n"
                                   "Please check:\n"
                                   "• You've entered the correct API key\n"
                                   "• No extra spaces or quotes in the key\n"
                                   "• The key hasn't expired\n\n"
                                   "To get a valid API key:\n"
                                   "1. Go to https://www.bria.ai\n"
                                   "2. Sign up for a free account (no credit card)\n"
                                   "3. Copy your API key from the dashboard\n"
                                   "4. Paste it in the API Key field above\n\n"
                                   f"Error details: {error_body}")
                        # Highlight the API key field with error
                        self.highlight_invalid_api_key()
                    else:
                        error_msg = f"{self.handle_error(e.code)} - Details: {error_body}"

                    self.log_error(f"HTTPError in masked removal: {e.code}")
                    self.log_error(f"URL: {url}")
                    self.log_error(f"Error body: {error_body}")
                    return error_msg
                except Exception as e:
                    if attempt == 0:
                        self.log_error(f"First attempt error: {str(e)}")
                        time.sleep(1)
                        continue
                    self.log_error(f"Error in masked removal: {str(e)}")
                    import traceback
                    self.log_error(traceback.format_exc())
                    return f"Error: {str(e)}"

        finally:
            # Cleanup temp files
            for f in [temp_image_file, temp_mask_file, result_file]:
                if f and os.path.exists(f) and not self.debug_checkbox.isChecked():
                    try:
                        os.remove(f)
                    except Exception:
                        pass  # Ignore cleanup errors

    def process_mask_generation(self, node, api_key, document, context):
        """Generate masks using /mask_generator endpoint"""
        # Prepare temporary file
        temp_dir = tempfile.gettempdir()
        unique_id = str(uuid.uuid4())[:8]
        temp_file = os.path.join(temp_dir, f"temp_layer_{unique_id}.jpg")

        try:
            # Export as JPEG
            export_params = InfoObject()
            export_params.setProperty("quality", 100)
            export_params.setProperty("forceSRGB", True)
            export_params.setProperty("alpha", False)
            try:
                # Log export attempt if debug mode
                if self.debug_checkbox.isChecked():
                    self.log_error(f"Exporting image to: {temp_file}")
                    bounds = node.bounds()
                    self.log_error(f"Node bounds: {bounds.x()}, {bounds.y()}, {bounds.width()}, {bounds.height()}")

                # Simply save without checking return value like the original
                node.save(temp_file, 1.0, 1.0, export_params, node.bounds())

                # Verify file was created
                if not os.path.exists(temp_file):
                    return "Error: Export file was not created"

                file_size = os.path.getsize(temp_file)
                if file_size == 0:
                    return "Error: Export file is empty"

                if self.debug_checkbox.isChecked():
                    self.log_error(f"Export successful, file size: {file_size} bytes")

            except Exception as e:
                return f"Error exporting image: {str(e)}"

            # Prepare API request
            # The mask_generator endpoint requires JSON format with base64-encoded file
            url = "https://engine.prod.bria-api.com/v1/objects/mask_generator"

            # Load the exported image to check dimensions and scale if needed
            export_img = QImage(temp_file)
            if export_img.isNull():
                return "Error: Failed to load exported image"

            original_width = export_img.width()
            original_height = export_img.height()

            if self.debug_checkbox.isChecked():
                self.log_error(f"Original exported dimensions: {original_width}x{original_height}")

            # Scale to 800px on longer dimension
            if original_width >= original_height:
                scaled_width = 800
                scaled_height = round(original_height * (800.0 / original_width))
            else:
                scaled_height = 800
                scaled_width = round(original_width * (800.0 / original_height))

            if self.debug_checkbox.isChecked():
                self.log_error(f"Scaling to: {scaled_width}x{scaled_height}")

            # Scale the image
            scaled_img = export_img.scaled(scaled_width, scaled_height,
                                          Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Save scaled image to temp file
            scaled_temp_file = os.path.join(temp_dir, f"scaled_{unique_id}.jpg")
            if not scaled_img.save(scaled_temp_file, "JPEG", 90):
                return "Error: Failed to save scaled image"

            # Read and encode the scaled image file as base64
            try:
                with open(scaled_temp_file, 'rb') as f:
                    file_data = f.read()
                    encoded_file = base64.b64encode(file_data).decode('utf-8')

                if self.debug_checkbox.isChecked():
                    self.log_error(f"Encoded file size: {len(encoded_file)} bytes")
            except Exception as e:
                return f"Error encoding image: {str(e)}"

            # Prepare JSON request with base64-encoded file
            request_data = {
                "file": encoded_file,
                "content_moderation": False,
                "sync": True
            }

            body = json.dumps(request_data).encode('utf-8')

            headers = {
                'Content-Type': 'application/json',
                'api_token': api_key,
                'User-Agent': 'Krita-Bria-MaskTools/1.0'
            }

            # Send request with retry
            for attempt in range(2):
                try:
                    req = urllib.request.Request(url, data=body, headers=headers, method='POST')

                    # Log request details if debug mode
                    if self.debug_checkbox.isChecked():
                        self.log_error(f"Mask generation request URL: {url}")
                        self.log_error(f"Request headers: {headers}")
                        self.log_error(f"Scaled image file size: {os.path.getsize(scaled_temp_file)} bytes")

                    with urllib.request.urlopen(req, timeout=30, context=context) as response:
                        if response.status == 200:
                            try:
                                response_data = json.loads(response.read().decode('utf-8'))
                            except json.JSONDecodeError:
                                return "Error: Invalid JSON response from server"

                            # Check for different response formats
                            objects_masks_url = response_data.get('objects_masks')
                            masks_list = response_data.get('masks', [])

                            if self.debug_checkbox.isChecked():
                                self.log_error(f"Response data: {response_data}")

                            mask_count = 0

                            if objects_masks_url:
                                # Download the file (could be ZIP or image)
                                download_file = os.path.join(temp_dir, f"masks_{unique_id}_download")
                                try:
                                    urllib.request.urlretrieve(objects_masks_url, download_file)
                                except Exception as e:
                                    return f"Error downloading masks file: {str(e)}"

                                # Check if it's a ZIP file or an image
                                try:
                                    # Try to open as ZIP first
                                    with zipfile.ZipFile(download_file, 'r') as zip_ref:
                                        # Validate ZIP contents before extraction
                                        total_size = sum(zinfo.file_size for zinfo in zip_ref.filelist)
                                        if total_size > 100 * 1024 * 1024:  # 100MB limit for total extracted size
                                            return f"Error: ZIP file too large ({total_size} bytes)"

                                        # Check for suspicious filenames
                                        for zinfo in zip_ref.filelist:
                                            if os.path.isabs(zinfo.filename) or ".." in zinfo.filename:
                                                return f"Error: Suspicious filename in ZIP: {zinfo.filename}"

                                        # Extract all files to temp directory
                                        extract_dir = os.path.join(temp_dir, f"masks_{unique_id}_extracted")
                                        zip_ref.extractall(extract_dir)

                                        if self.debug_checkbox.isChecked():
                                            self.log_error(f"ZIP contains files: {zip_ref.namelist()}")

                                        # Process each extracted mask (walk recursively)
                                        mask_files = []
                                        if self.debug_checkbox.isChecked():
                                            self.log_error(f"Walking directory: {extract_dir}")

                                        for root, dirs, files in os.walk(extract_dir):
                                            if self.debug_checkbox.isChecked() and files:
                                                self.log_error(f"Found {len(files)} files in {root}")

                                            for filename in files:
                                                filepath = os.path.join(root, filename)

                                                # Skip directories (not needed with os.walk but kept for safety)
                                                if os.path.isdir(filepath):
                                                    continue

                                                # Validate it's actually an image file
                                                try:
                                                    # Use QImage to check if it's a valid image
                                                    test_img = QImage(filepath)
                                                    if test_img.isNull():
                                                        if self.debug_checkbox.isChecked():
                                                            self.log_error(f"Skipping invalid image file: {filename}")
                                                        continue

                                                    # Log successful load
                                                    if self.debug_checkbox.isChecked():
                                                        self.log_error(f"Successfully loaded {filename}: "
                                                                     f"{test_img.width()}x{test_img.height()}")
                                                except Exception as e:
                                                    if self.debug_checkbox.isChecked():
                                                        self.log_error(
                                                            f"Error checking file type for {filename}: {str(e)}")
                                                    continue

                                                # Skip the panoptic map as it's not useful as a mask
                                                if 'panoptic' in filename.lower():
                                                    if self.debug_checkbox.isChecked():
                                                        self.log_error(f"Skipping panoptic map: {filename}")
                                                    continue

                                                # Also validate file size (skip suspiciously large files)
                                                file_size = os.path.getsize(filepath)
                                                if file_size > 50 * 1024 * 1024:  # 50MB limit
                                                    if self.debug_checkbox.isChecked():
                                                        self.log_error(
                                                            f"Skipping suspiciously large file: {filename} "
                                                            f"({file_size} bytes)")
                                                    continue

                                                mask_files.append((filepath, filename))

                                        # Sort masks numerically if they have numbers
                                        def extract_number(item):
                                            filepath, filename = item
                                            match = re.search(r'_(\d+)\.', filename)
                                            return int(match.group(1)) if match else 999

                                        mask_files.sort(key=extract_number)

                                        for idx, (mask_file, filename) in enumerate(mask_files):

                                            # Extract mask number from filename if available
                                            mask_num = extract_number((mask_file, filename))
                                            if mask_num != 999:
                                                mask_name = f"Object Mask {mask_num}"
                                            else:
                                                mask_name = f"Mask {idx + 1}"

                                            # Create mask as either transparency mask or separate layer
                                            if self.masks_as_layers_checkbox.isChecked():
                                                # Create as separate paint layer
                                                mask_layer = document.createNode(mask_name, "paintlayer")
                                            else:
                                                # Create as transparency mask (default)
                                                mask_layer = document.createNode(mask_name, "transparencymask")

                                            if not mask_layer:
                                                continue  # Skip if layer creation fails

                                            # Load mask image
                                            if self.debug_checkbox.isChecked():
                                                self.log_error(f"Loading mask from: {mask_file}")

                                            mask_image = QImage(mask_file)
                                            if not mask_image.isNull():
                                                if self.debug_checkbox.isChecked():
                                                    self.log_error(
                                                        f"Mask loaded successfully: "
                                                        f"{mask_image.width()}x{mask_image.height()}")
                                                    self.log_error(
                                                        f"Original layer bounds: "
                                                        f"{node.bounds().width()}x{node.bounds().height()}")

                                                # Always scale mask back to original dimensions
                                                # The mask is returned at the scaled size (800px on longer dimension)
                                                # We need to scale it back to match the original layer
                                                layer_width = node.bounds().width()
                                                layer_height = node.bounds().height()

                                                if self.debug_checkbox.isChecked():
                                                    self.log_error(
                                                        f"Scaling mask from {mask_image.width()}x{mask_image.height()} "
                                                        f"back to original size: {layer_width}x{layer_height}")

                                                # Scale mask to match original layer dimensions
                                                mask_image = mask_image.scaled(
                                                    layer_width, layer_height,
                                                    Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

                                                # Convert image data to bytes
                                                ptr = mask_image.constBits()
                                                ptr.setsize(mask_image.byteCount())
                                                mask_layer.setPixelData(bytes(ptr), 0, 0,
                                                                      mask_image.width(), mask_image.height())

                                                # Add the mask layer
                                                if self.masks_as_layers_checkbox.isChecked():
                                                    # Add as sibling layer (above the original)
                                                    parent = node.parentNode()
                                                    if not parent:
                                                        parent = document.rootNode()
                                                    parent.addChildNode(mask_layer, node)
                                                else:
                                                    # Add as child transparency mask
                                                    node.addChildNode(mask_layer, None)

                                                mask_count += 1

                                                if self.debug_checkbox.isChecked():
                                                    self.log_error(f"Added mask: {filename}")
                                            else:
                                                if self.debug_checkbox.isChecked():
                                                    self.log_error(f"Failed to load mask image: {mask_file}")
                                except zipfile.BadZipFile:
                                    # Not a ZIP file, try as single image
                                    if self.debug_checkbox.isChecked():
                                        self.log_error("File is not a ZIP, trying as single image")

                                    # Validate it's actually an image file using QImage
                                    test_img = QImage(download_file)
                                    if test_img.isNull():
                                        return f"Error: Downloaded file is not a valid image"

                                    # Check file size
                                    file_size = os.path.getsize(download_file)
                                    if file_size > 50 * 1024 * 1024:  # 50MB limit
                                        return f"Error: Downloaded file too large ({file_size} bytes)"

                                    # Try to load as image
                                    mask_image = QImage(download_file)
                                    if not mask_image.isNull():
                                        # Create single transparency mask
                                        mask_layer = document.createNode("Generated Mask", "transparencymask")
                                        if mask_layer:
                                            # Convert image data to bytes
                                            ptr = mask_image.constBits()
                                            ptr.setsize(mask_image.byteCount())
                                            mask_layer.setPixelData(bytes(ptr), 0, 0,
                                                                  mask_image.width(), mask_image.height())

                                            # Add as child of the node
                                            node.addChildNode(mask_layer, None)
                                            mask_count = 1

                                    # Cleanup
                                    if not self.debug_checkbox.isChecked():
                                        try:
                                            os.remove(download_file)
                                        except Exception:
                                            pass
                                except Exception as e:
                                    return f"Error processing file: {str(e)}"
                                finally:
                                    # Cleanup ZIP and extracted files
                                    if not self.debug_checkbox.isChecked():
                                        try:
                                            shutil.rmtree(extract_dir)
                                            os.remove(download_file)
                                        except Exception:
                                            pass

                                if mask_count > 0:
                                    try:
                                        document.refreshProjection()
                                    except Exception:
                                        pass  # Non-critical if refresh fails
                                    return f"Generated {mask_count} masks for {node.name()}"
                                else:
                                    return "Error: No valid masks found in ZIP file"
                            elif masks_list and isinstance(masks_list, list):
                                # Handle individual mask URLs
                                for idx, mask_url in enumerate(masks_list):
                                    if not mask_url or not isinstance(mask_url, str):
                                        continue

                                    # Download mask
                                    mask_file = os.path.join(temp_dir, f"mask_{unique_id}_{idx}.png")
                                    try:
                                        urllib.request.urlretrieve(mask_url, mask_file)
                                    except Exception as e:
                                        if self.debug_checkbox.isChecked():
                                            self.log_error(f"Failed to download mask {idx}: {str(e)}")
                                        continue

                                    # Create transparency mask
                                    mask_name = f"Mask {idx + 1}"
                                    mask_layer = document.createNode(mask_name, "transparencymask")
                                    if not mask_layer:
                                        continue

                                    # Load mask image
                                    mask_image = QImage(mask_file)
                                    if not mask_image.isNull():
                                        # Convert image data to bytes
                                        ptr = mask_image.constBits()
                                        ptr.setsize(mask_image.byteCount())
                                        mask_layer.setPixelData(bytes(ptr), 0, 0,
                                                              mask_image.width(), mask_image.height())

                                        # Add as child of the node
                                        node.addChildNode(mask_layer, None)
                                        mask_count += 1

                                    # Cleanup
                                    if not self.debug_checkbox.isChecked():
                                        try:
                                            os.remove(mask_file)
                                        except Exception:
                                            pass

                                if mask_count > 0:
                                    try:
                                        document.refreshProjection()
                                    except Exception:
                                        pass
                                    return f"Generated {mask_count} masks for {node.name()}"
                                else:
                                    return "Error: Failed to process any masks"
                            else:
                                return "Error: No masks data in response"
                        else:
                            return self.handle_error(response.status)

                except urllib.error.HTTPError as e:
                    if attempt == 0:
                        self.log_error(f"First attempt failed for mask generation: {e.code}")
                        time.sleep(1)
                        continue
                    error_body = ""
                    try:
                        error_body = e.read().decode('utf-8')
                        # Try to parse as JSON for better formatting
                        try:
                            error_json = json.loads(error_body)
                            error_body = json.dumps(error_json, indent=2)
                        except:
                            pass
                    except:
                        pass

                    # Special handling for 401 errors
                    if e.code == 401:
                        error_msg = ("INVALID API KEY\n\n"
                                   "Your API key was rejected by BriaAI.\n\n"
                                   "Please check:\n"
                                   "• You've entered the correct API key\n"
                                   "• No extra spaces or quotes in the key\n"
                                   "• The key hasn't expired\n\n"
                                   "To get a valid API key:\n"
                                   "1. Go to https://www.bria.ai\n"
                                   "2. Sign up for a free account (no credit card)\n"
                                   "3. Copy your API key from the dashboard\n"
                                   "4. Paste it in the API Key field above\n\n"
                                   f"Error details: {error_body}")
                        # Highlight the API key field with error
                        self.highlight_invalid_api_key()
                    else:
                        error_msg = f"{self.handle_error(e.code)} - Details: {error_body}"

                    self.log_error(f"HTTPError in mask generation: {e.code}")
                    self.log_error(f"URL: {url}")
                    self.log_error(f"Error body: {error_body}")
                    return error_msg
                except Exception as e:
                    if attempt == 0:
                        self.log_error(f"First attempt error in mask generation: {str(e)}")
                        time.sleep(1)
                        continue
                    self.log_error(f"Error in mask generation: {str(e)}")
                    import traceback
                    self.log_error(traceback.format_exc())
                    return f"Error: {str(e)}"

        finally:
            if temp_file and os.path.exists(temp_file) and not self.debug_checkbox.isChecked():
                try:
                    os.remove(temp_file)
                except Exception:
                    pass  # Ignore cleanup errors

    def handle_error(self, status_code):
        error_messages = {
            206: "File value was not provided.",
            400: "Bad request. Please check your input.",
            401: "Unauthorized. Please check your API key.",
            403: "Forbidden. Your API key may not have access to this feature.",
            404: "Endpoint not found.",
            405: "Method not allowed.",
            413: "File too large. Please use a smaller image.",
            415: "Unsupported media type. Please use JPG or PNG format.",
            429: "Too many requests. Please wait a moment and try again.",
            460: "Failed to download image.",
            500: "Internal server error. Please try again later.",
            503: "Service temporarily unavailable. Please try again later.",
            506: "Insufficient data. The given input is not supported by the Bria API."
        }
        return (f"Error {status_code}: "
                f"{error_messages.get(status_code, 'Unknown error. Please check your connection.')}")

    def log_error(self, message):
        """Log error messages to both stderr and status label"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[{timestamp}] {message}"

        # Log to stderr
        sys.stderr.write(full_message + "\n")
        sys.stderr.flush()

        # Also print to stdout for better visibility
        print(full_message)

        # Also append to status label if in debug mode
        if hasattr(self, 'debug_checkbox') and self.debug_checkbox.isChecked():
            self.status_label.append(f"DEBUG: {message}")

    def highlight_invalid_api_key(self):
        """Highlight the API key field when it's invalid"""
        if hasattr(self, 'api_key_status'):
            self.api_key_status.setText("Invalid API Key - Please check and re-enter")
            self.api_key_status.setStyleSheet("QLabel { color: red; font-weight: bold; }")
        if hasattr(self, 'api_key_input'):
            self.api_key_input.setStyleSheet("QLineEdit { border: 2px solid red; }")

    def enable_ui(self):
        """Re-enable all UI elements after processing"""
        self.action_button.setEnabled(True)
        self.batch_checkbox.setEnabled(True)
        for button in [self.remove_bg_radio, self.remove_bg_mask_radio, self.generate_mask_radio]:
            button.setEnabled(True)

    def canvasChanged(self, canvas):
        pass

class BackgroundRemoverExtension(krita.Extension):

    def __init__(self, parent):
        super().__init__(parent)
        self.actions = []

    def setup(self):
        pass

    def createActions(self, window):
        # Create action for BriaAI settings
        action = window.createAction("bria_ai_settings", "Configure BriaAI Plugin", "Settings")
        action.triggered.connect(self.show_settings)
        self.actions.append(action)

        # Create actions for hotkeys only - not in menus
        # Note: These actions have no menu path, so they won't appear in any menu
        # but can still be assigned hotkeys in Settings → Configure Krita → Keyboard Shortcuts

        # Create the main script action
        main_action = window.createAction("bria_mask_tools", "Bria Mask Tools", "Tools/Scripts")
        main_action.triggered.connect(self.toggle_docker)
        self.actions.append(main_action)

    def show_settings(self):
        """Show the BriaAI settings dialog"""
        # Create a new settings dialog directly
        dialog = BriaAISettingsDialog(Krita.instance().activeWindow().qwindow())

        # Load current API key
        app = Krita.instance()
        api_key = app.readSetting("AGD_BriaAI", "api_key", "")
        dialog.set_api_key(api_key)

        # Show dialog and save if accepted
        if dialog.exec_() == QDialog.Accepted:
            new_key = dialog.get_api_key()
            app.writeSetting("AGD_BriaAI", "api_key", new_key)

    def find_docker(self):
        """Find the BackgroundRemover docker instance"""
        app = Krita.instance()
        # Try to find in all windows
        for window in app.windows():
            if window:
                dockers = window.dockers()
                for docker in dockers:
                    try:
                        # The docker widget might be wrapped, so we need to check carefully
                        if hasattr(docker, 'widget') and callable(docker.widget):
                            widget = docker.widget()
                            if isinstance(widget, BackgroundRemover):
                                return widget
                    except:
                        pass

        # Alternative method - check all QDockWidget instances
        for widget in QApplication.allWidgets():
            if isinstance(widget, BackgroundRemover):
                return widget

        return None

    # Removed execute_mode since we're not using hotkey actions anymore

    # Removed toggle_batch_mode since we're not using hotkey actions anymore

    def toggle_docker(self):
        """Toggle the visibility of the Bria Mask Tools docker"""
        app = Krita.instance()
        window = app.activeWindow()
        if window:
            # Try to find and toggle the docker
            dockers = window.dockers()
            for docker in dockers:
                if hasattr(docker, 'windowTitle') and callable(docker.windowTitle):
                    if docker.windowTitle() == "Bria Mask Tools":
                        docker.setVisible(not docker.isVisible())
                        return

            # If not found, show message
            QMessageBox.information(None, "Bria Mask Tools",
                                  "Please enable the docker first:\nSettings → Dockers → Bria Mask Tools")

# Add extension with error handling
try:
    extension = BackgroundRemoverExtension(Krita.instance())
    Krita.instance().addExtension(extension)
except Exception as e:
    import traceback
    # Log error to stderr instead of stdout
    sys.stderr.write(f"Failed to add extension: {e}\n")
    traceback.print_exc(file=sys.stderr)

def createInstance():
    return BackgroundRemover()

Krita.instance().addDockWidgetFactory(
    DockWidgetFactory("krita_bria_masktools",
                      DockWidgetFactoryBase.DockRight,
                      createInstance))
