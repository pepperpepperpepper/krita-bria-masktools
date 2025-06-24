#!/usr/bin/env python3
import os
import base64
import json
import urllib.request
import urllib.error
import zipfile
import tempfile

# API configuration
API_KEY = "eedc6ae49dc34a00be2c4ef34615d35f"
API_URL = "https://engine.prod.bria-api.com/v1/objects/mask_generator"

# Read and encode the image
with open("test_image.png", "rb") as f:
    file_data = f.read()
    encoded_file = base64.b64encode(file_data).decode('utf-8')
    
# Check the input image size
from PIL import Image
input_img = Image.open("test_image.png")
print(f"Input image size: {input_img.size}")
print(f"Input image mode: {input_img.mode}")

# Prepare request
request_data = {
    "file": encoded_file,
    "content_moderation": False,
    "sync": True
}

# Convert to JSON
json_data = json.dumps(request_data).encode('utf-8')

# Create request
headers = {
    'Content-Type': 'application/json',
    'api_token': API_KEY
}

req = urllib.request.Request(API_URL, data=json_data, headers=headers, method='POST')

try:
    print("Sending request to mask generator API...")
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status == 200:
            result = json.loads(response.read().decode('utf-8'))
            print(f"Response: {json.dumps(result, indent=2)}")
            
            # Check what we got back
            if 'objects_masks' in result:
                masks = result['objects_masks']
                if isinstance(masks, str):
                    print(f"\nGot single mask URL: {masks}")
                    
                    # Download and check if it's a ZIP
                    download_file = "downloaded_mask.bin"
                    urllib.request.urlretrieve(masks, download_file)
                    
                    # Check if it's a ZIP file
                    try:
                        with zipfile.ZipFile(download_file, 'r') as zip_ref:
                            print(f"\nIt's a ZIP file containing: {zip_ref.namelist()}")
                            
                            # Extract and examine contents
                            extract_dir = "extracted_masks"
                            os.makedirs(extract_dir, exist_ok=True)
                            zip_ref.extractall(extract_dir)
                            
                            # Walk through extracted files
                            print("\nExtracted files:")
                            for root, dirs, files in os.walk(extract_dir):
                                for file in files:
                                    filepath = os.path.join(root, file)
                                    rel_path = os.path.relpath(filepath, extract_dir)
                                    size = os.path.getsize(filepath)
                                    print(f"  {rel_path} ({size} bytes)")
                                    
                                    # Check one of the mask files
                                    if file.endswith('_1.png'):
                                        from PIL import Image
                                        img = Image.open(filepath)
                                        print(f"    Image mode: {img.mode}, size: {img.size}")
                                        print(f"    Format: {img.format}, bits: {img.bits}")
                                        # Check pixel data
                                        pixels = list(img.getdata())
                                        print(f"    First 10 pixels: {pixels[:10]}")
                                        print(f"    Unique values: {len(set(pixels))}")
                                    
                    except zipfile.BadZipFile:
                        print("\nNot a ZIP file, checking if it's an image...")
                        # Try to identify file type
                        with open(download_file, 'rb') as f:
                            header = f.read(16)
                            print(f"File header: {header[:8].hex()}")
                
                elif isinstance(masks, list):
                    print(f"\nGot list of {len(masks)} mask URLs")
                    for i, mask_url in enumerate(masks):
                        print(f"  Mask {i}: {mask_url}")
            else:
                print("\nNo 'masks' field in response")
        else:
            print(f"Error: HTTP {response.status}")
            
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.reason}")
    if e.code == 422:
        error_data = e.read().decode('utf-8')
        print(f"Error details: {error_data}")
except Exception as e:
    print(f"Error: {e}")