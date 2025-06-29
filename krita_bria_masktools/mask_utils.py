from PyQt5.QtGui import QImage
from PyQt5.QtCore import Qt  # type: ignore
from krita import Selection  # type: ignore

# ------------------------------------------------------------
# Utility: convert QImage pixel buffer safely to Python bytes
# ------------------------------------------------------------

def qimage_to_bytes(img: QImage) -> bytes:
    """Return raw bytes of QImage pixel data."""
    bits = img.bits()
    bits.setsize(img.byteCount())  # type: ignore
    try:
        return bits.asstring(img.byteCount())  # type: ignore
    except AttributeError:
        return bytes(bits)  # type: ignore

def _strip_padding(img: QImage):
    """Strip scanline padding and return raw bytes of grayscale QImage."""
    width, height = img.width(), img.height()
    bpl = img.bytesPerLine()
    bits = img.bits()
    bits.setsize(img.byteCount())  # type: ignore
    raw = bits.asstring(img.byteCount())  # type: ignore
    data = bytearray(width * height)
    for y in range(height):
        start = y * bpl
        end = start + width
        data[y * width:(y + 1) * width] = raw[start:end]
    return bytes(data), width, height

# ------------------------------------------------------------
# Utility: prepare pixel data for different Krita node types
# ------------------------------------------------------------

def prepare_mask_bytes(node_type: str, img: QImage):
    """Return (bytes, width, height) formatted for Krita mask or layer nodes."""
    # Transparency mask expects 8-bit grayscale
    if node_type == "transparencymask":
        # Transparencymask expects strict 8-bit grayscale alpha, stripped of padding
        grayscale = img.convertToFormat(QImage.Format_Grayscale8)
        raw, w, h = _strip_padding(grayscale)
        return raw, w, h

    # Selection mask expects 8-bit grayscale indicating selection
    elif node_type == "selectionmask":
        # Selection masks require strict black/white 8-bit grayscale, stripped of padding
        grayscale = img.convertToFormat(QImage.Format_Grayscale8)
        raw_data, w, h = _strip_padding(grayscale)
        data = bytearray(raw_data)
        # Threshold to binary
        threshold = 128
        for i in range(len(data)):
            data[i] = 255 if data[i] >= threshold else 0
        return bytes(data), w, h

    # Paint layers expect ARGB32
    elif node_type == "paintlayer":
        # Paint layers expect ARGB32 format
        argb = img.convertToFormat(QImage.Format_ARGB32)
        raw = argb.bits().asstring(argb.byteCount())  # type: ignore
        return raw, argb.width(), argb.height()

    else:
        raise ValueError(f"Unsupported node type for mask_utils: {node_type}")

# ------------------------------------------------------------
# Create and attach a Krita mask node from a QImage
# ------------------------------------------------------------

def create_transparency_mask_from_qimage(document, parent_node, mask_name, img: QImage):
    """
    Create and attach a transparency mask node from a QImage.
    Returns the created mask node.
    """
    # Determine full document dimensions
    w, h = document.width(), document.height()
    # Scale input image to match document size
    scaled = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # type: ignore
    # Convert to 8-bit grayscale and strip padding
    gray = scaled.convertToFormat(QImage.Format_Grayscale8)
    raw, _, _ = _strip_padding(gray)

    # Create a true transparency mask via PyKrita API
    mask_node = document.createTransparencyMask(mask_name)

    # Attach and apply mask data
    parent_node.addChildNode(mask_node, None)
    mask_node.setPixelData(raw, 0, 0, w, h)

    # Start mask as invisible so users can toggle visibility via the eye icon
    try:
        mask_node.setVisible(False)
    except Exception:
        pass

    try:
        document.refreshProjection()
    except Exception:
        pass
    return mask_node

def create_selection_mask_from_qimage(document, parent_node, mask_name, img: QImage):
    """
    Create and attach a selection mask node from a QImage.
    Returns the created mask node.
    """
    # Determine full document dimensions
    w, h = document.width(), document.height()
    # Scale input image to full document size
    scaled = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # type: ignore
    # Convert to 8-bit grayscale and strip padding
    gray = scaled.convertToFormat(QImage.Format_Grayscale8)
    raw_data, _, _ = _strip_padding(gray)
    # Threshold to binary selection mask (white = selected)
    data = bytearray(raw_data)
    threshold = 128
    for i in range(len(data)):
        data[i] = 255 if data[i] >= threshold else 0

    # Create a true selection mask via PyKrita API
    try:
        mask_node = document.createSelectionMask(mask_name)
    except Exception:
        mask_node = document.createNode(mask_name, "selectionmask")

    # Initialize Krita Selection
    sel = Selection()
    sel.select(bytes(data), 0, 0, w, h)
    mask_node.setSelection(sel)
    parent_node.addChildNode(mask_node, None)

    # Start mask as invisible by default
    try:
        mask_node.setVisible(False)
    except Exception:
        pass

    try:
        document.refreshProjection()
    except Exception:
        pass
    return mask_node 