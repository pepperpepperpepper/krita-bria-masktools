# Krita Bria MaskTools

A comprehensive Krita plugin for AI-powered masking operations using BriaAI's API services.

## Features

### Three Powerful Modes:

1. **Remove Background** - Quick background removal using BriaAI's background removal API
2. **Remove Background with Mask** - Precise background removal using custom masks or selections
3. **Generate Mask** - AI-powered object detection and mask generation

## Key Features

- **Smart Mask Detection**: Automatically detects and uses:
  - Any mask type attached to your layer (transparency, filter, selection, etc.)
  - Active selections
  - Multiple selected layers (select both image and mask layers)
  - Any layer with "mask" in its name
- **Batch Processing**: Process multiple layers at once (available for Remove Background and Generate Mask modes)
- **Settings Dialog**: Secure API key storage via Krita's menu system
- **Advanced Options**: Control threading and enable debug mode
- **Robust Error Handling**: Automatic retry with clear error messages

## Installation

1. Download the plugin ZIP file
2. In Krita: Tools → Scripts → Import Python Plugin from File
3. Select the downloaded ZIP (do not extract)
4. Enable via Settings → Dockers → Krita Bria MaskTools

## Setup

1. Get your free API key from [bria.ai](https://bria.ai)
   - No credit card required for first 3 months
   - 1000 free operations per month
2. Configure your API key: Settings → Configure BriaAI Plugin
3. Enter your API key and click OK

## Usage

### Remove Background
1. Select a layer
2. Choose "Remove Background" mode
3. Click "Remove"
4. Result appears as new "Cutout" layer

### Remove Background with Mask
1. Provide a mask using one of these methods:
   - Create a selection with any selection tool, or
   - Add a mask to your layer (any mask type), or
   - Select two layers: your image and a mask layer, or
   - Create any layer with "mask" in its name
2. Choose "Remove Background with Mask" mode
3. Click "Remove"
4. Result appears as new "Masked" layer

### Generate Mask
1. Select a layer with objects
2. Choose "Generate Mask" mode
3. Click "Remove"
4. AI-generated masks appear as transparency masks on your layer

## Tips

- For best results, use images with clear subjects
- Fill transparent areas before background removal
- Use Image → Trim to Image Size for layers extending beyond canvas
- Enable batch mode to process multiple layers efficiently

## Attribution

This plugin is based on the original "Background Remover BriaAI" plugin by A. Gould.
- Original repository: [github.com/agoulddesign/krita-bg-remove-bria](https://github.com/agoulddesign/krita-bg-remove-bria)

## License

MIT License - See LICENSE file for details

## Compatibility

- Tested with Krita 5.2.2+
- Requires Python 3.6+
- Works on Windows, macOS, and Linux