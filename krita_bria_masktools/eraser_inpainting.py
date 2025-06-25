"""
Eraser/Inpainting functionality for Bria Mask Tools
This module contains the masked removal (inpainting) logic that was removed from the main plugin.
"""

import os
import sys
import json
import tempfile
import urllib.request
import uuid
import base64
from PyQt5.QtGui import QImage, qRgb
from PyQt5.QtCore import Qt
from krita import InfoObject


def process_masked_removal(node, api_key, document, context, mask, mask_type, 
                          preserve_alpha=True, prompt_text="", debug_callback=None):
    """
    Process background removal with mask using /erase_foreground endpoint
    
    Args:
        node: The Krita node to process
        api_key: BriaAI API key
        document: Krita document
        context: SSL context
        mask: The detected mask
        mask_type: Type of mask ("selection", "mask", etc.)
        preserve_alpha: Whether to preserve alpha channel
        prompt_text: Optional prompt to guide the inpainting
        debug_callback: Optional callback function for debug messages
    
    Returns:
        Error message string on failure, or (new_layer, success_message) tuple on success
    """
    
    def log_debug(message):
        if debug_callback:
            debug_callback(message)
    
    # Log mask detection
    log_debug(f"Detected mask type: {mask_type}")
    if hasattr(mask, 'name'):
        log_debug(f"Mask name: {mask.name()}")
    if hasattr(mask, 'bounds'):
        bounds = mask.bounds()
        log_debug(f"Mask bounds: {bounds.x()}, {bounds.y()}, {bounds.width()}, {bounds.height()}")

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
            # Log export attempt
            log_debug(f"Exporting image to: {temp_image_file}")
            bounds = node.bounds()
            log_debug(f"Node bounds: {bounds.x()}, {bounds.y()}, {bounds.width()}, {bounds.height()}")

            # Simply save without checking return value like the original
            node.save(temp_image_file, 1.0, 1.0, export_params, node.bounds())

            # Verify file was created
            if not os.path.exists(temp_image_file):
                return "Error: Export file was not created"

            file_size = os.path.getsize(temp_image_file)
            if file_size == 0:
                return "Error: Export file is empty"

            log_debug(f"Export successful, file size: {file_size} bytes")

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

            log_debug(f"Encoded image size: {len(encoded_image)} bytes")
            log_debug(f"Encoded mask size: {len(encoded_mask)} bytes")
        except Exception as e:
            return f"Error encoding files: {str(e)}"

        # Prepare JSON request
        request_data = {
            "file": encoded_image,
            "mask_file": encoded_mask,
            "mask_type": "manual",
            "sync": True,
            "preserve_alpha": preserve_alpha,
            "content_moderation": False
        }

        # Add prompt if provided
        if prompt_text:
            request_data["prompt"] = prompt_text
            log_debug(f"Using prompt: {prompt_text}")

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

                # Log request details
                log_debug(f"Masked removal request URL: {url}")
                log_debug(f"Request headers: {headers}")
                log_debug(f"Image file size: {os.path.getsize(temp_image_file)} bytes")
                log_debug(f"Mask file size: {os.path.getsize(temp_mask_file)} bytes")

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
                            layer_name = "Erased Fill"
                            if prompt_text:
                                # Include prompt in layer name if it's short enough
                                if len(prompt_text) <= 20:
                                    layer_name = f"Erased Fill ({prompt_text})"
                                else:
                                    layer_name = f"Erased Fill ({prompt_text[:17]}...)"
                            
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

                            # Clean up temp files
                            for f in [temp_image_file, temp_mask_file, result_file]:
                                if f and os.path.exists(f):
                                    try:
                                        os.remove(f)
                                    except:
                                        pass

                            # Return success with the new layer
                            result_msg = f"Eraser completed successfully for {node.name()}"
                            if prompt_text:
                                result_msg += f" with prompt: {prompt_text}"
                            
                            return (new_layer, result_msg)
                        else:
                            return "Error: No result URL in response"
                    else:
                        error_body = response.read().decode('utf-8')
                        return f"HTTP error {response.status}: {error_body}"
                        
            except urllib.error.HTTPError as e:
                error_msg = f"HTTP Error {e.code}: {e.reason}"
                if hasattr(e, 'read'):
                    try:
                        error_detail = e.read().decode('utf-8')
                        log_debug(f"Error details: {error_detail}")
                        error_msg += f"\nDetails: {error_detail}"
                    except:
                        pass
                
                if e.code == 422 and attempt == 0:
                    log_debug("Retrying due to 422 error...")
                    continue
                return error_msg
            except Exception as e:
                return f"Request error: {str(e)}"

        return "Error: Failed after retry attempts"

    finally:
        # Clean up temp files
        for f in [temp_image_file, temp_mask_file]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass