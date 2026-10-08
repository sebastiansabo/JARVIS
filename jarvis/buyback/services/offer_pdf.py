"""One-page 'Fisa vehicul' PDF for the buyback offer email.

Uses reportlab platypus (the renderer the rest of the app uses). Diacritics are
stripped to ASCII via _ascii() because the base-14 reportlab fonts can't render
Romanian glyphs (ș/ț/ă/â/î) — mirrors foi_parcurs/services/pdf_service.py::_ascii.
"""
import io
import unicodedata

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _ascii(value) -> str:
    """Strip diacritics to plain ASCII (ș→s, ț→t, ă→a, â→a, î→i)."""
    text = '' if value is None else str(value)
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _yes_no(v) -> str:
    if v is None:
        return '-'
    return 'Da' if v else 'Nu'


def build_vehicle_sheet_pdf(record: dict) -> bytes:
    """Render a single-page A4 vehicle spec sheet as PDF bytes. Missing fields
    are omitted; the damage-details row appears only when the car has damage."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title='Fisa vehicul',
    )
    styles = getSampleStyleSheet()
    elems = []

    brand_model = f"{record.get('brand') or ''} {record.get('model') or ''}".strip()
    elems.append(Paragraph(_ascii(f"Fisa vehicul — {brand_model}"), styles['Title']))
    code = record.get('record_code') or record.get('id') or ''
    if code:
        elems.append(Paragraph(_ascii(f"Cod solicitare: {code}"), styles['Normal']))
    elems.append(Spacer(1, 8 * mm))

    # (label, value) in display order; raw empty values are dropped, boolean
    # fields always render (Da/Nu/-).
    rows = [
        ('Marca', record.get('brand')),
        ('Model', record.get('model')),
        ('Varianta', record.get('variant')),
        ('Echipare', record.get('equipment')),
        ('VIN', record.get('vin')),
        ('Rulaj (km)', record.get('mileage_km')),
        ('Capacitate cilindrica (cm3)', record.get('engine_capacity_cm3')),
        ('Combustibil', record.get('fuel_type')),
        ('Transmisie', record.get('transmission')),
        ('Cutie de viteze', record.get('gearbox')),
        ('Data fabricatie', record.get('manufacture_date')),
        ('Data prima inmatriculare', record.get('first_registration_date')),
        ('Istoric service la zi', _yes_no(record.get('service_history_uptodate'))),
        ('Roti extra', _yes_no(record.get('extra_wheels'))),
        ('Nr. chei', record.get('keys_count')),
        ('Conditie generala (1-5)', record.get('general_condition')),
        ('Daune', _yes_no(record.get('has_damage'))),
    ]
    if record.get('has_damage') and record.get('damage_details'):
        rows.append(('Detalii daune', record.get('damage_details')))

    table_data = [
        [_ascii(label), Paragraph(_ascii(val), styles['Normal'])]
        for label, val in rows
        if val is not None and str(val).strip() != ''
    ]

    table = Table(table_data, colWidths=[55 * mm, 110 * mm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f7f7f7')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elems.append(table)

    doc.build(elems)
    return buf.getvalue()
