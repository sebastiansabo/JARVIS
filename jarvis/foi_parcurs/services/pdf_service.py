"""PDF generation service for Foi de Parcurs contracts."""
import os
import base64
import tempfile
import logging
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = logging.getLogger('jarvis.foi_parcurs.pdf_service')

# Output directory (relative to Flask app root — will be resolved at call time)
_PDF_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'pdfs', 'foi-parcurs')


def _ensure_dir():
    os.makedirs(_PDF_DIR, exist_ok=True)


def _decode_signature(data_url: str) -> str | None:
    """Decode a base64 PNG data URL and save as a temp file. Returns temp file path or None."""
    if not data_url or not data_url.startswith('data:image'):
        return None
    try:
        header, b64data = data_url.split(',', 1)
        img_bytes = base64.b64decode(b64data)
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp.write(img_bytes)
        tmp.close()
        return tmp.name
    except Exception:
        logger.warning('Failed to decode signature image', exc_info=True)
        return None


def _fmt_dt(dt_val) -> str:
    """Format a datetime or ISO string nicely."""
    if not dt_val:
        return '—'
    if isinstance(dt_val, str):
        try:
            dt_val = datetime.fromisoformat(dt_val.replace('Z', '+00:00'))
        except Exception:
            return str(dt_val)
    return dt_val.strftime('%d.%m.%Y %H:%M')


def _sig_image(data_url: str, width: float = 55 * mm, height: float = 22 * mm):
    """Return a ReportLab Image flowable from a base64 data URL, or None."""
    path = _decode_signature(data_url)
    if not path:
        return None
    return Image(path, width=width, height=height)


# ---------------------------------------------------------------------------
# Legal PDF — standard Foaie de Parcurs format
# ---------------------------------------------------------------------------

def generate_legal_pdf(contract: dict) -> str:
    """Generate the official Foaie de Parcurs PDF and return its file path."""
    _ensure_dir()
    cid = contract.get('contract_id', contract.get('id', 'unknown'))
    out_path = os.path.join(_PDF_DIR, f'{cid}-legal.pdf')

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'FPTitle', parent=styles['Heading1'],
        fontSize=16, alignment=TA_CENTER, spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        'FPSub', parent=styles['Normal'],
        fontSize=10, alignment=TA_CENTER, spaceAfter=2,
    )
    label_style = ParagraphStyle(
        'FPLabel', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#555555'),
    )
    value_style = ParagraphStyle(
        'FPValue', parent=styles['Normal'],
        fontSize=10, leading=13,
    )
    section_style = ParagraphStyle(
        'FPSection', parent=styles['Heading3'],
        fontSize=11, spaceBefore=8, spaceAfter=4,
        textColor=colors.HexColor('#1a1a2e'),
    )

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )

    W = A4[0] - 40 * mm  # usable width

    story = []

    # ---- Header ----
    story.append(Paragraph('FOAIE DE PARCURS', title_style))
    story.append(Paragraph(f'Nr. {cid}', sub_style))
    story.append(HRFlowable(width='100%', thickness=1.5, color=colors.HexColor('#1a1a2e'), spaceAfter=8))

    # ---- Company & Vehicle ----
    story.append(Paragraph('Date Companie și Vehicul', section_style))

    cv_data = [
        [Paragraph('Companie', label_style), Paragraph(str(contract.get('company_name') or '—'), value_style)],
        [Paragraph('VIN', label_style), Paragraph(str(contract.get('vin') or '—'), value_style)],
        [Paragraph('Nr. înmatriculare', label_style), Paragraph(str(contract.get('registration_number') or '—'), value_style)],
    ]
    cv_table = Table(cv_data, colWidths=[45 * mm, W - 45 * mm])
    cv_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ]))
    story.append(cv_table)
    story.append(Spacer(1, 6))

    # ---- Client ----
    story.append(Paragraph('Date Client', section_style))
    cl_data = [
        [Paragraph('Client', label_style), Paragraph(str(contract.get('client_name') or '—'), value_style)],
        [Paragraph('Consilier vânzări', label_style), Paragraph(str(contract.get('advisor_name') or '—'), value_style)],
    ]
    cl_table = Table(cl_data, colWidths=[45 * mm, W - 45 * mm])
    cl_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ]))
    story.append(cl_table)
    story.append(Spacer(1, 6))

    # ---- Route ----
    story.append(Paragraph('Rută', section_style))
    ro_data = [
        [Paragraph('Itinerar', label_style), Paragraph(str(contract.get('itinerary') or '—'), value_style)],
        [Paragraph('Plecare', label_style), Paragraph(_fmt_dt(contract.get('departure_datetime')), value_style)],
        [Paragraph('Retur', label_style), Paragraph(_fmt_dt(contract.get('return_datetime')), value_style)],
    ]
    ro_table = Table(ro_data, colWidths=[45 * mm, W - 45 * mm])
    ro_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ]))
    story.append(ro_table)
    story.append(Spacer(1, 6))

    # ---- Odometer ----
    story.append(Paragraph('Kilometraj', section_style))
    km_data = [
        [Paragraph('Km start', label_style), Paragraph(str(contract.get('km_start') or '—'), value_style),
         Paragraph('Km final', label_style), Paragraph(str(contract.get('km_end') or '—'), value_style)],
        [Paragraph('Distanță parcursă', label_style), Paragraph(f"{contract.get('distance_km') or '—'} km", value_style), '', ''],
    ]
    km_table = Table(km_data, colWidths=[38 * mm, 35 * mm, 38 * mm, W - 111 * mm])
    km_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('SPAN', (1, 1), (3, 1)),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ]))
    story.append(km_table)
    story.append(Spacer(1, 6))

    # ---- Fuel ----
    story.append(Paragraph('Combustibil', section_style))
    fu_data = [
        [Paragraph('Nivel plecare', label_style), Paragraph(str(contract.get('fuel_gauge_start_level') or '—'), value_style),
         Paragraph('Nivel sosire', label_style), Paragraph(str(contract.get('fuel_gauge_end_level') or '—'), value_style)],
        [Paragraph('Litri start', label_style), Paragraph(str(contract.get('fuel_start_liters') or '—'), value_style),
         Paragraph('Litri final', label_style), Paragraph(str(contract.get('fuel_end_liters') or '—'), value_style)],
        [Paragraph('Combustibil consumat', label_style), Paragraph(f"{contract.get('fuel_consumed_liters') or '—'} L", value_style), '', ''],
    ]
    fu_table = Table(fu_data, colWidths=[38 * mm, 35 * mm, 38 * mm, W - 111 * mm])
    fu_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('SPAN', (1, 2), (3, 2)),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ]))
    story.append(fu_table)
    story.append(Spacer(1, 10))

    # ---- Signatures ----
    story.append(Paragraph('Semnături', section_style))

    client_sig_img = _sig_image(contract.get('client_signature', ''))
    advisor_sig_img = _sig_image(contract.get('signature_ai_generated', ''))

    sig_box_style = TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#999999')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ])

    col_w = W / 2 - 3 * mm

    def _sig_cell(img, label):
        inner = []
        if img:
            inner.append([img])
        else:
            inner.append([Paragraph('<i>Lipsă semnătură</i>', ParagraphStyle('x', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=colors.grey))])
        inner.append([Paragraph(label, ParagraphStyle('lbl', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER))])
        t = Table(inner, colWidths=[col_w - 4 * mm])
        t.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return t

    sig_row = [[_sig_cell(client_sig_img, 'Semnătură Client'), _sig_cell(advisor_sig_img, 'Semnătură Consilier')]]
    sig_table = Table(sig_row, colWidths=[col_w, col_w], rowHeights=[35 * mm])
    sig_table.setStyle(sig_box_style)
    story.append(sig_table)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc'), spaceAfter=4))
    story.append(Paragraph(
        f'Document generat automat • {datetime.now().strftime("%d.%m.%Y %H:%M")}',
        ParagraphStyle('footer', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER, textColor=colors.grey),
    ))

    doc.build(story)
    logger.info('Legal PDF generated: %s', out_path)
    return out_path


# ---------------------------------------------------------------------------
# Custom PDF — branded Test Drive Summary
# ---------------------------------------------------------------------------

def generate_custom_pdf(contract: dict) -> str:
    """Generate a branded Test Drive summary PDF and return its file path."""
    _ensure_dir()
    cid = contract.get('contract_id', contract.get('id', 'unknown'))
    out_path = os.path.join(_PDF_DIR, f'{cid}-custom.pdf')

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TDTitle', parent=styles['Heading1'],
        fontSize=18, alignment=TA_CENTER, spaceAfter=2,
        textColor=colors.HexColor('#1a1a2e'),
    )
    sub_style = ParagraphStyle(
        'TDSub', parent=styles['Normal'],
        fontSize=11, alignment=TA_CENTER, spaceAfter=6,
        textColor=colors.HexColor('#444444'),
    )
    section_style = ParagraphStyle(
        'TDSection', parent=styles['Heading3'],
        fontSize=11, spaceBefore=10, spaceAfter=4,
        textColor=colors.white,
        backColor=colors.HexColor('#1a1a2e'),
        leftIndent=-2, rightIndent=-2,
    )
    label_style = ParagraphStyle(
        'TDLabel', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#666666'),
    )
    value_style = ParagraphStyle(
        'TDValue', parent=styles['Normal'],
        fontSize=10, leading=13,
    )
    note_style = ParagraphStyle(
        'TDNote', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#888888'), leading=11,
    )

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )

    W = A4[0] - 40 * mm

    story = []

    # ---- Header banner ----
    banner_data = [[Paragraph('Rezumat Test Drive', title_style)],
                   [Paragraph(str(contract.get('company_name') or ''), sub_style)]]
    banner = Table(banner_data, colWidths=[W])
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f4ff')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1a1a2e')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 8))

    def section_table(rows):
        t = Table(rows, colWidths=[48 * mm, W - 48 * mm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#e0e0e0')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8f8f8')),
        ]))
        return t

    def section_header(title):
        p = Paragraph(f'&nbsp; {title}', section_style)
        t = Table([[p]], colWidths=[W])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1a1a2e')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        return t

    def row(lbl, val):
        return [Paragraph(lbl, label_style), Paragraph(str(val) if val else '—', value_style)]

    # ---- Vehicle ----
    story.append(section_header('Vehicul'))
    story.append(section_table([
        row('VIN', contract.get('vin')),
        row('Nr. înmatriculare', contract.get('registration_number')),
    ]))
    story.append(Spacer(1, 4))

    # ---- Client ----
    story.append(section_header('Client'))
    story.append(section_table([
        row('Nume', contract.get('client_name')),
        row('Consilier vânzări', contract.get('advisor_name')),
    ]))
    story.append(Spacer(1, 4))

    # ---- Rută ----
    story.append(section_header('Rută'))
    story.append(section_table([
        row('Itinerar', contract.get('itinerary')),
        row('Plecare', _fmt_dt(contract.get('departure_datetime'))),
        row('Retur', _fmt_dt(contract.get('return_datetime'))),
        row('Distanță estimată', f"{contract.get('distance_km') or '—'} km"),
    ]))
    story.append(Spacer(1, 4))

    # ---- Kilometraj & Combustibil ----
    story.append(section_header('Kilometraj & Combustibil'))
    story.append(section_table([
        row('Km start', contract.get('km_start')),
        row('Km final', contract.get('km_end')),
        row('Nivel combustibil (plecare)', contract.get('fuel_gauge_start_level')),
        row('Nivel combustibil (sosire)', contract.get('fuel_gauge_end_level')),
        row('Combustibil consumat', f"{contract.get('fuel_consumed_liters') or '—'} L"),
    ]))
    story.append(Spacer(1, 4))

    # ---- Consimțăminte ----
    story.append(section_header('Consimțăminte'))

    gdpr_text = 'DA — consimțământ acordat' if contract.get('gdpr_consent') else 'NU'
    insp_text = 'DA — acceptat' if contract.get('inspection_acceptance') else 'NU'

    story.append(section_table([
        row('Consimțământ GDPR', gdpr_text),
        row('Acceptare inspecție', insp_text),
    ]))
    story.append(Spacer(1, 8))

    # ---- Signatures ----
    story.append(section_header('Semnături'))
    story.append(Spacer(1, 4))

    client_sig_img = _sig_image(contract.get('client_signature', ''))
    advisor_sig_img = _sig_image(contract.get('signature_ai_generated', ''))

    col_w = W / 2 - 3 * mm

    no_sig_style = ParagraphStyle('nosig', parent=styles['Normal'], fontSize=8,
                                  alignment=TA_CENTER, textColor=colors.grey)
    lbl_sig_style = ParagraphStyle('lblsig', parent=styles['Normal'], fontSize=9,
                                   alignment=TA_CENTER, fontName='Helvetica-Bold')

    def _sig_cell(img, label):
        inner = []
        if img:
            inner.append([img])
        else:
            inner.append([Paragraph('<i>Lipsă semnătură</i>', no_sig_style)])
        inner.append([Paragraph(label, lbl_sig_style)])
        t = Table(inner, colWidths=[col_w - 4 * mm])
        t.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return t

    sig_row = [[_sig_cell(client_sig_img, 'Semnătură Client'), _sig_cell(advisor_sig_img, 'Semnătură Consilier')]]
    sig_table = Table(sig_row, colWidths=[col_w, col_w], rowHeights=[38 * mm])
    sig_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#999999')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fafafa')),
    ]))
    story.append(sig_table)

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc'), spaceAfter=4))
    story.append(Paragraph(
        f'Generat automat de JARVIS • {datetime.now().strftime("%d.%m.%Y %H:%M")} • {cid}',
        ParagraphStyle('footer', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER, textColor=colors.grey),
    ))

    doc.build(story)
    logger.info('Custom PDF generated: %s', out_path)
    return out_path
