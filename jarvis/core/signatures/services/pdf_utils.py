"""PDF utilities for digital signatures — embed signature image + hash."""
import base64
import hashlib
import io
import logging
import os

from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import NameObject, ArrayObject, FloatObject

logger = logging.getLogger('jarvis.core.signatures.pdf_utils')


def embed_signature_image(original_pdf_path, base64_image, output_path):
    """Embed a signature image on the last page of a PDF (bottom-right).

    Args:
        original_pdf_path: Path to the original PDF file.
        base64_image: Base64-encoded PNG signature image.
        output_path: Path to write the signed PDF.

    Returns:
        output_path on success.

    Raises:
        FileNotFoundError: If original PDF doesn't exist.
        ValueError: If base64_image is invalid.
    """
    if not os.path.exists(original_pdf_path):
        raise FileNotFoundError(f'PDF not found: {original_pdf_path}')

    # Decode signature image
    try:
        img_data = base64.b64decode(base64_image.split(',')[-1])
    except Exception as e:
        raise ValueError(f'Invalid base64 image: {e}')

    sig_img = Image.open(io.BytesIO(img_data))
    if sig_img.mode != 'RGBA':
        sig_img = sig_img.convert('RGBA')

    # Scale signature to reasonable size (max 200x80 points)
    max_w, max_h = 200, 80
    w, h = sig_img.size
    scale = min(max_w / w, max_h / h, 1.0)
    sig_w = int(w * scale)
    sig_h = int(h * scale)
    if scale < 1.0:
        sig_img = sig_img.resize((sig_w, sig_h), Image.LANCZOS)

    reader = PdfReader(original_pdf_path)
    writer = PdfWriter()

    # Copy all pages
    for page in reader.pages:
        writer.add_page(page)

    # Get last page dimensions
    last_page = writer.pages[-1]
    page_w = float(last_page.mediabox.width)
    page_h = float(last_page.mediabox.height)

    # Create a small PDF with just the signature image using ReportLab-free approach
    # We'll create an XObject image and add it to the last page
    sig_pdf_buffer = _create_sig_overlay(sig_img, sig_w, sig_h, page_w, page_h)

    sig_reader = PdfReader(sig_pdf_buffer)
    last_page.merge_page(sig_reader.pages[0])

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f:
        writer.write(f)

    logger.info(f'Signature embedded in PDF: {output_path}')
    return output_path


def _create_sig_overlay(sig_img, sig_w, sig_h, page_w, page_h):
    """Create a single-page PDF containing just the signature image positioned bottom-right."""
    # Save signature as PNG bytes
    img_buffer = io.BytesIO()
    sig_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)

    # Position: bottom-right with 40pt margin
    margin = 40
    x = page_w - sig_w - margin
    y = margin

    # Build a minimal PDF with the image
    # Using raw PDF construction since we don't have reportlab
    from PyPDF2 import PdfWriter as PW
    from PyPDF2.generic import (
        DictionaryObject, NumberObject, StreamObject,
        NameObject, ArrayObject,
    )

    overlay_writer = PW()
    overlay_writer.add_blank_page(width=page_w, height=page_h)
    page = overlay_writer.pages[0]

    # Encode image as flate-compressed stream for inline embedding
    img_bytes = img_buffer.getvalue()

    # Create an image XObject
    img_obj = StreamObject()
    img_obj[NameObject('/Type')] = NameObject('/XObject')
    img_obj[NameObject('/Subtype')] = NameObject('/Image')
    img_obj[NameObject('/Width')] = NumberObject(sig_w)
    img_obj[NameObject('/Height')] = NumberObject(sig_h)
    img_obj[NameObject('/ColorSpace')] = NameObject('/DeviceRGB')
    img_obj[NameObject('/BitsPerComponent')] = NumberObject(8)

    # Convert RGBA to RGB bytes for PDF
    rgb_img = sig_img.convert('RGB')
    raw_data = rgb_img.tobytes()
    img_obj._data = raw_data

    # Add image as indirect object
    img_ref = overlay_writer._add_object(img_obj)

    # Create content stream that draws the image
    content_stream = f'q {sig_w} 0 0 {sig_h} {x:.2f} {y:.2f} cm /SigImg Do Q'

    # Get existing resources or create new
    resources = page.get('/Resources', DictionaryObject())
    if '/XObject' not in resources:
        resources[NameObject('/XObject')] = DictionaryObject()
    resources[NameObject('/XObject')][NameObject('/SigImg')] = img_ref
    page[NameObject('/Resources')] = resources

    # Set content stream
    cs = StreamObject()
    cs._data = content_stream.encode('latin-1')
    cs_ref = overlay_writer._add_object(cs)
    page[NameObject('/Contents')] = cs_ref

    buf = io.BytesIO()
    overlay_writer.write(buf)
    buf.seek(0)
    return buf


def hash_pdf(pdf_path):
    """Compute SHA-256 hash of a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Hex string of the SHA-256 hash.

    Raises:
        FileNotFoundError: If file doesn't exist.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f'PDF not found: {pdf_path}')

    sha256 = hashlib.sha256()
    with open(pdf_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()
