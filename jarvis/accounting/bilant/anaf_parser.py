"""ANAF PDF Parser — extract bilant template from XFA-based ANAF PDFs.

Parses the XFA template XML stream to extract F10L (large entities, 103 rows)
or F10S (small entities, 49 rows) bilant structure.

Uses PyPDF2 for XFA extraction, pikepdf for XFA field filling.
"""

import io
import os
import re
import html
import logging
import xml.etree.ElementTree as ET

from .formula_engine import extract_ct_formula

logger = logging.getLogger('jarvis.bilant.anaf_parser')

XFA_NS = 'http://www.xfa.org/schema/xfa-template/3.0/'
_NS = f'{{{XFA_NS}}}'


def extract_xfa_streams(pdf_bytes: bytes) -> dict[str, bytes]:
    """Extract all XFA streams from an ANAF PDF.

    Returns dict keyed by stream name ('template', 'datasets', etc.).
    Raises ValueError if the PDF doesn't contain XFA data.
    """
    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    try:
        xfa = reader.trailer['/Root']['/AcroForm']['/XFA']
    except (KeyError, TypeError):
        raise ValueError('PDF does not contain XFA form data')

    streams = {}
    for i in range(0, len(xfa), 2):
        name = str(xfa[i])
        obj = xfa[i + 1].get_object()
        if hasattr(obj, 'get_data'):
            streams[name] = obj.get_data()
        elif isinstance(obj, bytes):
            streams[name] = obj
    return streams


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return text.strip()


def _get_all_text(elem) -> str:
    """Extract all text from an XFA element (handles <text>, <exData>, nested HTML)."""
    # Direct <text> child
    for child in elem.iter(f'{_NS}text'):
        if child.text:
            return child.text.strip()
    # <exData> with HTML content
    for child in elem.iter(f'{_NS}exData'):
        if child.text:
            return _strip_html(child.text)
        inner = ''.join(child.itertext())
        if inner.strip():
            return _strip_html(inner)
    return ''


def _extract_rd_formula_strict(description: str) -> str:
    """Extract row formula with stricter matching than the base extract_row_formula.

    Only matches 'rd.' or '(rd' patterns (not 'rd' inside words like 'acordate').
    """
    if not description:
        return ''
    text = str(description).lower()
    # Require 'rd.' with explicit dot, or 'rd' preceded by '(' or space
    match = re.search(r'(?:^|[\s(])rd\.?\s*([^)]+)\)', text)
    if not match:
        return ''
    raw = match.group(1).strip()
    # Must contain at least one digit to be a valid row formula
    if not re.search(r'\d', raw):
        return ''
    raw = re.sub(r'\s+', '', raw)
    # Expand "la" ranges (e.g., "01la06" -> "01+02+03+04+05+06")
    la_match = re.search(r'(\d+)la(\d+)', raw)
    if la_match:
        start = int(la_match.group(1))
        end = int(la_match.group(2))
        width = len(la_match.group(1))
        if end >= start:
            parts = [str(i).zfill(width) for i in range(start, end + 1)]
            expanded = '+'.join(parts)
            raw = raw[:la_match.start()] + expanded + raw[la_match.end():]
    return raw


def _is_numeric_rd(text: str) -> bool:
    """Check if text looks like a row number (e.g., '01', '103', '35a')."""
    return bool(re.match(r'^\d{1,3}[a-z]?$', text.strip()))


def parse_f10_rows(template_xml: bytes, form: str = 'F10L') -> list[dict]:
    """Parse XFA template XML to extract F10 bilant row definitions.

    Args:
        template_xml: Raw XML bytes of the XFA template stream.
        form: 'F10L' for large entities (103 rows) or 'F10S' for small (49 rows).

    Returns:
        List of row dicts with keys: anaf_name, nr_rd, description,
        formula_ct, formula_rd, row_type, is_bold, indent_level, sort_order.
    """
    root = ET.fromstring(template_xml)

    # Find the form subform (F10L or F10S)
    form_elem = None
    for elem in root.iter(f'{_NS}subform'):
        if elem.get('name') == form:
            form_elem = elem
            break
    if form_elem is None:
        raise ValueError(f'Form {form} not found in XFA template')

    # Find Table1 inside the form
    table1 = None
    for child in form_elem:
        if child.get('name') == 'Table1':
            table1 = child
            break
    if table1 is None:
        raise ValueError(f'Table1 not found inside {form}')

    rows = []
    sort_idx = 0

    for child in table1:
        tag = child.tag.replace(_NS, '')
        name = child.get('name', '')

        if tag != 'subform':
            continue
        # Skip separator/page-break rows
        if name.startswith('RGOL'):
            continue
        # Only process R-prefixed subforms
        if not name.startswith('R'):
            continue

        # Collect all draw/field children with their text
        elements = []
        for sub in child:
            stag = sub.tag.replace(_NS, '')
            sname = sub.get('name', '')
            if stag in ('draw', 'field'):
                text = _get_all_text(sub)
                # Check if element has bold font
                is_bold = False
                for font in sub.iter(f'{_NS}font'):
                    if font.get('weight') == 'bold':
                        is_bold = True
                        break
                elements.append({
                    'tag': stag,
                    'name': sname,
                    'text': text,
                    'is_bold': is_bold,
                })

        # Parse elements to extract description and nr_rd
        description = ''
        nr_rd = ''
        bold = False

        # Strategy: first element with long text (or named Cell1) = description
        # Remaining elements with short numeric text = nr_rd
        desc_found = False
        for el in elements:
            text = el['text']
            if not text:
                continue

            if el['name'] == 'Cell1' or el['name'] == 'Cell2':
                if el['name'] == 'Cell1' and not desc_found:
                    description = text
                    bold = bold or el['is_bold']
                    desc_found = True
                elif el['name'] == 'Cell2' and not nr_rd:
                    if _is_numeric_rd(text):
                        nr_rd = text.strip()
                continue

            # Unnamed element — determine if it's description or nr_rd
            if not desc_found and (len(text) > 5 or not _is_numeric_rd(text)):
                description = text
                bold = bold or el['is_bold']
                desc_found = True
            elif not nr_rd and _is_numeric_rd(text):
                nr_rd = text.strip()

        # Clean up description whitespace
        description = re.sub(r'\s+', ' ', description).strip()

        # Extract formulas from description
        formula_ct = extract_ct_formula(description) or None
        formula_rd = _extract_rd_formula_strict(description) or None

        # Fallback: bare parenthesized account number without 'ct.' prefix
        # e.g. "5.Alte elemente de capitaluri proprii (1031)"
        if not formula_ct and description:
            bare_match = re.search(r'\((\d{3,4})\)\s*$', description)
            if bare_match:
                formula_ct = bare_match.group(1)

        # Determine row type
        has_total = 'TOTAL' in description.upper()
        has_rd_formula = bool(formula_rd)
        is_section = not nr_rd and not formula_ct and not formula_rd and bool(description)

        if is_section:
            row_type = 'section'
        elif has_total or has_rd_formula:
            row_type = 'total'
            bold = True
        else:
            row_type = 'data'

        # Determine indent from row type
        indent = 0
        if row_type == 'data' and nr_rd:
            indent = 1

        rows.append({
            'anaf_name': name,
            'nr_rd': nr_rd or None,
            'description': description,
            'formula_ct': formula_ct,
            'formula_rd': formula_rd,
            'row_type': row_type,
            'is_bold': bold,
            'indent_level': indent,
            'sort_order': sort_idx,
        })
        sort_idx += 1

    logger.info('Parsed %d rows from %s', len(rows), form)
    return rows


def parse_f10_data(datasets_xml: bytes, form: str = 'F10L') -> dict[str, dict[str, float]]:
    """Extract filled values from XFA datasets XML.

    Returns dict of {row_name: {'C1': value, 'C2': value}}.
    """
    root = ET.fromstring(datasets_xml)
    data = {}

    # Find the form data node (may be namespaced or not)
    form_node = None
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == form:
            form_node = elem
            break

    if form_node is None:
        return data

    # Find Table1 under the form node
    for table in form_node.iter():
        tag = table.tag.split('}')[-1] if '}' in table.tag else table.tag
        if tag == 'Table1':
            for row in table:
                row_tag = row.tag.split('}')[-1] if '}' in row.tag else row.tag
                if not row_tag.startswith('R'):
                    continue
                values = {}
                for field in row:
                    ftag = field.tag.split('}')[-1] if '}' in field.tag else field.tag
                    if ftag in ('C1', 'C2') and field.text:
                        try:
                            values[ftag] = float(field.text.strip())
                        except ValueError:
                            pass
                if values:
                    data[row_tag] = values
            break

    return data


def parse_anaf_pdf(pdf_bytes: bytes) -> dict:
    """High-level parser: extract bilant template and data from ANAF PDF.

    Returns:
        {
            'form_type': 'F10L' or 'F10S',
            'rows': [...],     # template row definitions
            'data': {...},     # filled values per row (may be empty)
        }
    """
    streams = extract_xfa_streams(pdf_bytes)

    if 'template' not in streams:
        raise ValueError('XFA template stream not found in PDF')

    template_xml = streams['template']

    # Try F10L first (large entities), fallback to F10S
    form_type = 'F10L'
    try:
        rows = parse_f10_rows(template_xml, form='F10L')
    except ValueError:
        form_type = 'F10S'
        rows = parse_f10_rows(template_xml, form='F10S')

    # Extract data if datasets stream exists
    data = {}
    if 'datasets' in streams:
        data = parse_f10_data(streams['datasets'], form=form_type)

    return {
        'form_type': form_type,
        'rows': rows,
        'data': data,
    }


def generate_row_mapping(rows: list[dict]) -> dict:
    """Generate ANAF field name mapping from parsed rows.

    Returns dict: {'F10_0011': {'row': '01', 'col': 'C1'}, ...}
    ANAF naming: F10_XXXC where XXX = 3-digit padded row number, C = column (1 or 2).
    """
    mapping = {}
    for row in rows:
        nr = row.get('nr_rd')
        if not nr:
            continue
        # Convert B numbering to ANAF code ('35a' → '301'), then pad to 3 digits
        anaf_code = _nr_rd_to_anaf(nr)
        padded = anaf_code.zfill(3)
        for col in ('1', '2'):
            key = f'F10_{padded}{col}'
            mapping[key] = {'row': nr, 'col': f'C{col}'}
    return mapping


def _nr_rd_to_anaf(nr_rd: str) -> str:
    """Convert nr_rd to ANAF row code. Handles '35a' -> '301'."""
    return '301' if nr_rd == '35a' else nr_rd


def _anaf_to_nr_rd(anaf_code: str) -> str:
    """Convert ANAF row code to nr_rd. Handles '301' -> '35a'."""
    return '35a' if anaf_code == '301' else anaf_code


# ════════════════════════════════════════════════════════════════
# ANAF Export Formats (balanta.txt + XML)
# ════════════════════════════════════════════════════════════════

def generate_anaf_txt(values: dict, prior_values: dict | None = None,
                      company_name: str = '', cif: str = '',
                      form: str = 'F10L') -> str:
    """Generate ANAF balanta.txt import file.

    Format: CSV with CR+LF line endings.
    Line 1: 27-field identification record (since 12/2022).
    Lines 2+: balance entries — cont,formular,rand,coloana,semn,suma

    Fields: tipBil,cifE,entitate,judet,sector,localitate,strada,nr,bloc,
            scara,ap,telefon,nrRC,formaProp,caen1,caen2,admin,intocmit,
            calitate,nrOP,oblig,optiune,aprob,auditor,nrRA,cifA,cifLEI

    Args:
        values: {nr_rd: value} for C2 (current period).
        prior_values: optional {nr_rd: value} for C1 (prior period).
        company_name: entity name for identification line.
        cif: CIF/CUI for identification line.
        form: 'F10L' or 'F10S'.

    Returns:
        String content of the balanta.txt file.
    """
    lines = []

    # Line 1: identification (27 fields since 12/2022, previously 26)
    tip_bil = 'BL' if form == 'F10L' else 'BS'
    ident_fields = [
        tip_bil, cif, company_name,
        '', '', '', '', '', '', '', '', '',  # judet..telefon (fields 4-12)
        '', '', '', '',  # nrRC, formaProp, caen1, caen2 (fields 13-16)
        '', '', '', '',  # admin, intocmit, calitate, nrOP (fields 17-20)
        'N', 'N', '0', '', '', '',  # oblig, optiune, aprob, auditor, nrRA, cifA (21-26)
        '',  # cifLEI (field 27, added 12/2022)
    ]
    lines.append(','.join(ident_fields))

    # Balance entries: cont,formular,rand,coloana,semn,suma
    all_rows = set()
    if values:
        all_rows.update(values.keys())
    if prior_values:
        all_rows.update(prior_values.keys())

    for nr_rd in sorted(all_rows, key=lambda x: _nr_rd_to_anaf(x).zfill(4)):
        anaf_rd = _nr_rd_to_anaf(nr_rd)
        # C2 (current period)
        c2_val = values.get(nr_rd) if values else None
        if c2_val is not None and c2_val != 0:
            val = round(float(c2_val))
            sign = '-' if val < 0 else ''
            lines.append(f',{form},R{anaf_rd},C2,{sign},{abs(int(val))}')

        # C1 (prior period)
        if prior_values:
            c1_val = prior_values.get(nr_rd)
            if c1_val is not None and c1_val != 0:
                val = round(float(c1_val))
                sign = '-' if val < 0 else ''
                lines.append(f',{form},R{anaf_rd},C1,{sign},{abs(int(val))}')

    return '\r\n'.join(lines) + '\r\n'


def _xml_escape(val: str) -> str:
    """Escape special chars for XML attribute values."""
    return (val
            .replace('&', '&amp;')
            .replace('"', '&quot;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def generate_anaf_xml(values: dict, prior_values: dict | None = None,
                      company_name: str = '', cif: str = '',
                      period_date: str | None = None,
                      form: str = 'F10L') -> bytes:
    """Generate ANAF XML import file.

    DEPRECATED: Use anaf_exporter.build_anaf_xml() instead.
    This function only generates F10 tokens for S1002/S1003.
    The new exporter supports all four schemas with F10+F20+F30+F40 and XSD validation.

    The XML uses the official ANAF format:
      <?xml version="1.0"?>
      <Bilant1002 luna="12" an="2024" cui="..." den="..." xmlns:xsi="..." ...>
        <F10 F10_0011="val" F10_0012="val" F10_0021="val" ... />
      </Bilant1002>

    Field naming: F10_XXXC where XXX = 3-digit zero-padded row number,
    C = column (1=C1 prior year, 2=C2 current year).

    The root tag is Bilant1002 (large entities) or Bilant1003 (small entities).
    The ANAF import function validates by checking for 'Bilant1002' in the file.

    Args:
        values: {nr_rd: value} for C2 (current period).
        prior_values: optional {nr_rd: value} for C1 (prior period).
        company_name: entity name.
        cif: CIF/CUI.
        period_date: period end date (e.g. '2024-12-31').
        form: 'F10L' or 'F10S'.

    Returns:
        UTF-8 encoded XML bytes.
    """
    # Parse period date
    an_r = ''
    luna_r = ''
    if period_date:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(period_date.replace('Z', '+00:00') if 'T' in period_date else period_date)
            an_r = str(dt.year)
            luna_r = str(dt.month)
        except (ValueError, AttributeError):
            pass

    # Root tag: Bilant1002 (large entities S1002), Bilant1003 (small S1003)
    root_tag = 'Bilant1002' if form == 'F10L' else 'Bilant1003'
    schema_code = 's1002' if form == 'F10L' else 's1003'
    # Schema version: v14 for annual 2024+
    schema_ver = 'v14'
    tip_bil = 'BL' if form == 'F10L' else 'BS'

    # Build root attributes (identification data)
    parts = [f'<?xml version="1.0"?>\n<{root_tag}']

    if luna_r:
        parts.append(f' luna="{_xml_escape(luna_r)}"')
    if an_r:
        parts.append(f' an="{_xml_escape(an_r)}"')
    if cif:
        parts.append(f' cui="{_xml_escape(cif)}"')
    if company_name:
        parts.append(f' den="{_xml_escape(company_name)}"')
    parts.append(f' tipBIL="{tip_bil}"')

    # XML namespace (required for ANAF validation)
    parts.append(
        f' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        f' xsi:schemaLocation="mfp:anaf:dgti:{schema_code}:declaratie:{schema_ver}'
        f' {schema_code}.xsd"'
        f' xmlns="mfp:anaf:dgti:{schema_code}:declaratie:{schema_ver}"'
    )
    parts.append('>')

    # F10 element with field values as attributes
    f10_attrs = []
    all_rows = set()
    if values:
        all_rows.update(values.keys())
    if prior_values:
        all_rows.update(prior_values.keys())

    for nr_rd in sorted(all_rows, key=lambda x: _nr_rd_to_anaf(x).zfill(4)):
        anaf_code = _nr_rd_to_anaf(nr_rd)
        padded = anaf_code.zfill(3)

        # C1 (prior period) — column suffix "1"
        if prior_values:
            c1_val = prior_values.get(nr_rd)
            if c1_val is not None and c1_val != 0:
                int_val = int(round(float(c1_val)))
                f10_attrs.append(f'F10_{padded}1="{int_val}"')

        # C2 (current period) — column suffix "2"
        if values:
            c2_val = values.get(nr_rd)
            if c2_val is not None and c2_val != 0:
                int_val = int(round(float(c2_val)))
                f10_attrs.append(f'F10_{padded}2="{int_val}"')

    parts.append(f'\n\t<F10 {" ".join(f10_attrs)} />')
    parts.append(f'\n</{root_tag}>')

    return ''.join(parts).encode('utf-8')


# ════════════════════════════════════════════════════════════════
# XFA PDF Field Filling
# ════════════════════════════════════════════════════════════════

_ANAF_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'static', 'anaf_f10s_template.pdf')


def _fill_datasets_xml(datasets_xml: bytes, values: dict, prior_values: dict | None,
                       form: str = 'F10L', f20_values: dict | None = None) -> bytes:
    """Modify XFA datasets XML to fill C1/C2 field values.

    Args:
        datasets_xml: Raw XML bytes of the XFA datasets stream.
        values: {nr_rd: value} for F10L C2 (current period).
        prior_values: optional {nr_rd: value} for F10L C1 (prior period).
        form: 'F10L' or 'F10S'.
        f20_values: optional dict from f20_engine.compute_f20() with keys:
            'named': {row_tag: int}, 'standalone': {(row, idx): int},
            'rows_with_c1_zero': set

    Returns:
        Modified XML bytes.
    """
    # Register namespaces to preserve them in output
    namespaces = {}
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(datasets_xml), events=['start-ns']):
        namespaces[prefix] = uri
        ET.register_namespace(prefix, uri)

    root = ET.fromstring(datasets_xml)

    # Navigate: datasets → data → form1
    xfa_ns = '{http://www.xfa.org/schema/xfa-data/1.0/}'
    data_elem = root.find(f'{xfa_ns}data')
    if data_elem is None:
        logger.warning('XFA datasets missing <data> element')
        return datasets_xml

    form1 = data_elem.find('form1')
    if form1 is None:
        logger.warning('XFA datasets missing <form1> element')
        return datasets_xml

    # ── Fill F10S (Balance Sheet — Bilant Prescurtat) ──
    filled_count = 0
    f10s_elem = form1.find('F10S')
    if f10s_elem is not None:
        filled_count = _fill_f10s_in_datasets(f10s_elem, values, prior_values)
    else:
        # Fallback: try F10L Table1 structure (legacy templates)
        form_elem = form1.find(form)
        if form_elem is not None:
            table = form_elem.find('Table1')
            if table is not None:
                for row_elem in table:
                    tag = row_elem.tag
                    if not tag.startswith('R') or tag.startswith('RGOL') or tag.startswith('F10'):
                        continue

                    raw_code = tag[1:]
                    if raw_code.startswith('_'):
                        raw_code = raw_code[1:]
                    nr_rd = _anaf_to_nr_rd(raw_code)

                    c2_val = values.get(nr_rd)
                    if c2_val is not None and c2_val != 0:
                        c2 = row_elem.find('C2')
                        if c2 is not None:
                            c2.text = str(int(round(float(c2_val))))
                            filled_count += 1

                    if prior_values:
                        c1_val = prior_values.get(nr_rd)
                        if c1_val is not None and c1_val != 0:
                            c1 = row_elem.find('C1')
                            if c1 is not None:
                                c1.text = str(int(round(float(c1_val))))
        else:
            logger.warning('XFA datasets missing F10S and <%s> elements', form)

    logger.info('Filled %d F10 C2 values in XFA datasets', filled_count)

    # ── Fill F20 (Profit & Loss) ──
    if f20_values:
        f20_filled = _fill_f20_in_form1(form1, f20_values)
        logger.info('Filled %d F20 values in XFA datasets', f20_filled)

    # No xml_declaration — datasets is an XDP fragment, not a standalone document.
    # Do NOT use ET.indent() — it corrupts XFA XML structure in Adobe Reader.
    xml_bytes = ET.tostring(root, encoding='unicode').encode('utf-8')
    # Preserve the leading newline from the original stream.
    if datasets_xml.startswith(b'\n') and not xml_bytes.startswith(b'\n'):
        xml_bytes = b'\n' + xml_bytes
    return xml_bytes


# F10S XFA datasets positional structure.
# Each entry: (row_tag, 'pair') for standalone C1/C2 or (row_tag, 'named') for named elements.
_F10S_STRUCTURE = [
    ('R01', 'pair'), ('R02', 'pair'), ('R03', 'pair'), ('R04', 'pair'),
    ('R05', 'pair'), ('R301', 'pair'), ('R302', 'pair'), ('R06', 'pair'),
    ('R07', 'pair'), ('R08', 'pair'), ('R09', 'pair'), ('R10', 'pair'),
    ('R11', 'named'), ('R12', 'named'),
    ('R13', 'pair'), ('R14', 'pair'), ('R15', 'pair'), ('R16', 'pair'),
    ('R17', 'pair'), ('R18', 'pair'), ('R19', 'pair'), ('R20', 'pair'),
    ('R21', 'pair'), ('R22', 'pair'), ('R23', 'pair'), ('R24', 'pair'), ('R25', 'pair'),
    ('R26', 'named'), ('R27', 'named'), ('R28', 'named'),
    ('R29', 'pair'), ('R30', 'pair'), ('R31', 'pair'), ('R32', 'pair'),
    ('R33', 'named'),
    ('R34', 'pair'), ('R35', 'pair'), ('R36', 'pair'), ('R37', 'pair'),
    ('R38', 'pair'), ('R39', 'pair'), ('R40', 'pair'), ('R41', 'pair'), ('R42', 'pair'),
    ('R43', 'pair'), ('R44', 'pair'), ('R45', 'pair'),
    ('R46', 'pair'), ('R47', 'pair'), ('R48', 'pair'), ('R49', 'pair'),
]


def _fill_f10s_in_datasets(f10s_elem, values: dict, prior_values: dict | None) -> int:
    """Fill F10S section in XFA datasets.

    F10S has a flat structure under <F10S>:
      [0] F10_info, [1] C1 (date), [2] C2 (date),
      then alternating named rows (R11, R12, R26, R27, R28, R33) with C1/C2 children,
      and standalone C1/C2 pairs for all other rows.
      Ends with Cell1 (text), Scontrol1, SEMNATURI.

    Args:
        f10s_elem: ElementTree element for <F10S>
        values: {row_tag: int_value} from compute_f10s() — C2 (current period)
        prior_values: optional {row_tag: int_value} for C1 (prior period)

    Returns:
        Number of fields filled.
    """
    children = list(f10s_elem)
    filled = 0
    struct_idx = 0  # index into _F10S_STRUCTURE
    child_idx = 3   # start after F10_info + date C1/C2

    while child_idx < len(children) and struct_idx < len(_F10S_STRUCTURE):
        child = children[child_idx]
        tag = child.tag
        row_tag, kind = _F10S_STRUCTURE[struct_idx]

        if kind == 'named':
            # Named row element (R11, R12, etc.) — must match tag
            if tag != row_tag:
                # Unexpected element, skip
                child_idx += 1
                continue
            val = values.get(row_tag, 0)
            c2_sub = child.find('C2')
            if c2_sub is not None:
                c2_sub.text = str(int(round(float(val)))) if val else '0'
                filled += 1
            c1_sub = child.find('C1')
            if c1_sub is not None:
                if prior_values:
                    c1_val = prior_values.get(row_tag, 0)
                    c1_sub.text = str(int(round(float(c1_val)))) if c1_val else '0'
                # else: leave C1 empty (no prior period data)
            struct_idx += 1
            child_idx += 1

        elif kind == 'pair':
            # Standalone C1/C2 pair — tag should be 'C1'
            if tag == 'C1':
                if prior_values:
                    c1_val = prior_values.get(row_tag, 0)
                    children[child_idx].text = str(int(round(float(c1_val)))) if c1_val else '0'
                # else: leave C1 empty (no prior period data)
                # Next should be C2
                if child_idx + 1 < len(children) and children[child_idx + 1].tag == 'C2':
                    val = values.get(row_tag, 0)
                    children[child_idx + 1].text = str(int(round(float(val)))) if val else '0'
                    filled += 1
                    child_idx += 2
                else:
                    child_idx += 1
                struct_idx += 1
            elif tag == 'Cell1' or tag == 'Scontrol1' or tag == 'SEMNATURI':
                # Skip non-data elements between rows
                child_idx += 1
            else:
                # Unexpected element, skip
                child_idx += 1

    return filled


def _fill_f20_in_form1(form1, f20_values: dict) -> int:
    """Fill F20 named rows and standalone C1/C2 pairs in form1 element.

    F20 structure in XFA: form1 > F20_r1 > R01, C1, C2, R04, C1, C2, ...
    Named rows have C1/C2 as child elements.
    Standalone C1/C2 pairs appear between named rows.

    Args:
        form1: ElementTree element for form1
        f20_values: dict with 'named', 'standalone', 'rows_with_c1_zero'

    Returns:
        Number of fields filled.
    """
    named = f20_values.get('named', {})
    standalone = f20_values.get('standalone', {})
    rows_with_c1_zero = f20_values.get('rows_with_c1_zero', set())

    children = list(form1)

    # Find F20 section start (after F20_r1 element)
    start_idx = 0
    for i, child in enumerate(children):
        if child.tag == 'F20_r1':
            start_idx = i + 1
            break

    if start_idx == 0:
        logger.warning('F20_r1 element not found in form1')
        return 0

    filled = 0
    prev_named = None
    pair_idx = 0
    i = start_idx

    while i < len(children):
        tag = children[i].tag

        if tag.startswith('R') and len(tag) > 1:
            # Named row — fill C1/C2 children
            if tag in named:
                val = named[tag]
                c2_elem = children[i].find('C2')
                if c2_elem is None:
                    c2_elem = ET.SubElement(children[i], 'C2')
                c2_elem.text = str(val)

                c1_elem = children[i].find('C1')
                if c1_elem is None:
                    c1_elem = ET.SubElement(children[i], 'C1')
                c1_elem.text = '0' if tag in rows_with_c1_zero else ''
                filled += 1

            prev_named = tag
            pair_idx = 0
            i += 1

        elif tag == 'C1':
            # Standalone C1/C2 pair
            key = (prev_named, pair_idx)
            c2_next = i + 1 if (i + 1 < len(children) and children[i + 1].tag == 'C2') else None

            if key in standalone:
                val = standalone[key]
                children[i].text = ''  # C1 = empty (prior year)
                if c2_next is not None:
                    children[c2_next].text = str(val)
                filled += 1

            pair_idx += 1
            i = (c2_next + 1) if c2_next else (i + 1)

        elif tag == 'C2':
            # Orphan C2 (no preceding C1 in this pair)
            pair_idx += 1
            i += 1

        elif tag.startswith('F30') or tag.startswith('F40'):
            break
        else:
            i += 1

    return filled


def fill_anaf_pdf(values: dict, prior_values: dict | None = None,
                  template_path: str | None = None,
                  form: str = 'F10L',
                  f20_values: dict | None = None) -> io.BytesIO:
    """Fill editable fields in the original ANAF PDF template with computed values.

    Preserves the original PDF structure — only modifies the XFA datasets XML stream.

    Args:
        values: {nr_rd: value} mapping row numbers to computed F10L C2 values.
        prior_values: optional {nr_rd: value} for F10L C1 (prior period) column.
        template_path: path to ANAF PDF template (defaults to bundled F10L).
        form: 'F10L' or 'F10S'.
        f20_values: optional dict from f20_engine.compute_f20() to fill F20 section.

    Returns:
        io.BytesIO containing the filled PDF.

    Raises:
        ValueError: if template not found or PDF doesn't contain XFA data.
    """
    import pikepdf

    path = template_path or _ANAF_TEMPLATE_PATH
    if not os.path.exists(path):
        raise ValueError(f'ANAF PDF template not found: {path}')

    with open(path, 'rb') as f:
        pdf_bytes = f.read()

    pdf = pikepdf.Pdf.open(io.BytesIO(pdf_bytes))
    try:
        xfa = pdf.Root.AcroForm.XFA
    except (AttributeError, KeyError):
        pdf.close()
        raise ValueError('PDF does not contain XFA form data')

    # Find and modify datasets stream
    datasets_found = False
    for i in range(0, len(xfa), 2):
        if str(xfa[i]) == 'datasets':
            stream_obj = xfa[i + 1]
            xml_data = bytes(stream_obj.read_bytes())
            modified_xml = _fill_datasets_xml(xml_data, values, prior_values, form,
                                              f20_values=f20_values)
            stream_obj.write(modified_xml)
            datasets_found = True
            break

    if not datasets_found:
        pdf.close()
        raise ValueError('XFA datasets stream not found in PDF')

    output = io.BytesIO()
    pdf.save(output)
    pdf.close()
    output.seek(0)
    return output
