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

import krita  # type: ignore
from krita import Krita, DockWidgetFactory, DockWidgetFactoryBase, InfoObject, Selection  # type: ignore
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLineEdit, QLabel, QDockWidget,
                             QApplication, QCheckBox, QSpinBox, QTextEdit, QProgressDialog,
                             QHBoxLayout, QMessageBox, QGroupBox, QRadioButton, QButtonGroup,
                             QDialog, QFormLayout, QDialogButtonBox, QComboBox, QSizePolicy, QScrollArea)
from PyQt5.QtGui import QImage, QClipboard, qRgb
from PyQt5.QtCore import QRect, Qt
from .mask_utils import prepare_mask_bytes, qimage_to_bytes, create_transparency_mask_from_qimage, create_selection_mask_from_qimage

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

class BriaMaskTools(QDockWidget):
    def __init__(self):
        try:
            super().__init__()
            self.setWindowTitle("Bria Mask Tools")

            widget = QWidget()
            # Main vertical layout with compact margins and spacing
            layout = QVBoxLayout()
            layout.setContentsMargins(5, 5, 5, 5)
            layout.setSpacing(5)
            widget.setLayout(layout)

            # Ensure the docker starts wide enough so group-box titles are not clipped
            widget.setMinimumWidth(260)
            widget.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)

            # Mode selection radio buttons
            mode_group = QGroupBox("Mode")
            # Prevent the mode group from expanding vertically
            mode_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            mode_layout = QHBoxLayout()
            mode_group.setLayout(mode_layout)

            # Compact margins around mode radio buttons
            mode_layout.setContentsMargins(10, 6, 10, 6)
            # Optional: adjust spacing between radio buttons
            mode_layout.setSpacing(10)

            self.mode_button_group = QButtonGroup()

            self.remove_bg_radio = QRadioButton("Remove Background")
            self.remove_bg_radio.setChecked(True)
            self.mode_button_group.addButton(self.remove_bg_radio, 0)
            mode_layout.addWidget(self.remove_bg_radio)

            self.generate_mask_radio = QRadioButton("Generate Masks")
            self.mode_button_group.addButton(self.generate_mask_radio, 1)
            mode_layout.addWidget(self.generate_mask_radio)

            layout.addWidget(mode_group)

            # Mask import mode selector moved here (under Mode group)
            self.mask_import_combo = QComboBox()
            self.mask_import_combo.addItems([
                "Selection masks (default)",
                "Transparency masks",
                "Separate layers"
            ])
            self.mask_import_combo.setCurrentIndex(0)
            self.mask_import_combo.setToolTip("Choose how downloaded masks should be imported into Krita")
            self.mask_import_combo.setVisible(False)
            self.mask_import_combo.currentIndexChanged.connect(self.update_add_to_new_layer_visibility)
            layout.addWidget(self.mask_import_combo)

            # Add to new layer checkbox
            self.add_to_new_layer_checkbox = QCheckBox("Add to new layer")
            self.add_to_new_layer_checkbox.setChecked(False)
            self.add_to_new_layer_checkbox.setToolTip("Add masks to a new blank layer instead of the original")
            self.add_to_new_layer_checkbox.setVisible(False)
            layout.addWidget(self.add_to_new_layer_checkbox)

            # Connect mode changes to update batch checkbox state
            self.mode_button_group.buttonClicked.connect(self.on_mode_changed)

            batch_layout = QHBoxLayout()
            # Compact batch-layout spacing
            batch_layout.setContentsMargins(0, 0, 0, 0)
            batch_layout.setSpacing(5)
            self.batch_checkbox = QCheckBox("Batch (selected layers)")
            self.batch_checkbox.stateChanged.connect(self.toggle_batch_mode)
            batch_layout.addWidget(self.batch_checkbox)

            # Advanced options
            self.advanced_checkbox = QCheckBox("Settings")
            self.advanced_checkbox.stateChanged.connect(self.toggle_advanced_options)
            batch_layout.addWidget(self.advanced_checkbox)

            layout.addLayout(batch_layout)

            self.advanced_group = QGroupBox("Settings")
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

            # Row for API Key and Debug Mode
            row_layout = QHBoxLayout()
            self.api_key_button = QPushButton("API Key")
            self.api_key_button.clicked.connect(self.show_settings_dialog)
            row_layout.addWidget(self.api_key_button)
            self.debug_checkbox = QCheckBox("Debug Mode")
            self.debug_checkbox.stateChanged.connect(self.toggle_debug_mode)
            row_layout.addWidget(self.debug_checkbox)
            advanced_layout.addLayout(row_layout)

            # Test mask buttons (visible in debug mode)
            test_layout = QHBoxLayout()
            self.test_transparency_button = QPushButton("Test Transparency Mask")
            self.test_transparency_button.clicked.connect(self.test_transparency_mask)
            test_layout.addWidget(self.test_transparency_button)

            self.test_selection_button = QPushButton("Test Selection Mask")
            self.test_selection_button.clicked.connect(self.test_selection_mask)
            test_layout.addWidget(self.test_selection_button)
            advanced_layout.addLayout(test_layout)

            layout.addWidget(self.advanced_group)

            button_layout = QHBoxLayout()
            # Compact button-layout spacing
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.setSpacing(5)
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
            # Hide status log unless debug mode is enabled
            self.status_label.setVisible(False)
            layout.addWidget(self.status_label)

            # Wrap the content in a scroll area to enable scrolling when the widget is taller than the viewport
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(widget)
            self.setWidget(scroll_area)

            # Add extra top padding to groupbox titles so the text isn't clipped
            try:
                content_widget = scroll_area.widget()
                if content_widget:
                    content_widget.setStyleSheet(
                        "QGroupBox::title {"
                        "subcontrol-origin: margin;"
                        "subcontrol-position: top left;"
                        "padding-top: 6px;"
                        "}"
                    )
            except Exception:
                pass

            # Load saved API key
            self.load_api_key()

            # Create menu action for settings
            self.create_settings_menu()
            # Initialize UI state based on current mode (after all controls are set up)
            self.on_mode_changed()

            # Register this widget with the current canvas to receive canvasChanged events
            try:
                window = Krita.instance().activeWindow()
                view = window.activeView() if window else None
                canvas = view.canvas() if view else None
                if canvas:
                    canvas.addObserver(self)
                    self._canvas = canvas
            except Exception:
                pass

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

        # Show or hide mask import selector based on mode
        self.mask_import_combo.setVisible(mode == 1)
        # Enable batch for all modes
        self.batch_checkbox.setEnabled(True)

        # Update action button label based on selected mode
        if hasattr(self, 'action_button'):
            if mode == 0:
                # Remove Background mode
                self.action_button.setText("Remove")
            else:
                # Generate Masks mode
                self.action_button.setText("Generate")

        self.update_add_to_new_layer_visibility()

    def update_add_to_new_layer_visibility(self):
        if self.generate_mask_radio.isChecked():
            idx = self.mask_import_combo.currentIndex()
            self.add_to_new_layer_checkbox.setVisible(idx == 0)
        else:
            self.add_to_new_layer_checkbox.setVisible(False)

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
        self.toggle_batch_mode()  # Update thread visibility

    def toggle_thread_count(self):
        self.thread_count_spinbox.setVisible(not self.auto_thread_checkbox.isChecked())

    def copy_status_text(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.status_label.toPlainText())  # type: ignore
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
        # Show test mask buttons only in debug and advanced mode
        self.test_transparency_button.setVisible(is_advanced and debug_mode)
        self.test_selection_button.setVisible(is_advanced and debug_mode)
        # Show or hide status log based on debug mode
        if hasattr(self, 'status_label'):
            self.status_label.setVisible(is_advanced and debug_mode)

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
        old_api_key = app.readSetting("BriaMaskToolsBriaAI", "api_key", "")
        if old_api_key:
            # If the old key is found, save it to the new setting and delete the old setting
            app.writeSetting("AGD_BriaAI", "api_key", old_api_key)
            app.writeSetting("BriaMaskToolsBriaAI", "api_key", "")  # Clear the old key
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
            self.api_key_status.setText("")  # type: ignore
            self.api_key_status.setStyleSheet("")  # type: ignore
        if hasattr(self, 'api_key_input'):
            self.api_key_input.setStyleSheet("")  # reset  # type: ignore

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
            mode_names = ["Remove Background", "Generate Masks"]
            mode_name = mode_names[mode]

            # Create a progress dialog
            try:
                progress = QProgressDialog(f"{mode_name}...", "Cancel", 0, 100,
                                          Krita.instance().activeWindow().qwindow())  # type: ignore
                progress.setWindowModality(Qt.WindowModal)  # type: ignore
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
            for button in [self.remove_bg_radio, self.generate_mask_radio]:
                button.setEnabled(False)
            self.mode_button_group.setExclusive(True)

            # Load API key from persistent settings
            self.load_api_key()

            # Ensure an API key has been configured
            if not self.api_key:
                progress.close()
                QMessageBox.warning(None, "Missing API Key", "Please set your API key under Settings.", QMessageBox.Ok)
                self.show_settings_dialog()
                self.enable_ui()
                return

            # Validate API key length
            if len(self.api_key) < 10:
                progress.close()
                QMessageBox.warning(None, "Invalid API Key", "The API key appears too short. Please check your Settings.", QMessageBox.Ok)
                self.show_settings_dialog()
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

            # Mode validation removed
            if False:  # Removed mode
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
                    if not result.startswith("Error"):
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
            except:
                pass

            # End timing the process
            end_time = time.time()

            # Calculate the total time taken in milliseconds
            total_time_ms = int((end_time - start_time) * 1000)

            # Final status update
            final_status = f"Completed. Processed {success_count}/{total_count} successfully. ({total_time_ms}ms)"
            if error_messages:
                final_status += f"\nErrors:\n" + "\n".join(error_messages)

            self.status_label.append(final_status)
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
        elif mode == 1:  # Generate Mask
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

                        # Convert image data to bytes safely
                        raw = qimage_to_bytes(image)
                        new_layer.setPixelData(raw, 0, 0, image.width(), image.height())

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
                                          Qt.KeepAspectRatio, Qt.SmoothTransformation)  # type: ignore

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

                            import_mode = self.get_selected_mask_import_mode()
                            node_type = {
                                "layers": "paintlayer",
                                "transparency": "transparencymask",
                                "selection": "selectionmask",
                            }[import_mode]

                            parent_node_for_masks = node
                            if import_mode == "selection" and self.add_to_new_layer_checkbox.isChecked():
                                new_layer = document.createNode("Generated Masks Layer", "paintlayer")
                                grandparent = node.parentNode()
                                if grandparent:
                                    grandparent.addChildNode(new_layer, node)
                                else:
                                    document.rootNode().addChildNode(new_layer, None)
                                parent_node_for_masks = new_layer

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
                                                if 'panoptic' in filename.lower():  # type: ignore
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

                                        # Iterate through list and create per-mask nodes
                                        for idx, (mask_file, filename) in enumerate(mask_files):
                                            # Extract mask number from filename if available
                                            mask_num = extract_number((mask_file, filename))
                                            if mask_num != 999:
                                                mask_name = f"Object Mask {mask_num}"
                                            else:
                                                mask_name = f"Mask {idx + 1}"

                                            mask_layer = document.createNode(mask_name, node_type)

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

                                                # Use helper functions for mask creation
                                                if node_type == "transparencymask":
                                                    # create and attach transparency mask
                                                    # remove placeholder layer and use helper
                                                    document.rootNode().removeChildNode(mask_layer)
                                                    mask_layer = create_transparency_mask_from_qimage(document, parent_node_for_masks, mask_name, mask_image)
                                                elif node_type == "selectionmask":
                                                    # remove placeholder layer and use helper
                                                    document.rootNode().removeChildNode(mask_layer)
                                                    mask_layer = create_selection_mask_from_qimage(document, parent_node_for_masks, mask_name, mask_image)
                                                else:
                                                    # paintlayer: scale to original layer size and prepare pixel data
                                                    lw = node.bounds().width()
                                                    lh = node.bounds().height()
                                                    mask_image = mask_image.scaled(
                                                        lw, lh,
                                                        Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # type: ignore
                                                    raw, w, h = prepare_mask_bytes(node_type, mask_image)
                                                    mask_layer.setPixelData(raw, 0, 0, w, h)

                                                # Add to document according to preference
                                                if import_mode == "layers":
                                                    parent = node.parentNode() or document.rootNode()
                                                    parent.addChildNode(mask_layer, node)
                                                else:
                                                    parent_node_for_masks.addChildNode(mask_layer, None)

                                                # Scale masks for separate layers mode
                                                if node_type == "paintlayer":
                                                    lw = node.bounds().width()
                                                    lh = node.bounds().height()
                                                    mask_image = mask_image.scaled(lw, lh,
                                                                          Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # type: ignore

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
                                        # Create single mask according to preference
                                        mask_name = "Generated Mask"
                                        mask_layer = document.createNode(mask_name, node_type)
                                        if mask_layer:
                                            # Use helpers for mask creation
                                            if node_type == "transparencymask":
                                                document.rootNode().removeChildNode(mask_layer)
                                                mask_layer = create_transparency_mask_from_qimage(document, parent_node_for_masks, mask_name, mask_image)
                                            elif node_type == "selectionmask":
                                                document.rootNode().removeChildNode(mask_layer)
                                                mask_layer = create_selection_mask_from_qimage(document, parent_node_for_masks, mask_name, mask_image)
                                            else:
                                                # paintlayer: scale to original layer size and prepare pixel data
                                                lw = node.bounds().width()
                                                lh = node.bounds().height()
                                                mask_image = mask_image.scaled(
                                                    lw, lh,
                                                    Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # type: ignore
                                                raw, w, h = prepare_mask_bytes(node_type, mask_image)
                                                mask_layer.setPixelData(raw, 0, 0, w, h)

                                            # Add to document according to preference
                                            if import_mode == "layers":
                                                parent = node.parentNode() or document.rootNode()
                                                parent.addChildNode(mask_layer, node)
                                            else:
                                                parent_node_for_masks.addChildNode(mask_layer, None)
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
                                # Iterate through list and create per-mask nodes
                                for idx, mask_url in enumerate(masks_list):
                                    if not mask_url or not isinstance(mask_url, str):
                                        continue
                                    mask_file = os.path.join(temp_dir, f"mask_{unique_id}_{idx}.png")
                                    try:
                                        urllib.request.urlretrieve(mask_url, mask_file)
                                    except Exception:
                                        continue

                                    # Create a mask node for each URL
                                    mask_name = f"Mask {idx + 1}"
                                    mask_layer = document.createNode(mask_name, node_type)
                                    if not mask_layer:
                                        continue

                                    # Load and scale mask image
                                    mask_image = QImage(mask_file)
                                    if mask_image.isNull():
                                        continue
                                    layer_width = node.bounds().width()
                                    layer_height = node.bounds().height()
                                    mask_image = mask_image.scaled(
                                        layer_width, layer_height,
                                        Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # type: ignore

                                    # Use helpers for mask creation
                                    if node_type == "transparencymask":
                                        document.rootNode().removeChildNode(mask_layer)
                                        mask_layer = create_transparency_mask_from_qimage(document, parent_node_for_masks, mask_name, mask_image)
                                    elif node_type == "selectionmask":
                                        document.rootNode().removeChildNode(mask_layer)
                                        mask_layer = create_selection_mask_from_qimage(document, parent_node_for_masks, mask_name, mask_image)
                                    else:
                                        # paintlayer: scale to original layer size and prepare pixel data
                                        lw = node.bounds().width()
                                        lh = node.bounds().height()
                                        mask_image = mask_image.scaled(
                                            lw, lh,
                                            Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # type: ignore
                                        raw, w, h = prepare_mask_bytes(node_type, mask_image)
                                        mask_layer.setPixelData(raw, 0, 0, w, h)

                                    # Add to document according to preference
                                    if import_mode == "layers":
                                        parent = node.parentNode() or document.rootNode()
                                        parent.addChildNode(mask_layer, node)
                                    else:
                                        parent_node_for_masks.addChildNode(mask_layer, None)

                                    # Scale masks for separate layers mode
                                    if node_type == "paintlayer":
                                        lw = node.bounds().width()
                                        lh = node.bounds().height()
                                        mask_image = mask_image.scaled(lw, lh,
                                                                      Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # type: ignore

                                    mask_count += 1
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
            self.api_key_status.setText("Invalid API Key - Please check and re-enter")  # type: ignore
            self.api_key_status.setStyleSheet("QLabel { color: red; font-weight: bold; }")  # type: ignore
        if hasattr(self, 'api_key_input'):
            self.api_key_input.setStyleSheet("QLineEdit { border: 2px solid red; }")  # type: ignore

    def enable_ui(self):
        """Re-enable all UI elements after processing"""
        self.action_button.setEnabled(True)
        self.batch_checkbox.setEnabled(True)
        for button in [self.remove_bg_radio, self.generate_mask_radio]:
            button.setEnabled(True)

    def canvasChanged(self, canvas):
        pass

    def showEvent(self, event):
        super().showEvent(event)
        # Register with current canvas when shown
        try:
            window = Krita.instance().activeWindow()
            view = window.activeView() if window else None
            canvas = view.canvas() if view else None
            if canvas:
                canvas.addObserver(self)
                self._canvas = canvas
        except Exception:
            pass

    def hideEvent(self, event):
        super().hideEvent(event)
        # Unregister from canvas when hidden
        try:
            if hasattr(self, '_canvas') and self._canvas:
                self._canvas.removeObserver(self)  # type: ignore
                self._canvas = None
        except Exception:
            pass

    # ------------------------------------------------------------
    # Helper: determine the desired mask import mode
    # ------------------------------------------------------------
    def get_selected_mask_import_mode(self):
        """Return one of 'selection', 'transparency', 'layers' depending on UI choice"""
        idx = 0
        try:
            idx = self.mask_import_combo.currentIndex()
        except Exception:
            pass  # Fallback if combo not yet initialised

        # 0 = Selection masks, 1 = Transparency masks, 2 = Layers
        if idx == 0:
            return "selection"
        elif idx == 1:
            return "transparency"
        else:
            return "layers"

    def test_transparency_mask(self):
        """Create a test 20x20 white transparency mask on the active layer."""
        app = Krita.instance()
        doc = app.activeDocument()
        if not doc:
            return
        node = doc.activeNode()
        if not node:
            return
        # Create a small white mask image
        img = QImage(20, 20, QImage.Format_Grayscale8)
        img.fill(255)
        create_transparency_mask_from_qimage(doc, node, "Test Transparency Mask", img)

    def test_selection_mask(self):
        """Create a test 20x20 selection mask on the active layer."""
        app = Krita.instance()
        doc = app.activeDocument()
        if not doc:
            return
        node = doc.activeNode()
        if not node:
            return
        # Create a small white mask image
        img = QImage(20, 20, QImage.Format_Grayscale8)
        img.fill(255)
        create_selection_mask_from_qimage(doc, node, "Test Selection Mask", img)

class BriaMaskToolsExtension(krita.Extension):

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
        """Find the BriaMaskTools docker instance"""
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
                            if isinstance(widget, BriaMaskTools):
                                return widget
                    except:
                        pass

        # Alternative method - check all QDockWidget instances
        for widget in QApplication.allWidgets():
            if isinstance(widget, BriaMaskTools):
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
    extension = BriaMaskToolsExtension(Krita.instance())
    Krita.instance().addExtension(extension)
except Exception as e:
    import traceback
    # Log error to stderr instead of stdout
    sys.stderr.write(f"Failed to add extension: {e}\n")
    traceback.print_exc(file=sys.stderr)

def createInstance():
    return BriaMaskTools()

Krita.instance().addDockWidgetFactory(
    DockWidgetFactory("krita_bria_masktools",
                      DockWidgetFactoryBase.DockRight,
                      createInstance))
