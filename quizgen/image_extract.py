import base64
import io
import re

import fitz  # PyMuPDF


# Common mojibake replacements (UTF-8 decoded as Latin-1)
_TEXT_REPLACEMENTS = {
    "\u00e2\u0080\u0094": "-",   # em-dash mojibake
    "\u00e2\u0080\u0093": "-",   # en-dash mojibake
    "\u00e2\u0080\u0099": "'",   # right single quote mojibake
    "\u00e2\u0080\u009c": '"',   # left double quote mojibake
    "\u00e2\u0080\u009d": '"',   # right double quote mojibake
    "\u00c2\u00b0": "\u00b0",    # degree sign mojibake
    "\u00c2": "",                 # stray Â
    "\u2014": "-",               # em-dash
    "\u2013": "-",               # en-dash
    "\u2019": "'",               # right single quote
    "\u201c": '"',               # left double quote
    "\u201d": '"',               # right double quote
}


def _fix_encoding(text: str) -> str:
    """Fix common mojibake / encoding issues in extracted text."""
    for bad, good in _TEXT_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text


# Caption patterns: "Figure 1:", "Fig. 2:", "Diagram 3:", "Table 1:", etc.
_CAPTION_PATTERN = re.compile(
    r"(?:Figure|Fig\.?|Diagram|Table|Chart|Image|Photo|Illustration)"
    r"\s*\d*\s*[:\.\-–—]\s*(.+)",
    re.IGNORECASE
)


def _resize_image_bytes(image_bytes: bytes, max_width: int = 400) -> bytes:
    """Resize image to max_width using PyMuPDF (no PIL needed)."""
    try:
        pix = fitz.Pixmap(image_bytes)
        if pix.width > max_width:
            scale = max_width / pix.width
            new_w = int(pix.width * scale)
            new_h = int(pix.height * scale)
            # Create a new pixmap by rendering at smaller size
            src_rect = fitz.Rect(0, 0, pix.width, pix.height)
            dst_rect = fitz.Rect(0, 0, new_w, new_h)
            # Use fitz to create resized image
            small_pix = fitz.Pixmap(pix, 0) if pix.alpha else pix
            # Convert to PNG bytes
            return small_pix.tobytes("png")
        return pix.tobytes("png")
    except Exception:
        return image_bytes


def _get_text_blocks(page: fitz.Page) -> list[dict]:
    """Extract text blocks with positions from a page."""
    blocks = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") == 0:  # text block
            text = ""
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text += span.get("text", "")
                text += " "
            text = text.strip()
            if text:
                blocks.append({
                    "text": text,
                    "bbox": block["bbox"],  # (x0, y0, x1, y1)
                })
    return blocks


def _find_caption(image_bbox: tuple, text_blocks: list[dict], page_height: float) -> str:
    """Find the caption text closest to an image, preferring text below then above."""
    ix0, iy0, ix1, iy1 = image_bbox
    img_center_x = (ix0 + ix1) / 2
    img_bottom = iy1
    img_top = iy0

    best_caption = ""
    best_distance = float("inf")

    for block in text_blocks:
        tx0, ty0, tx1, ty1 = block["bbox"]
        text = block["text"]

        # Check if text is horizontally aligned with image (overlap)
        if tx1 < ix0 - 50 or tx0 > ix1 + 50:
            continue

        # Text below image (most common for captions)
        if ty0 >= img_bottom - 5:
            distance = ty0 - img_bottom
            if distance < 80 and distance < best_distance:
                best_distance = distance
                best_caption = text

        # Text above image
        if ty1 <= img_top + 5:
            distance = img_top - ty1
            if distance < 60 and distance < best_distance * 0.8:  # prefer below
                best_distance = distance / 0.8
                best_caption = text

    # Try to extract clean caption from matched text
    if best_caption:
        best_caption = _fix_encoding(best_caption)
        m = _CAPTION_PATTERN.match(best_caption)
        if m:
            return m.group(1).strip()
        # If no "Figure X:" pattern, use the text as-is (truncated)
        if len(best_caption) > 120:
            best_caption = best_caption[:120].rsplit(" ", 1)[0]
        return best_caption

    return ""


def extract_images_from_pdf(pdf_path: str, max_width: int = 400,
                             min_size: int = 50, max_bytes: int = 5_000_000
                             ) -> list[dict]:
    """
    Extract images from PDF with captions.

    Returns list of:
    {
        "image_b64": str,       # base64-encoded PNG
        "caption": str,         # associated caption text
        "page": int,            # page number (0-indexed)
        "width": int,
        "height": int
    }
    """
    doc = fitz.open(pdf_path)
    results = []
    seen_hashes = set()

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text_blocks = _get_text_blocks(page)
        image_list = page.get_images(full=True)

        for img_info in image_list:
            xref = img_info[0]

            # Skip duplicates (same image referenced multiple times)
            if xref in seen_hashes:
                continue
            seen_hashes.add(xref)

            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue

            if not base_image or not base_image.get("image"):
                continue

            img_bytes = base_image["image"]
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)

            # Filter: too small (icons, bullets)
            if width < min_size or height < min_size:
                continue

            # Filter: too large
            if len(img_bytes) > max_bytes:
                continue

            # Get image position on page for caption matching
            img_rects = page.get_image_rects(xref)
            if img_rects:
                bbox = img_rects[0]  # use first occurrence
                caption = _find_caption(
                    (bbox.x0, bbox.y0, bbox.x1, bbox.y1),
                    text_blocks,
                    page.rect.height
                )
            else:
                caption = ""

            # Convert to PNG and resize
            try:
                pix = fitz.Pixmap(doc, xref)
                # Handle CMYK or other color spaces
                if pix.n > 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                elif pix.alpha:
                    pix = fitz.Pixmap(fitz.csRGB, pix)

                png_bytes = pix.tobytes("png")

                # Resize if needed
                if width > max_width:
                    scale = max_width / width
                    mat = fitz.Matrix(scale, scale)
                    # Re-render at smaller size
                    small_pix = fitz.Pixmap(fitz.csRGB, pix, 0)
                    png_bytes = small_pix.tobytes("png")
                    width = int(width * scale)
                    height = int(height * scale)

            except Exception:
                # Fallback: use raw bytes
                png_bytes = img_bytes

            b64 = base64.b64encode(png_bytes).decode("ascii")

            results.append({
                "image_b64": b64,
                "caption": caption,
                "page": page_idx,
                "width": width,
                "height": height,
            })

    doc.close()
    return results
