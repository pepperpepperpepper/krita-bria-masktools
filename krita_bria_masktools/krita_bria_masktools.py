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
from concurrent.futures import ThreadPoolExecutor, as_completed

import krita
from krita import Krita, DockWidgetFactory, DockWidgetFactoryBase, InfoObject
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLineEdit, QLabel, QDockWidget, QApplication, QCheckBox, QSpinBox, QTextEdit, QProgressDialog, QHBoxLayout, QMessageBox, QGroupBox, QRadioButton, QButtonGroup, QDialog, QFormLayout, QDialogButtonBox
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
            
            self.remove_bg_mask_radio = QRadioButton("Remove Background with Mask")
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

            layout.addWidget(self.advanced_group)

            button_layout = QHBoxLayout()
            
            # Temporarily disabled to debug
            # self.settings_button = QPushButton("Settings")
            # self.settings_button.clicked.connect(self.show_settings)
            # button_layout.addWidget(self.settings_button)
            
            self.remove_bg_button = QPushButton("Remove")
            self.remove_bg_button.clicked.connect(self.remove_background)
            button_layout.addWidget(self.remove_bg_button)

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
            QMessageBox.critical(None, "Error", f"Failed to initialize Bria Mask Tools:\n{str(e)}\n\n{traceback.format_exc()}")
            raise
    
    def create_settings_menu(self):
        """Create menu action for BriaAI settings"""
        pass  # Will be implemented in the Extension class
    
    def on_mode_changed(self):
        """Handle mode changes and update UI accordingly"""
        mode = self.mode_button_group.checkedId()
        
        # Update button text based on mode
        if mode == 2:  # Generate Mask mode
            self.remove_bg_button.setText("Generate Mask")
        else:
            self.remove_bg_button.setText("Remove")
        
        # Disable batch for Remove Background with Mask mode
        if mode == 1:  # Remove Background with Mask
            self.batch_checkbox.setChecked(False)
            self.batch_checkbox.setEnabled(False)
            self.status_label.setText("Batch processing is not supported when using manual masks or selections.")
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

    def detect_mask(self, document, node):
        """Detect mask from various sources in priority order"""
        # 1. Check for explicit transparency mask
        if node.childNodes():
            for child in node.childNodes():
                if child.type() == "transparencymask":
                    return child, "transparency_mask"
        
        # 2. Check for paint layer named 'Mask Layer'
        root = document.rootNode()
        for layer in root.childNodes():
            if layer.type() == "paintlayer" and layer.name().lower() == "mask layer":
                return layer, "mask_layer"
        
        # 3. Check for active selection
        selection = document.selection()
        if selection is not None:
            # Check if selection has valid dimensions
            if selection.width() > 0 and selection.height() > 0:
                return selection, "selection"
        
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
            # Debug output
            print("DEBUG: remove_background called")
            self.status_label.setText("DEBUG: Button clicked, starting process...")
            
            start_time = time.time()
            
            # Get selected mode
            mode = self.mode_button_group.checkedId()
            print(f"DEBUG: Selected mode: {mode}")
            mode_names = ["Remove Background", "Remove Background with Mask", "Generate Mask"]
            mode_name = mode_names[mode]

            # Create a progress dialog
            try:
                progress = QProgressDialog(f"{mode_name}...", "Cancel", 0, 100, Krita.instance().activeWindow().qwindow())
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(0)
                progress.setValue(0)
                progress.show()
            except Exception as e:
                print(f"DEBUG: Error creating progress dialog: {e}")
                self.status_label.setText(f"Error creating progress dialog: {e}")
                return

            # Clear the status_label field
            self.status_label.setText("Preparing file(s) and request(s)...")
            QApplication.processEvents()

            # Get API key from input field
            self.api_key = self.api_key_input.text().strip()
            
            # Check if API key is blank
            if self.api_key == "":
                self.status_label.setText("Error: API key is blank. Please enter your API key in the field above.")
                progress.close()
                return
            
            # Debug: Show API key length (not the key itself for security)
            self.status_label.append(f"Debug: API key length: {len(self.api_key)} characters")

            application = Krita.instance()
            document = application.activeDocument()
            window = application.activeWindow()

            if not document:
                self.status_label.setText("No active document")
                progress.close()
                return

            if not window:
                self.status_label.setText("No active window")
                progress.close()
                return

            view = window.activeView()
            if not view:
                self.status_label.setText("No active view")
                progress.close()
                return

            nodes = [document.activeNode()] if not self.batch_checkbox.isChecked() else view.selectedNodes()
            if not nodes:
                self.status_label.setText("No active layer or no layers selected")
                progress.close()
                return
            
            # For Remove Background with Mask mode, validate mask availability
            if mode == 1:  # Remove Background with Mask
                mask, mask_type = self.detect_mask(document, nodes[0])
                if not mask:
                    self.status_label.setText("Please create a selection or mask layer before proceeding.")
                    progress.close()
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
                    QApplication.processEvents()
                    
            try:
                context = ssl.create_default_context()
            except Exception as e:
                self.status_label.setText(f"Error creating SSL context: {str(e)}")
                progress.close()
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

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self.process_node, node, self.api_key, document, context, mode) for node in nodes]

                for future in as_completed(futures):
                    try:
                        result = future.result()
                        processed_count += 1
                        if "successfully" in result.lower():
                            success_count += 1
                        else:
                            error_messages.append(result)
                        self.status_label.append(f"Processed {processed_count}/{total_count}: {result}")
                        progress.setValue(10 + int(90 * processed_count / total_count))
                    except Exception as e:
                        processed_count += 1
                        error_messages.append(f"Error: {str(e)}")
                    finally:
                        QApplication.processEvents()

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
        except Exception as e:
            import traceback
            error_msg = f"ERROR in remove_background: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.status_label.setText(error_msg)
            try:
                progress.close()
            except:
                pass

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
            node_bounds = node.bounds()
            if not node_bounds or node_bounds.width() <= 0 or node_bounds.height() <= 0:
                return "Error: Invalid layer bounds"
            
            if not node.save(temp_file, 1.0, 1.0, export_params, node_bounds):
                return "Error: Failed to export image for processing"
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
                'api_token': api_key
            }
            req = urllib.request.Request(url, data=body, headers=headers, method='POST')
            
            with urllib.request.urlopen(req, timeout=30, context=context) as response:
                if response.status == 200:
                    # Parse the JSON response
                    try:
                        response_data = json.loads(response.read().decode('utf-8'))
                    except json.JSONDecodeError:
                        return "Error: Invalid JSON response from server"
                    
                    result_url = response_data.get('result_url')
                    
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

                        if original_color_space != "RGBA":
                            # Create a new document with the downloaded image
                            app = Krita.instance()
                            temp_doc = None
                            try:
                                temp_doc = app.createDocument(0, 0, "temp_doc", "RGBA", "U8", "", 300.0)
                                if not temp_doc:
                                    return "Error: Failed to create temporary document"
                                    
                                temp_layer = temp_doc.createNode("temp_layer", "paintlayer")
                                if not temp_layer:
                                    return "Error: Failed to create temporary layer"
                                    
                                temp_doc.rootNode().addChildNode(temp_layer, None)
                                
                                # Load the image into the layer
                                image = QImage(result_file)
                                if image.isNull():
                                    return "Error: Failed to load result image"
                                
                                # Convert image data to bytes
                                ptr = image.constBits()
                                ptr.setsize(image.byteCount())
                                temp_layer.setPixelData(bytes(ptr), 0, 0, image.width(), image.height())

                                # Convert the temporary document to the original color space
                                temp_doc.setColorSpace(original_color_space, document.colorDepth(), document.colorProfile())
                                temp_doc.refreshProjection()

                                # Copy the layer to the original document
                                copied_layer = temp_layer.clone()
                                if not copied_layer:
                                    return "Error: Failed to clone layer"
                                    
                                document.rootNode().addChildNode(copied_layer, node)
                                copied_layer.setName(new_layer_name)
                            finally:
                                # Always close the temporary document
                                if temp_doc:
                                    try:
                                        temp_doc.close()
                                    except Exception:
                                        pass

                            result = f"Background removed successfully for {node.name()} (Converted to {original_color_space}, please note that colors may not look like the original image)"
                        else:
                            # For RGBA documents, directly create a new layer with the image
                            new_layer = document.createNode(new_layer_name, "paintlayer")
                            if not new_layer:
                                return "Error: Failed to create new layer"
                            
                            # Load the image into the layer
                            image = QImage(result_file)
                            if image.isNull():
                                return "Error: Failed to load result image"
                            
                            # Validate image dimensions
                            if image.width() <= 0 or image.height() <= 0:
                                return "Error: Invalid image dimensions"
                            
                            # Convert image data to bytes
                            ptr = image.constBits()
                            ptr.setsize(image.byteCount())
                            new_layer.setPixelData(bytes(ptr), 0, 0, image.width(), image.height())
                            
                            document.rootNode().addChildNode(new_layer, node)
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
            except:
                pass
            return f"{self.handle_error(e.code)} - Details: {error_body}"
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                return "SSL Certificate verification failed. You may need to update your certificates."
            else:
                return f"URLError: {str(e)}"
        except json.JSONDecodeError:
            return "Error: Invalid JSON response"
        except Exception as e:
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
            return "Error: No mask detected. Please create a selection or mask layer."
        
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
                if not node.save(temp_image_file, 1.0, 1.0, export_params, node.bounds()):
                    return "Error: Failed to export image for processing"
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
                    if not mask.save(temp_mask_file, 1.0, 1.0, export_params, mask.bounds()):
                        return "Error: Failed to export mask for processing"
                except Exception as e:
                    return f"Error exporting mask: {str(e)}"
            
            # Prepare API request for /eraser endpoint
            url = "https://engine.prod.bria-api.com/v1/eraser"
            
            # Prepare multipart form data
            boundary = 'wL36Yn8afVp8Ag7AmP8qZ0SA4n1v9T'
            data = []
            
            # Add image file
            data.append(f'--{boundary}'.encode())
            data.append(b'Content-Disposition: form-data; name="file"; filename="image.png"')
            data.append(b'Content-Type: image/png')
            data.append(b'')
            with open(temp_image_file, 'rb') as f:
                data.append(f.read())
            
            # Add mask file
            data.append(f'--{boundary}'.encode())
            data.append(b'Content-Disposition: form-data; name="mask"; filename="mask.png"')
            data.append(b'Content-Type: image/png')
            data.append(b'')
            with open(temp_mask_file, 'rb') as f:
                data.append(f.read())
            
            data.append(f'--{boundary}--'.encode())
            data.append(b'')
            body = b'\r\n'.join(data)
            
            # Create and send request with retry
            headers = {
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'api_token': api_key
            }
            
            for attempt in range(2):  # Try twice
                try:
                    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
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
                                
                                # Create new layer
                                new_layer = document.createNode("Masked", "paintlayer")
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
                                
                                return f"Masked background removed successfully for {node.name()}"
                            else:
                                return "Error: No result URL in response"
                        else:
                            return self.handle_error(response.status)
                        
                except urllib.error.HTTPError as e:
                    if attempt == 0:  # First attempt failed, retry
                        time.sleep(1)
                        continue
                    return self.handle_error(e.code)
                except Exception as e:
                    if attempt == 0:
                        time.sleep(1)
                        continue
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
                if not node.save(temp_file, 1.0, 1.0, export_params, node.bounds()):
                    return "Error: Failed to export image for processing"
            except Exception as e:
                return f"Error exporting image: {str(e)}"
            
            # Prepare API request
            url = "https://engine.prod.bria-api.com/v1/mask_generator"
            
            # Prepare multipart form data
            boundary = 'wL36Yn8afVp8Ag7AmP8qZ0SA4n1v9T'
            data = []
            data.append(f'--{boundary}'.encode())
            data.append(b'Content-Disposition: form-data; name="file"; filename="image.jpg"')
            data.append(b'Content-Type: image/jpeg')
            data.append(b'')
            with open(temp_file, 'rb') as f:
                data.append(f.read())
            data.append(f'--{boundary}--'.encode())
            data.append(b'')
            body = b'\r\n'.join(data)
            
            headers = {
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'api_token': api_key
            }
            
            # Send request with retry
            for attempt in range(2):
                try:
                    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
                    with urllib.request.urlopen(req, timeout=30, context=context) as response:
                        if response.status == 200:
                            try:
                                response_data = json.loads(response.read().decode('utf-8'))
                            except json.JSONDecodeError:
                                return "Error: Invalid JSON response from server"
                            
                            masks = response_data.get('masks', [])
                            
                            if masks and isinstance(masks, list):
                                mask_count = 0
                                
                                for idx, mask_url in enumerate(masks):
                                    # Validate mask URL
                                    if not mask_url or not isinstance(mask_url, str):
                                        continue
                                        
                                    # Download mask
                                    mask_file = os.path.join(temp_dir, f"mask_{unique_id}_{idx}.png")
                                    try:
                                        urllib.request.urlretrieve(mask_url, mask_file)
                                    except Exception as e:
                                        # Skip this mask if download fails
                                        continue
                                    
                                    # Create transparency mask
                                    mask_name = f"Mask {idx + 1}"
                                    mask_layer = document.createNode(mask_name, "transparencymask")
                                    if not mask_layer:
                                        continue  # Skip if layer creation fails
                                    
                                    # Load mask image
                                    mask_image = QImage(mask_file)
                                    if not mask_image.isNull():
                                        # Convert image data to bytes
                                        ptr = mask_image.constBits()
                                        ptr.setsize(mask_image.byteCount())
                                        mask_layer.setPixelData(bytes(ptr), 0, 0, mask_image.width(), mask_image.height())
                                        
                                        # Add as child of the node only if image loaded successfully
                                        node.addChildNode(mask_layer, None)
                                        mask_count += 1
                                    
                                    # Cleanup
                                    if not self.debug_checkbox.isChecked():
                                        try:
                                            os.remove(mask_file)
                                        except Exception:
                                            pass
                                
                                try:
                                    document.refreshProjection()
                                except Exception:
                                    pass  # Non-critical if refresh fails
                                return f"Generated {mask_count} masks for {node.name()}"
                            else:
                                return "Error: No masks generated"
                        else:
                            return self.handle_error(response.status)
                            
                except urllib.error.HTTPError as e:
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    return self.handle_error(e.code)
                except Exception as e:
                    if attempt == 0:
                        time.sleep(1)
                        continue
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
        return f"Error {status_code}: {error_messages.get(status_code, 'Unknown error. Please check your connection and try again.')}"

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
    print(f"Failed to add extension: {e}")
    traceback.print_exc()

def createInstance():
    return BackgroundRemover()

Krita.instance().addDockWidgetFactory(
    DockWidgetFactory("krita_bria_masktools",
                      DockWidgetFactoryBase.DockRight,
                      createInstance))
