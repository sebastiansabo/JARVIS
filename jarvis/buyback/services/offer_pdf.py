"""One-page 'Fisa vehicul' PDF for the buyback offer email.

Uses reportlab platypus (the renderer the rest of the app uses). Diacritics are
stripped to ASCII via _ascii() because the base-14 reportlab fonts can't render
Romanian glyphs (ș/ț/ă/â/î) — mirrors foi_parcurs/services/pdf_service.py::_ascii.
"""
import html as _html
import io
import logging
import unicodedata

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from buyback import lifecycle

logger = logging.getLogger('jarvis.buyback.offer_pdf')


def _ascii(value) -> str:
    """Strip diacritics to plain ASCII (ș→s, ț→t, ă→a, â→a, î→i)."""
    text = '' if value is None else str(value)
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _ptext(value) -> str:
    """ASCII + HTML-escaped text safe to put inside a reportlab Paragraph.
    Escaping is REQUIRED for user-controlled fields: reportlab parses a mini
    markup, so a bare '<'/'&' crashes the parser and an <img src=...> tag would
    trigger a fetch (SSRF). Escaping renders everything as literal text."""
    return _html.escape(_ascii(value))


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
    elems.append(Paragraph(_ptext(f"Fisa vehicul — {brand_model}"), styles['Title']))
    code = record.get('record_code') or record.get('id') or ''
    if code:
        elems.append(Paragraph(_ptext(f"Cod solicitare: {code}"), styles['Normal']))
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
        [_ascii(label), Paragraph(_ptext(val), styles['Normal'])]
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


# ═══════════════════════════════════════════════════════════════════════════
# Full record export — all data sections + embedded photos
# ═══════════════════════════════════════════════════════════════════════════

def _money(v) -> str:
    if v is None or str(v).strip() == '':
        return ''
    try:
        return f"{float(v):,.0f} EUR".replace(',', '.')
    except (TypeError, ValueError):
        return str(v)


def _kv_table(rows, styles):
    """Build a 2-column label/value Table from (label, value) pairs, dropping
    blank values (booleans are pre-stringified by the caller via _yes_no)."""
    data = [
        [_ascii(label), Paragraph(_ptext(val), styles['Normal'])]
        for label, val in rows
        if val is not None and str(val).strip() != ''
    ]
    if not data:
        return None
    table = Table(data, colWidths=[55 * mm, 110 * mm])
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
    return table


_EVENT_LABELS = {
    'created': 'Solicitare creata',
    'status_changed': 'Status schimbat',
    'record_edited': 'Detalii editate',
    'inspection_updated': 'Inspectie actualizata',
    'inspection_report_uploaded': 'Raport inspectie incarcat',
}


def _event_line(ev) -> str:
    """One-line summary of an audit event for the Istoric section."""
    action = ev.get('action') or ''
    label = _EVENT_LABELS.get(action, action)
    details = ev.get('details') or {}
    extra = ''
    if action == 'status_changed' and isinstance(details, dict):
        frm = lifecycle.STATUS_LABELS.get(details.get('from'), details.get('from'))
        to = lifecycle.STATUS_LABELS.get(details.get('to'), details.get('to'))
        if frm or to:
            extra = f" ({frm or '-'} -> {to or '-'})"
    elif action == 'record_edited' and isinstance(details, dict):
        changes = details.get('changes') or {}
        if isinstance(changes, dict) and changes:
            extra = ': ' + ', '.join(sorted(changes.keys()))
    ts = ev.get('created_at')
    ts_str = f" — {ts}" if ts else ''
    return f"{label}{extra}{ts_str}"


def build_record_export_pdf(record: dict, offers=None, events=None, photos=None) -> bytes:
    """Render the full BuyBack record (all data sections, offers, history and
    embedded gallery photos) as PDF bytes.

    `photos` is a list of raw image bytes (already resolved from storage by the
    caller, best-effort — an unresolvable photo is simply omitted). Text is
    ASCII-folded (base-14 fonts can't render Romanian diacritics); see _ptext.
    """
    offers = offers or []
    events = events or []
    photos = photos or []

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=16 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
        title='Fisa BuyBack',
    )
    styles = getSampleStyleSheet()
    elems = []

    brand_model = f"{record.get('brand') or ''} {record.get('model') or ''}".strip()
    elems.append(Paragraph(_ptext(f"Fisa BuyBack — {brand_model}"), styles['Title']))
    meta = []
    code = record.get('record_code') or record.get('id')
    if code:
        meta.append(f"Cod: {code}")
    status = record.get('status')
    if status:
        meta.append(f"Status: {lifecycle.STATUS_LABELS.get(status, status)}")
    if record.get('created_at'):
        meta.append(f"Creat: {record.get('created_at')}")
    if meta:
        elems.append(Paragraph(_ptext('   |   '.join(meta)), styles['Normal']))
    elems.append(Spacer(1, 6 * mm))

    def _section(title, rows):
        table = _kv_table(rows, styles)
        if table is None:
            return
        elems.append(Paragraph(_ptext(title), styles['Heading2']))
        elems.append(table)
        elems.append(Spacer(1, 5 * mm))

    _section('Vehicul', [
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
        ('Detalii daune', record.get('damage_details') if record.get('has_damage') else None),
    ])

    _section('Vanzator & Trade-in', [
        ('Tip client', record.get('client_type')),
        ('Status TVA', record.get('vat_status')),
        ('Nume', record.get('seller_name')),
        ('Email', record.get('seller_email')),
        ('Telefon', record.get('seller_phone')),
        ('CUI', record.get('seller_cui')),
        ('Trade-in', _yes_no(record.get('is_trade_in'))),
        ('Vehicul tinta', record.get('target_vehicle_text') if record.get('is_trade_in') else None),
    ])

    _section('Preturi', [
        ('Pret cerut', _money(record.get('client_asking_price_eur'))),
        ('Pret achizitie', _money(record.get('purchase_price_eur')) if record.get('status') == lifecycle.BOUGHT else None),
        ('Cost reconditionare', _money(record.get('reconditioning_cost_eur'))),
    ])

    _section('Inspectie', [
        ('Rating', f"{record.get('inspection_rating')}/5" if record.get('inspection_rating') is not None else None),
        ('Cost reconditionare', _money(record.get('reconditioning_cost_eur'))),
        ('Notite inspectie', record.get('inspection_notes')),
    ])

    # Offers table
    if offers:
        elems.append(Paragraph(_ptext('Oferte'), styles['Heading2']))
        header = ['Tip', 'Suma', 'TVA', 'Decizie', 'Data']
        body = [[
            _ascii(o.get('offer_type') or ''),
            _ascii(_money(o.get('amount_eur'))),
            _ascii(o.get('vat_status') or ''),
            _ascii(o.get('client_decision') or ''),
            _ascii(str(o.get('created_at') or '')[:10]),
        ] for o in offers]
        otable = Table([header] + body, colWidths=[35 * mm, 35 * mm, 30 * mm, 30 * mm, 35 * mm])
        otable.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f7f7')]),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eeeeee')),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elems.append(otable)
        elems.append(Spacer(1, 5 * mm))

    # History (Istoric)
    if events:
        elems.append(Paragraph(_ptext('Istoric'), styles['Heading2']))
        for ev in events:
            elems.append(Paragraph(_ptext(f"• {_event_line(ev)}"), styles['Normal']))
        elems.append(Spacer(1, 5 * mm))

    # Photos — scaled to fit, flowing across pages
    if photos:
        elems.append(Paragraph(_ptext(f"Poze ({len(photos)})"), styles['Heading2']))
        max_w = 120 * mm
        max_h = 90 * mm
        for data in photos:
            try:
                ir = ImageReader(io.BytesIO(data))
                iw, ih = ir.getSize()
                if not iw or not ih:
                    continue
                scale = min(max_w / iw, max_h / ih)
                img = Image(io.BytesIO(data), width=iw * scale, height=ih * scale)
                img.hAlign = 'LEFT'
                elems.append(img)
                elems.append(Spacer(1, 4 * mm))
            except Exception:
                logger.warning('export pdf: failed to embed a photo', exc_info=True)

    doc.build(elems)
    return buf.getvalue()
