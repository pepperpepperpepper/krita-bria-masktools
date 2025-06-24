#!/bin/bash

# Quick install script for Krita Bria Mask Tools

echo "Installing Krita Bria Mask Tools..."

# Create temp directory
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"

# Clone the repository
echo "Downloading from GitHub..."
git clone https://github.com/pepperpepperpepper/krita-bria-masktools.git

# Create Krita pykrita directory if it doesn't exist
mkdir -p ~/.local/share/krita/pykrita/

# Remove old installation if exists
rm -rf ~/.local/share/krita/pykrita/krita_bria_masktools*

# Copy files to Krita
echo "Installing to Krita..."
cp -r krita-bria-masktools/krita_bria_masktools* ~/.local/share/krita/pykrita/

# Clean up
cd ..
rm -rf "$TEMP_DIR"

echo "Installation complete!"
echo "Please restart Krita and enable the plugin in:"
echo "  - Settings → Dockers → Bria Mask Tools"
echo "  - Tools → Scripts → Bria Mask Tools"