#!/usr/bin/env python3
from PyQt5.QtGui import QImage
from PyQt5.QtCore import QCoreApplication
import sys

app = QCoreApplication(sys.argv)

# Test loading one of the mask files
test_file = "extracted_masks/9465f403-2855-43eb-bb4d-b0c2385bdd83/9465f403-2855-43eb-bb4d-b0c2385bdd83_1.png"

print(f"Testing QImage loading of: {test_file}")

img = QImage(test_file)
if img.isNull():
    print("ERROR: QImage failed to load the file")
else:
    print(f"SUCCESS: Image loaded, size: {img.width()}x{img.height()}, format: {img.format()}")
    
# Also test file header
with open(test_file, 'rb') as f:
    header = f.read(16)
    print(f"File header: {header[:8].hex()}")
    if header.startswith(b'\x89PNG'):
        print("This is a valid PNG file")