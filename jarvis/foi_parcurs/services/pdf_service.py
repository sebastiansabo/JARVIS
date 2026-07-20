"""PDF generation service for Foi de Parcurs contracts."""
import os
import base64
import tempfile
import logging
import unicodedata
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph as _RLParagraph, Spacer, Table, TableStyle, Image, HRFlowable,
    PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

logger = logging.getLogger('jarvis.foi_parcurs.pdf_service')


def _ascii(text):
    """Strip diacritics to plain ASCII (ș→s, ț→t, ă→a, â→a, î→i, and any other
    accented Latin letters). The base-14 reportlab fonts (Helvetica) can't render
    Romanian glyphs, so they'd otherwise show as boxes — we drop them entirely."""
    if not isinstance(text, str):
        return text
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def Paragraph(text, *args, **kwargs):
    """reportlab Paragraph with diacritics stripped from the text (see _ascii)."""
    return _RLParagraph(_ascii(text) if isinstance(text, str) else text, *args, **kwargs)


# Prestator (provider) party header shown at the top of the legal contract.
_PRESTATOR_INTRO = (
    'S.C. AUTOWORLD PLUS S.R.L., cu sediul in Cluj-Napoca, Calea Floresti, Nr. 145, '
    'avand puncte de lucru in Calea Clujului 4B_4C Com Apahida, 407035, Cluj, '
    'numar de ordine in Registrul Comertului J/12/2102/2024, CUI 50022994, '
    'cont RO34 BACX 0000 0026 7930 8000 RON, deschis la Unicredit Cluj-Napoca, '
    'telefon: 0264-207 400 / 0264-502 600, reprezentata de Dl Mezei Ioan director General, '
    'denumita in continuare "Prestator", si:'
)

# Fallback Prestator text (used when the contract has no resolvable company).
_PRESTATOR_FALLBACK = _PRESTATOR_INTRO


def _co(text: str, name: str) -> str:
    """Substitute the dealer-name token in body text with the actual company."""
    return text.replace('{CO}', name)


def _company_legal(company: dict) -> dict:
    """Map a `companies` row to Prestator display fields (best-effort, blanks ok)."""
    company = company or {}
    vat = (company.get('vat') or '').strip()
    cui = vat[2:].strip() if vat[:2].upper() == 'RO' else vat
    street = (company.get('street') or '').strip()
    city = (company.get('city') or '').strip()
    sediu = ', '.join(p for p in (city, street) if p)
    showroom = (company.get('showroom_address') or '').strip()
    puncte = '; '.join(line.strip() for line in showroom.splitlines() if line.strip())
    return {
        'name': (company.get('company') or '').strip(),
        'sediu': sediu,
        'puncte': puncte,
        'reg_no': (company.get('reg_no') or '').strip(),
        'cui': cui,
        'iban': (company.get('iban') or '').strip(),
        'bank': (company.get('bank') or '').strip(),
        'administrator': (company.get('administrator') or '').strip(),
    }


def _build_prestator_intro(company: dict, phone: str) -> str:
    """Full Prestator paragraph for the contract's company + brand phone."""
    lg = _company_legal(company)
    parts = [f'S.C. {lg["name"]}']
    if lg['sediu']:
        parts.append(f'cu sediul in {lg["sediu"]}')
    if lg['puncte']:
        parts.append(f'avand puncte de lucru in {lg["puncte"]}')
    if lg['reg_no']:
        parts.append(f'numar de ordine in Registrul Comertului {lg["reg_no"]}')
    if lg['cui']:
        parts.append(f'CUI {lg["cui"]}')
    if lg['iban']:
        cont = f'cont {lg["iban"]}'
        if lg['bank']:
            cont += f', deschis la {lg["bank"]}'
        parts.append(cont)
    if (phone or '').strip():
        parts.append(f'telefon: {phone.strip()}')
    if lg['administrator']:
        parts.append(f'reprezentata de {lg["administrator"]}, administrator')
    return ', '.join(parts) + ', denumita in continuare "Prestator", si:'


# --- Test-drive terms & conditions + GDPR note (appended to the legal PDF) ----

_TC_OBLIGATIONS = [
    'sa utilizeze autovehiculul potrivit destinatiei sale, exclusiv pe drumuri publice, fara a participa la curse auto, competitii, teste de performanta sau alte activitati care pot produce uzura excesiva ori daune autovehiculului;',
    'sa nu forteze, sa nu exploateze abuziv sau necorespunzator autovehiculul si sa respecte instructiunile primite privind utilizarea acestuia;',
    'sa pastreze curatenia in interiorul autovehiculului, sa nu fumeze in habitaclu si sa nu transporte substante periculoase, inflamabile, corozive sau alte obiecte care pot deteriora autovehiculul;',
    'sa asigure integritatea si securitatea autovehiculului pe intreaga perioada in care acesta se afla in folosinta sa;',
    'sa respecte regulile de circulatie si toate prevederile legale aplicabile;',
    'sa nu incredinteze autovehiculul unei alte persoane decat cele nominalizate in contract;',
    'sa nu conduca autovehiculul sub influenta alcoolului, drogurilor, substantelor psihoactive sau a oricaror substante care pot afecta capacitatea de conducere;',
    'sa anunte {CO} in cel mai scurt timp despre orice accident, avarie, defectiune, furt sau alta situatie care poate afecta autovehiculul;',
    'sa obtina, atunci cand legea impune, documentele necesare de la organele competente pentru constatarea accidentului sau avariei;',
    'sa coopereze cu {CO} si cu asiguratorul pentru deschiderea si solutionarea dosarului de dauna.',
]

_TC_LIABILITY = [
    'pentru orice daune, defectiuni, avarii sau stricaciuni produse autovehiculului, in masura in care acestea nu sunt acoperite de asigurarea CASCO;',
    'pentru furtul, distrugerea totala sau partiala a autovehiculului, daca asiguratorul refuza acoperirea prejudiciului conform politei CASCO;',
    'pentru orice daune produse tertilor prin utilizarea autovehiculului, in masura in care acestea nu sunt acoperite de asigurarea RCA;',
    'pentru orice amenzi, sanctiuni, taxe, penalitati sau contraventii rezultate din utilizarea autovehiculului;',
    'pentru lipsa documentelor necesare constatarii unei daune, daca aceasta lipsa impiedica solutionarea dosarului de asigurare.',
]

_TC_CASCO_EXCLUSIONS = [
    'avarierea partii inferioare a autovehiculului, a sasiului, a blocului motor sau a altor componente similare, prin actiune deliberata sau neglijenta;',
    'avarierea jantelor sau pneurilor, daca aceasta nu este cauzata de un accident rutier acoperit de asigurare;',
    'conducerea autovehiculului de catre o persoana neautorizata sau nenominalizata in contract;',
    'conducerea sub influenta alcoolului, drogurilor sau a altor substante interzise;',
    'daunele produse persoanelor si bagajelor aflate in autovehicul, daca acestea nu sunt acoperite prin polita de asigurare aplicabila.',
]

_TC_PARAGRAPHS = [
    'UTILIZATORUL declara ca i-a fost adus la cunostinta faptul ca asigurarea CASCO de care beneficiaza autovehiculul cuprinde o clauza de fransiza in valoare de minim 500 EURO in caz de dauna (in functie de conditiile politei CASCO), respectiv 20% din valoarea asigurata a autovehiculului in caz de dauna totala sau furt al autoturismului. In cazul producerii unei daune sau al furtului autovehiculului.',
    'UTILIZATORUL este obligat sa suporte contravaloarea francizei, astfel cum aceasta este stabilita prin polita de asigurare aplicabila. Plata se va efectua in termen de 3 zile de la comunicarea sumei datorate de catre {CO} sau de catre asigurator.',
    'UTILIZATORUL intelege ca nu dobandeste niciun drept de proprietate sau posesie asupra autovehiculului si are obligatia de a-l returna la data si ora stabilite sau la prima cerere a {CO}.',
    'Autovehiculul poate fi condus doar de persoane care detin permis de conducere valabil si care au o vechime a permisului de minimum 1 an.',
    'Deplasarea in afara teritoriului Romaniei este permisa numai cu acordul prealabil scris al {CO} si, daca este cazul, dupa extinderea valabilitatii asigurarilor pentru strainatate.',
    'In cazul in care UTILIZATORUL constata defectiuni, martori de bord, zgomote anormale sau orice semn care poate afecta siguranta in circulatie ori starea tehnica a autovehiculului, acesta are obligatia sa opreasca utilizarea autovehiculului si sa anunte imediat {CO}.',
    'UTILIZATORUL nu are dreptul sa efectueze reparatii, interventii sau modificari asupra autovehiculului fara acordul scris al {CO}. Reparatiile pot fi efectuate numai intr-un service agreat de {CO}.',
    'Diferenta de combustibil dintre cantitatea existenta la predarea autovehiculului catre UTILIZATOR si cantitatea existenta la returnare se va taxa cu 1,5 EUR/litru de combustibil lipsa.',
    'Autovehiculul va fi returnat in aceeasi stare in care a fost predat, curat la interior si exterior. In caz contrar, UTILIZATORUL va suporta costurile aferente curatarii.',
    'In cazul in care UTILIZATORUL intarzie returnarea autovehiculului cu mai mult de 24 de ore fara acordul {CO}, societatea isi rezerva dreptul de a sesiza organele competente si/sau compania de asigurare.',
    'Raspunderea {CO} este exclusa pentru evenimente, prejudicii sau consecinte produse din culpa UTILIZATORULUI ori ca urmare a nerespectarii obligatiilor asumate prin prezentul document.',
    'UTILIZATORULUI i s-a explicat modul de utilizare a autovehiculului, inclusiv principiile de functionare aplicabile autovehiculelor hibrid/electric, dupa caz, si a fost informat cu privire la tipul de combustibil sau energie utilizat.',
    'UTILIZATORUL declara ca intelege riscurile inerente utilizarii unui autovehicul in circulatia rutiera si ca nu va solicita despagubiri {CO} pentru prejudicii rezultate din accidente sau evenimente care nu sunt imputabile societatii.',
]


def _parse_conditions(text: str) -> list:
    """Parse the general-conditions markup subset into typed blocks.
    Rules: blank line separates blocks; '## ' = heading; '- ' = bullet
    (consecutive bullets = one list); other non-blank runs = one paragraph."""
    blocks = []
    para: list[str] = []
    bullets: list[str] = []

    def flush_para():
        if para:
            blocks.append(('paragraph', ' '.join(para)))
            para.clear()

    def flush_bullets():
        if bullets:
            blocks.append(('bullets', list(bullets)))
            bullets.clear()

    for raw in (text or '').splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_para(); flush_bullets(); continue
        if line.lstrip().startswith('## '):
            flush_para(); flush_bullets()
            blocks.append(('heading', line.lstrip()[3:].strip()))
        elif line.lstrip().startswith('- '):
            flush_para()
            bullets.append(line.lstrip()[2:].strip())
        else:
            flush_bullets()
            para.append(line.strip())
    flush_para(); flush_bullets()
    return blocks


def _general_conditions_flowables(text: str, accepted_at) -> list:
    """Reportlab flowables for the accepted general-conditions section. Empty
    list when there is no text (old/unconfigured contracts)."""
    if not (text or '').strip():
        return []
    styles = getSampleStyleSheet()
    sec = ParagraphStyle('GCSection', parent=styles['Heading3'], fontSize=11,
                         spaceBefore=8, spaceAfter=4, textColor=colors.HexColor('#1a1a2e'))
    head = ParagraphStyle('GCHead', parent=styles['Normal'], fontSize=9.5,
                          leading=13, spaceBefore=4, spaceAfter=2, fontName='Helvetica-Bold')
    body = ParagraphStyle('GCBody', parent=styles['Normal'], fontSize=8.5,
                          leading=12, alignment=TA_JUSTIFY, spaceAfter=4)
    bullet = ParagraphStyle('GCBullet', parent=body, leftIndent=10, bulletIndent=2, spaceAfter=2)
    note = ParagraphStyle('GCNote', parent=styles['Normal'], fontSize=8.5,
                          leading=12, spaceBefore=6, fontName='Helvetica-Oblique')

    fl = [Paragraph('Condiții generale', sec)]
    for kind, payload in _parse_conditions(text):
        if kind == 'heading':
            fl.append(Paragraph(payload, head))
        elif kind == 'bullets':
            for item in payload:
                fl.append(Paragraph(item, bullet, bulletText='•'))
        else:
            fl.append(Paragraph(payload, body))

    when = ''
    if accepted_at:
        try:
            when = datetime.fromisoformat(str(accepted_at).replace('Z', '')).strftime('%d.%m.%Y %H:%M')
        except Exception:
            when = str(accepted_at)
    suffix = f' la data de {when}' if when else ''
    fl.append(Paragraph(f'Clientul a citit și acceptat condițiile generale{suffix}.', note))
    return fl


def _terms_flowables(company_name: str, gdpr_text: str = ''):
    """T&C flowables (+ the company's GDPR text, when configured), appended
    after the contract summary and before the signatures (so the client signs
    having read the terms)."""
    styles = getSampleStyleSheet()
    title = ParagraphStyle('TCTitle', parent=styles['Heading2'], fontSize=12, alignment=TA_CENTER,
                           spaceBefore=2, spaceAfter=6, textColor=colors.HexColor('#1a1a2e'))
    header = ParagraphStyle('TCHead', parent=styles['Heading3'], fontSize=10, spaceBefore=8, spaceAfter=4,
                            textColor=colors.HexColor('#1a1a2e'))
    body = ParagraphStyle('TCBody', parent=styles['Normal'], fontSize=8, leading=11,
                          alignment=TA_JUSTIFY, spaceAfter=4)
    lead = ParagraphStyle('TCLead', parent=body, fontName='Helvetica-Bold', spaceBefore=3, spaceAfter=2)
    bullet = ParagraphStyle('TCBul', parent=body, leftIndent=14, bulletIndent=4, spaceAfter=2)

    def bl(items):
        return [Paragraph(_co(t, company_name), bullet, bulletText='-') for t in items]

    fl = [PageBreak(), Paragraph('CONDITII GENERALE TEST DRIVE', title)]
    fl.append(Paragraph('Pe perioada desfasurarii actiunii de test drive, UTILIZATORUL se obliga:', lead))
    fl += bl(_TC_OBLIGATIONS)
    fl.append(Paragraph('UTILIZATORUL poarta intreaga raspundere:', lead))
    fl += bl(_TC_LIABILITY)
    fl.append(Paragraph('Asigurarea CASCO nu include si nu este valabila in urmatoarele cazuri:', lead))
    fl += bl(_TC_CASCO_EXCLUSIONS)
    fl += [Paragraph(_co(t, company_name), body) for t in _TC_PARAGRAPHS]

    if (gdpr_text or '').strip():
        fl.append(Paragraph('PRELUCRAREA DATELOR CU CARACTER PERSONAL', header))
        for kind, payload in _parse_conditions(gdpr_text):
            if kind == 'heading':
                fl.append(Paragraph(payload, lead))
            elif kind == 'bullets':
                fl += [Paragraph(t, bullet, bulletText='-') for t in payload]
            else:
                fl.append(Paragraph(payload, body))
    return fl

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
    intro_style = ParagraphStyle(
        'FPIntro', parent=styles['Normal'],
        fontSize=8.5, leading=12, alignment=TA_JUSTIFY, spaceAfter=6,
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
    try:
        _dt = contract.get('departure_datetime')
        _hdr_date = (datetime.fromisoformat(str(_dt).replace('Z', '')) if _dt else datetime.now()).strftime('%d.%m.%Y')
    except Exception:
        _hdr_date = datetime.now().strftime('%d.%m.%Y')
    story.append(Paragraph('Contract Driving Auto', title_style))
    story.append(Paragraph(f'Nr. {cid}  •  {_hdr_date}', sub_style))
    story.append(HRFlowable(width='100%', thickness=1.5, color=colors.HexColor('#1a1a2e'), spaceAfter=8))

    # ---- Prestator (provider) party ----
    company_row = None
    _cid = contract.get('company_id')
    if _cid:
        try:
            from core.organization.repositories.company_repository import CompanyRepository
            company_row = CompanyRepository().get(_cid)
        except Exception:
            logging.exception('Prestator: company lookup failed for company_id=%s', _cid)
    if company_row and (company_row.get('company') or '').strip():
        try:
            from foi_parcurs.dealer_config import get_dealer_config
            _phone = get_dealer_config(company_row.get('company'), contract.get('vehicle_brand') or '').get('phone', '')
        except Exception:
            _phone = ''
        prestator_text = _build_prestator_intro(company_row, _phone)
        company_name = (company_row.get('company') or '').strip()
    else:
        prestator_text = _PRESTATOR_FALLBACK
        company_name = 'AUTOWORLD Plus S.R.L.'
    story.append(Paragraph(prestator_text, intro_style))

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

    _kv_style = TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ])

    def _kv_table(rows):
        if not rows:
            rows = [[Paragraph('—', label_style), Paragraph('—', value_style)]]
        t = Table([[Paragraph(l, label_style), Paragraph(str(v), value_style)] for l, v in rows],
                  colWidths=[45 * mm, W - 45 * mm])
        t.setStyle(_kv_style)
        return t

    # ---- Client ----
    story.append(Paragraph('Date Client', section_style))
    cl_rows = [(l, v) for l, v in (
        ('Nume', contract.get('client_name')),
        ('Telefon', contract.get('client_phone')),
        ('Email', contract.get('client_email')),
        ('Adresă', contract.get('client_address')),
        ('Serie/nr permis', contract.get('driver_license_number')),
        ('Valabilitate permis', contract.get('driver_license_expiry')),
    ) if v not in (None, '', '—')]
    story.append(_kv_table(cl_rows))
    story.append(Spacer(1, 6))

    # ---- Consilier ----
    story.append(Paragraph('Consilier', section_style))
    story.append(_kv_table([('Consilier vânzări', contract.get('advisor_name') or '—')]))
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

    # ---- Terms & conditions + GDPR note (own pages, before signing) ----
    story.extend(_terms_flowables(company_name, (company_row.get('gdpr_text') if company_row else '') or ''))

    # ---- Accepted general conditions (dealer-configured, per company/brand) ----
    story.extend(_general_conditions_flowables(
        contract.get('general_conditions_text') or '',
        contract.get('general_conditions_accepted_at'),
    ))

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

    # ---- Driver license photo (at the very end) ----
    lic_path = _decode_signature(contract.get('driver_license_photo') or '')
    if lic_path:
        try:
            from reportlab.lib.utils import ImageReader
            iw, ih = ImageReader(lic_path).getSize()
            disp_w = min(W, 130 * mm)
            disp_h = disp_w * ih / iw
            if disp_h > 85 * mm:
                disp_h = 85 * mm
                disp_w = disp_h * iw / ih
            story.append(Spacer(1, 10))
            story.append(Paragraph('Permis de conducere', section_style))
            story.append(Image(lic_path, width=disp_w, height=disp_h))
        except Exception:
            logger.warning('Could not embed driver-license photo in PDF', exc_info=True)

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
