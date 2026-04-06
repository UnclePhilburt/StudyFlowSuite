"""
PDF Flattening & Social Attribution for StudyFlow Suite

Rasterizes PDF pages so text cannot be copied/edited,
then adds clean header/footer bars with social attribution
(username, download ID, timestamp) instead of diagonal watermarks.
Also handles image files by converting them to attributed PDFs.
"""

import io
import math
from datetime import datetime
from StudyFlow.logging_utils import debug_log

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    debug_log("[-] PyMuPDF (fitz) not installed -- PDF flattening unavailable")

from PIL import Image, ImageDraw, ImageFont


DPI = 150  # Resolution for rasterizing pages (150 = good quality, reasonable size)
FOOTER_HEIGHT = 30  # pixels for the footer bar (header is fixed at 35px)


def _get_font(size):
    """Get a font, falling back to default if no TTF available."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", size)
        except (OSError, IOError):
            return ImageFont.load_default()


def _add_watermark(img, username, transaction_code):
    """Add social attribution header and footer bars to a Pillow Image."""
    width, height = img.size

    # Convert to RGBA for overlays
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Create overlay for header and footer
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Font sizes
    header_font = _get_font(max(14, width // 70))
    footer_font = _get_font(max(12, width // 80))

    # Header bar (top)
    header_height = 35
    draw.rectangle(
        [(0, 0), (width, header_height)],
        fill=(45, 45, 45, 200)
    )

    # Header text - Left side: username, Right side: StudyFlow Suite
    header_left = f"Shared by @{username}"
    header_right = "StudyFlow Suite"

    draw.text(
        (15, 10),
        header_left,
        fill=(220, 220, 220, 255),
        font=header_font
    )

    # Calculate right-aligned text position
    try:
        right_text_bbox = draw.textbbox((0, 0), header_right, font=header_font)
        right_text_width = right_text_bbox[2] - right_text_bbox[0]
    except:
        right_text_width = len(header_right) * 8  # Fallback estimate

    draw.text(
        (width - right_text_width - 15, 10),
        header_right,
        fill=(100, 149, 237, 255),  # Cornflower blue accent
        font=header_font
    )

    # Footer bar (bottom)
    footer_y = height - FOOTER_HEIGHT
    draw.rectangle(
        [(0, footer_y), (width, height)],
        fill=(45, 45, 45, 200)
    )

    # Footer text
    timestamp = datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")
    footer_text = f"Download ID: {transaction_code}  |  {timestamp}  |  studyflowsuite.com"

    draw.text(
        (15, footer_y + 8),
        footer_text,
        fill=(180, 180, 180, 255),
        font=footer_font
    )

    # Composite overlay onto image
    img = Image.alpha_composite(img, overlay)

    # Convert back to RGB for PDF embedding
    return img.convert('RGB')


def flatten_pdf(file_data, username, transaction_code):
    """
    Flatten a PDF: rasterize each page and add social attribution bars.

    Args:
        file_data: Raw PDF bytes
        username: User's username for attribution header
        transaction_code: Transaction ID for attribution footer

    Returns:
        bytes of the flattened PDF with header/footer attribution
    """
    if fitz is None:
        debug_log("[-] PyMuPDF not available, returning original file")
        return file_data

    try:
        # Open the original PDF
        src_doc = fitz.open(stream=file_data, filetype="pdf")
        page_count = len(src_doc)

        debug_log(f"[*] Flattening PDF: {page_count} pages at {DPI} DPI")

        # Create new PDF from watermarked images
        out_doc = fitz.open()

        for i in range(page_count):
            page = src_doc[i]

            # Render page to pixmap (image)
            mat = fitz.Matrix(DPI / 72, DPI / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Convert to Pillow Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Add watermark
            img = _add_watermark(img, username, transaction_code)

            # Convert back to bytes for PDF insertion
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG', quality=85)
            img_bytes.seek(0)

            # Create new page with same dimensions as original
            rect = page.rect
            out_page = out_doc.new_page(width=rect.width, height=rect.height)

            # Insert the rasterized image to fill the page
            out_page.insert_image(out_page.rect, stream=img_bytes.read())

        # Save to bytes
        output = io.BytesIO()
        out_doc.save(output)
        out_doc.close()
        src_doc.close()

        result = output.getvalue()
        debug_log(f"[+] Flattened PDF: {len(file_data)} -> {len(result)} bytes")
        return result

    except Exception as e:
        debug_log(f"[-] PDF flattening error: {e}")
        return file_data


def flatten_image(file_data, username, transaction_code):
    """
    Convert an image file to a single-page PDF with social attribution.

    Args:
        file_data: Raw image bytes (PNG, JPG, etc.)
        username: User's username for attribution header
        transaction_code: Transaction ID for attribution footer

    Returns:
        bytes of the PDF with header/footer attribution
    """
    if fitz is None:
        debug_log("[-] PyMuPDF not available, returning original file")
        return file_data

    try:
        img = Image.open(io.BytesIO(file_data))
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        img = _add_watermark(img, username, transaction_code)

        # Create PDF from single image
        out_doc = fitz.open()
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG', quality=85)
        img_bytes.seek(0)

        page = out_doc.new_page(width=img.width * 72 / DPI, height=img.height * 72 / DPI)
        page.insert_image(page.rect, stream=img_bytes.read())

        output = io.BytesIO()
        out_doc.save(output)
        out_doc.close()

        result = output.getvalue()
        debug_log(f"[+] Image -> watermarked PDF: {len(file_data)} -> {len(result)} bytes")
        return result

    except Exception as e:
        debug_log(f"[-] Image flattening error: {e}")
        return file_data


def can_flatten(filename):
    """Check if a file can be flattened based on extension."""
    if not filename:
        return False, None
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext == 'pdf':
        return True, 'pdf'
    if ext in ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'):
        return True, 'image'
    return False, None


# ============ UPLOAD-TIME PDF CONVERSION ============

def image_to_pdf(file_data):
    """Convert an image file to a plain PDF (no attribution -- that happens at download)."""
    if fitz is None:
        debug_log("[-] PyMuPDF not available, cannot convert image to PDF")
        return None

    try:
        img = Image.open(io.BytesIO(file_data))
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        if img.mode == 'RGBA':
            img = img.convert('RGB')

        out_doc = fitz.open()
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG', quality=90)
        img_bytes.seek(0)

        page = out_doc.new_page(width=img.width * 72 / DPI, height=img.height * 72 / DPI)
        page.insert_image(page.rect, stream=img_bytes.read())

        output = io.BytesIO()
        out_doc.save(output)
        out_doc.close()

        result = output.getvalue()
        debug_log(f"[+] Image -> PDF: {len(file_data)} -> {len(result)} bytes")
        return result

    except Exception as e:
        debug_log(f"[-] Image to PDF conversion error: {e}")
        return None


def text_to_pdf(text_content):
    """Convert plain text to a multi-page PDF document."""
    if fitz is None:
        debug_log("[-] PyMuPDF not available, cannot convert text to PDF")
        return None

    try:
        out_doc = fitz.open()
        page_width, page_height = 612, 792  # 8.5 x 11 inches in points
        margin = 50
        font_size = 11
        line_height = font_size * 1.4

        lines = text_content.split('\n')
        y = margin
        page = out_doc.new_page(width=page_width, height=page_height)

        for line in lines:
            # Wrap long lines
            while len(line) > 90:
                page.insert_text(
                    fitz.Point(margin, y + font_size),
                    line[:90],
                    fontsize=font_size,
                    fontname="helv"
                )
                line = line[90:]
                y += line_height
                if y + line_height > page_height - margin:
                    page = out_doc.new_page(width=page_width, height=page_height)
                    y = margin

            if y + line_height > page_height - margin:
                page = out_doc.new_page(width=page_width, height=page_height)
                y = margin

            page.insert_text(
                fitz.Point(margin, y + font_size),
                line,
                fontsize=font_size,
                fontname="helv"
            )
            y += line_height

        output = io.BytesIO()
        out_doc.save(output)
        out_doc.close()

        result = output.getvalue()
        debug_log(f"[+] Text -> PDF: {len(text_content)} chars -> {len(result)} bytes")
        return result

    except Exception as e:
        debug_log(f"[-] Text to PDF conversion error: {e}")
        return None


def convert_to_pdf(file_data, filename):
    """
    Convert any supported file to PDF at upload time.

    Returns:
        (pdf_bytes, new_filename) on success
        (None, None) on failure
    """
    if not filename:
        return None, None

    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
    new_filename = f"{base_name}.pdf"

    # Already a PDF
    if ext == 'pdf':
        return file_data, filename

    # Image files
    if ext in ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'):
        pdf_data = image_to_pdf(file_data)
        return (pdf_data, new_filename) if pdf_data else (None, None)

    # Plain text
    if ext == 'txt':
        text = file_data.decode('utf-8', errors='ignore')
        pdf_data = text_to_pdf(text)
        return (pdf_data, new_filename) if pdf_data else (None, None)

    # Word documents
    if ext in ('doc', 'docx'):
        try:
            from docx import Document
            doc = Document(io.BytesIO(file_data))
            text = '\n'.join(p.text for p in doc.paragraphs)
            pdf_data = text_to_pdf(text)
            return (pdf_data, new_filename) if pdf_data else (None, None)
        except Exception as e:
            debug_log(f"[-] DOCX to PDF conversion error: {e}")
            return None, None

    # Unsupported format
    debug_log(f"[-] Cannot convert .{ext} to PDF")
    return None, None
