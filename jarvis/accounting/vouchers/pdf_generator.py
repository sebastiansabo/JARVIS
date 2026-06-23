"""Voucher PDF generation using ReportLab + QR code."""
import io
from datetime import date

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _generate_qr_image(data: str, box_size: int = 8) -> ImageReader:
    """Generate a QR code PIL image wrapped for ReportLab."""
    qr = qrcode.QRCode(version=1, box_size=box_size, border=2,
                        error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return ImageReader(buf)


def _get_user_signature(user_id: int) -> str | None:
    """Fetch user's saved signature (base64 PNG)."""
    if not user_id:
        return None
    try:
        from core.base_repository import BaseRepository
        row = BaseRepository().query_one(
            'SELECT signature FROM users WHERE id = %s', (user_id,)
        )
        return row.get('signature') if row else None
    except Exception:
        return None


def _get_company_info(company_id: int) -> dict:
    """Fetch company details for the voucher header."""
    try:
        from core.base_repository import BaseRepository
        return BaseRepository().query_one(
            'SELECT company, vat, street, city, county, logo_url FROM companies WHERE id = %s',
            (company_id,)
        ) or {}
    except Exception:
        return {}


def generate_voucher_pdf(voucher: dict) -> bytes:
    """Generate a printable A4 voucher PDF with QR code and company details. Returns PDF bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    voucher_code = voucher.get('voucher_code', '')
    company = _get_company_info(voucher.get('company_id', 0))
    company_name = company.get('company', 'AUTOWORLD GROUP')
    company_vat = company.get('vat', '')
    company_addr = ', '.join(filter(None, [company.get('street'), company.get('city'), company.get('county')]))

    # Colors
    primary = HexColor('#1a365d')

    # Background header band
    c.setFillColor(primary)
    c.rect(0, h - 80 * mm, w, 80 * mm, fill=1, stroke=0)

    # Title
    c.setFillColor(HexColor('#ffffff'))
    c.setFont('Helvetica-Bold', 28)
    c.drawString(30 * mm, h - 25 * mm, 'VOUCHER')

    # Voucher code
    c.setFont('Helvetica-Bold', 20)
    c.drawString(30 * mm, h - 40 * mm, voucher_code)

    # Company info (top-right)
    c.setFont('Helvetica-Bold', 11)
    c.drawRightString(w - 55 * mm, h - 15 * mm, company_name)
    c.setFont('Helvetica', 9)
    if company_vat:
        c.drawRightString(w - 55 * mm, h - 20 * mm, f'CUI: {company_vat}')
    if company_addr:
        c.drawRightString(w - 55 * mm, h - 25 * mm, company_addr)

    # QR code in header (top-right corner)
    if voucher_code:
        # QR encodes both the scan prefix and a public URL for browser-based redemption
        qr_data = f"voucher:{voucher_code}"
        try:
            from flask import current_app
            base_url = current_app.config.get('APP_BASE_URL', 'https://jarvis.autoworld.ro')
            qr_data = f"{base_url}/app/voucher/{voucher_code}"
        except RuntimeError:
            pass
        qr_img = _generate_qr_image(qr_data, box_size=6)
        qr_size = 30 * mm
        c.drawImage(qr_img, w - 20 * mm - qr_size, h - 75 * mm,
                     width=qr_size, height=qr_size)

    # Status badge
    status = voucher.get('status', 'unknown').upper()
    c.setFillColor(HexColor('#ffffff'))
    c.setFont('Helvetica-Bold', 10)
    c.drawString(30 * mm, h - 55 * mm, f'Status: {status}')

    # Content area
    y = h - 95 * mm
    c.setFillColor(HexColor('#000000'))

    def _label_value(label, value, y_pos):
        c.setFont('Helvetica', 10)
        c.setFillColor(HexColor('#718096'))
        c.drawString(30 * mm, y_pos, label)
        c.setFont('Helvetica-Bold', 12)
        c.setFillColor(HexColor('#1a202c'))
        c.drawString(80 * mm, y_pos, str(value or ''))
        return y_pos - 10 * mm

    y = _label_value('Client:', voucher.get('client_name', ''), y)
    if voucher.get('client_email'):
        y = _label_value('Email:', voucher['client_email'], y)
    y = _label_value('Contract:', voucher.get('contract_number', ''), y)
    y = _label_value('VIN:', voucher.get('car_vin', ''), y)

    # Benefit
    vt = voucher.get('voucher_type', '')
    benefit = ''
    if vt == 'value':
        benefit = f"{voucher.get('value_lei', '')} LEI"
    elif vt == 'accessory_discount_code':
        benefit = f"Discount Code: {voucher.get('discount_code', '')}"
    elif vt == 'accessory_percentage':
        benefit = f"{voucher.get('discount_percentage', '')}% Discount"
    elif vt == 'service_items':
        items = voucher.get('service_items') or []
        if isinstance(items, list):
            benefit = ', '.join(items)
        else:
            benefit = str(items)

    y = _label_value('Type:', vt.replace('_', ' ').title(), y)
    y = _label_value('Benefit:', benefit, y)

    # Validity
    validity = f"{voucher.get('validity_months', '')} months"
    y = _label_value('Validity:', validity, y)
    y = _label_value('Issued:', str(voucher.get('issued_at', '')), y)
    y = _label_value('Expires:', str(voucher.get('expires_at', '')), y)

    # Separator line
    y -= 5 * mm
    c.setStrokeColor(HexColor('#e2e8f0'))
    c.setLineWidth(0.5)
    c.line(30 * mm, y, w - 30 * mm, y)
    y -= 10 * mm

    # Issuer
    y = _label_value('Issued by:', voucher.get('issued_by_name', ''), y)

    # Issuer signature
    issuer_sig = _get_user_signature(voucher.get('issued_by_user_id'))
    if issuer_sig:
        y -= 3 * mm
        c.setFont('Helvetica', 9)
        c.setFillColor(HexColor('#a0aec0'))
        c.drawString(30 * mm, y, 'Signature:')
        try:
            import base64
            sig_data = issuer_sig.split(',', 1)[-1]  # strip data:image/png;base64, prefix
            sig_buf = io.BytesIO(base64.b64decode(sig_data))
            sig_img = ImageReader(sig_buf)
            c.drawImage(sig_img, 80 * mm, y - 18 * mm, width=50 * mm, height=20 * mm,
                         preserveAspectRatio=True, mask='auto')
            y -= 22 * mm
        except Exception:
            y -= 5 * mm
    else:
        # Signature placeholder
        y -= 15 * mm
        c.setFont('Helvetica', 9)
        c.setFillColor(HexColor('#a0aec0'))
        c.drawString(30 * mm, y, 'Signature:')
        c.rect(30 * mm, y - 20 * mm, 60 * mm, 20 * mm, fill=0, stroke=1)
        y -= 25 * mm

    # Footer
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#a0aec0'))
    c.drawString(30 * mm, 15 * mm, f'Generated: {date.today().isoformat()}')
    c.drawString(30 * mm, 10 * mm, f'Scan QR code to verify/redeem')
    c.drawRightString(w - 20 * mm, 15 * mm, company_name)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
