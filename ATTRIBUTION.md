# Attribution

Krita Bria MaskTools is based on the original "Krita Background Remover BriaAI" plugin by A. Gould.

## Original Project
- **Name**: krita-bg-remove-bria
- **Author**: A. Gould (agoulddesign@gmail.com)
- **Repository**: https://github.com/agoulddesign/krita-bg-remove-bria
- **License**: MIT

## What's New in Krita Bria MaskTools

This project extends the original background removal functionality into a comprehensive masking toolkit:

### New Features
- Support for BriaAI's mask generation API endpoint
- Support for BriaAI's eraser API endpoint (background removal with custom masks)
- Three distinct operational modes with radio button selection
- Intelligent mask detection system (transparency masks, paint layers, selections)
- Dedicated settings dialog for API key management
- Enhanced batch processing capabilities
- Comprehensive error handling with automatic retry
- Memory-efficient processing for large images

### Technical Improvements
- Refactored codebase for maintainability
- Thread-safe operations with UUID-based file naming
- Proper resource cleanup and memory management
- Extensive input validation and bounds checking
- Support for various color spaces and formats

## License Compliance
This project is released under the MIT License, maintaining compatibility with the original project's licensing terms.
