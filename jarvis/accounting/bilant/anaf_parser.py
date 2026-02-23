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
        # Pad to 3 digits (handles '01' -> '001', '103' -> '103', '301' -> '301')
        padded = nr.zfill(3)
        for col in ('1', '2'):
            key = f'F10_{padded}{col}'
            mapping[key] = {'row': nr, 'col': f'C{col}'}
    return mapping


# ════════════════════════════════════════════════════════════════
# XFA PDF Field Filling
# ════════════════════════════════════════════════════════════════

_ANAF_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'static', 'anaf_f10l_template.pdf')


def _fill_datasets_xml(datasets_xml: bytes, values: dict, prior_values: dict | None,
                       form: str = 'F10L') -> bytes:
    """Modify XFA datasets XML to fill C1/C2 field values.

    Args:
        datasets_xml: Raw XML bytes of the XFA datasets stream.
        values: {nr_rd: value} for C2 (current period).
        prior_values: optional {nr_rd: value} for C1 (prior period).
        form: 'F10L' or 'F10S'.

    Returns:
        Modified XML bytes.
    """
    # Register namespaces to preserve them in output
    namespaces = {}
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(datasets_xml), events=['start-ns']):
        namespaces[prefix] = uri
        ET.register_namespace(prefix, uri)

    root = ET.fromstring(datasets_xml)

    # Navigate: datasets → data → form1 → F10L → Table1
    xfa_ns = '{http://www.xfa.org/schema/xfa-data/1.0/}'
    data_elem = root.find(f'{xfa_ns}data')
    if data_elem is None:
        logger.warning('XFA datasets missing <data> element')
        return datasets_xml

    form1 = data_elem.find('form1')
    if form1 is None:
        logger.warning('XFA datasets missing <form1> element')
        return datasets_xml

    form_elem = form1.find(form)
    if form_elem is None:
        logger.warning('XFA datasets missing <%s> element', form)
        return datasets_xml

    table = form_elem.find('Table1')
    if table is None:
        logger.warning('XFA datasets missing <Table1> element')
        return datasets_xml

    filled_count = 0
    for row_elem in table:
        tag = row_elem.tag
        # Skip non-row elements (RGOL separators, F10_r1 header)
        if not tag.startswith('R') or tag.startswith('RGOL') or tag.startswith('F10'):
            continue

        # Extract nr_rd from element name: R01 → '01', R103 → '103', R301 → '301'
        nr_rd = tag[1:]  # strip leading 'R'
        if nr_rd.startswith('_'):
            nr_rd = nr_rd[1:]  # R_PP → 'PP'

        # Fill C2 (current period)
        c2_val = values.get(nr_rd)
        if c2_val is not None and c2_val != 0:
            c2 = row_elem.find('C2')
            if c2 is not None:
                c2.text = str(int(round(float(c2_val))))
                filled_count += 1

        # Fill C1 (prior period)
        if prior_values:
            c1_val = prior_values.get(nr_rd)
            if c1_val is not None and c1_val != 0:
                c1 = row_elem.find('C1')
                if c1 is not None:
                    c1.text = str(int(round(float(c1_val))))

    logger.info('Filled %d C2 values in XFA datasets', filled_count)
    return ET.tostring(root, xml_declaration=True, encoding='UTF-8')


def fill_anaf_pdf(values: dict, prior_values: dict | None = None,
                  template_path: str | None = None,
                  form: str = 'F10L') -> io.BytesIO:
    """Fill editable fields in the original ANAF PDF template with computed values.

    Preserves the original PDF structure — only modifies the XFA datasets XML stream.

    Args:
        values: {nr_rd: value} mapping row numbers to computed C2 values.
        prior_values: optional {nr_rd: value} for C1 (prior period) column.
        template_path: path to ANAF PDF template (defaults to bundled F10L).
        form: 'F10L' or 'F10S'.

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
            modified_xml = _fill_datasets_xml(xml_data, values, prior_values, form)
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
