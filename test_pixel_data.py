#!/usr/bin/env python3
"""Test to understand Krita's pixel data requirements"""

from PIL import Image
import os

# Load one of the mask files
mask_path = "extracted_masks/02d78a35-8680-455b-a43f-101ebb5e57b8/02d78a35-8680-455b-a43f-101ebb5e57b8_1.png"
if os.path.exists(mask_path):
    img = Image.open(mask_path)
    print(f"Mask properties:")
    print(f"  Mode: {img.mode}")
    print(f"  Size: {img.size}")
    print(f"  Format: {img.format}")
    
    # Get raw pixel data
    pixels = img.tobytes()
    print(f"\nPixel data:")
    print(f"  Total bytes: {len(pixels)}")
    print(f"  Expected (width*height*channels): {img.width * img.height * 1}")
    print(f"  First 10 bytes: {list(pixels[:10])}")
    
    # For Krita, we need to understand:
    # 1. The mask is 800x800 but the layer might be 1080x1920
    # 2. The mask is grayscale (1 byte per pixel)
    # 3. Krita expects RGBA data (4 bytes per pixel) for paint layers
    # 4. For transparency masks, it might expect different format
    
    print(f"\nFor a 1080x1920 RGBA layer:")
    print(f"  Expected bytes: {1080 * 1920 * 4} (RGBA)")
    print(f"  Expected bytes: {1080 * 1920 * 1} (Grayscale)")
    
    # The error "not enough data" suggests we're providing 800x800 data
    # for a 1080x1920 layer
else:
    print(f"Mask file not found: {mask_path}")
    print("Available files:")
    for root, dirs, files in os.walk("extracted_masks"):
        for file in files:
            if file.endswith(".png"):
                print(f"  {os.path.join(root, file)}")