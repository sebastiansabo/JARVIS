import anthropic
import base64
import os
import re
from pdf2image import convert_from_path
from PIL import Image
from io import BytesIO
from typing import Optional
import json
import tempfile


def normalize_vat_number(vat: str) -> str:
    """
    Normalize VAT number to a consistent format: COUNTRYCODE + NUMBERS (no spaces).
    Examples:
        'RO 225615' -> 'RO225615'
        'RO225615' -> 'RO225615'
        'CUI 225615' -> 'RO225615'
        'CIF: RO 225615' -> 'RO225615'
        '225615' -> '225615'
        'RO-225-615' -> 'RO225615'
    """
    if not vat:
        return None

    # Convert to uppercase and strip
    vat = str(vat).upper().strip()

    # Remove common prefixes like 'CUI', 'CIF', 'VAT', 'TAX ID', etc.
    prefixes_to_remove = ['CUI:', 'CUI', 'CIF:', 'CIF', 'VAT:', 'VAT', 'TAX ID:', 'TAX ID', 'NR.', 'NR', 'NO.', 'NO']
    for prefix in prefixes_to_remove:
        if vat.startswith(prefix):
            vat = vat[len(prefix):].strip()

    # Remove all spaces, dashes, dots, and other separators
    vat = re.sub(r'[\s\-\./:]+', '', vat)

    # Extract country code (2 letters at start) and numbers
    match = re.match(r'^([A-Z]{2})(\d+)$', vat)
    if match:
        country_code = match.group(1)
        numbers = match.group(2)
        return f"{country_code}{numbers}"

    # If no country code, just return the cleaned number
    # But if it looks like a Romanian VAT (starts with digits), assume RO
    numbers_only = re.sub(r'[^0-9]', '', vat)
    if numbers_only:
        return numbers_only

    return vat if vat else None


def encode_image_to_base64(image_path: str) -> tuple[str, str]:
    """Convert image file to base64 string and return with media type."""
    ext = os.path.splitext(image_path)[1].lower()

    media_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }

    media_type = media_types.get(ext, 'image/jpeg')

    with open(image_path, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')

    return image_data, media_type


def pdf_to_images(pdf_path: str) -> list[tuple[str, str]]:
    """Convert PDF pages to base64 encoded images."""
    images = convert_from_path(pdf_path, dpi=150)
    result = []

    for img in images:
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        image_data = base64.standard_b64encode(buffer.read()).decode('utf-8')
        result.append((image_data, 'image/png'))

    return result


def parse_invoice(file_path: str, api_key: Optional[str] = None) -> dict:
    """
    Parse an invoice file (PDF or image) using Claude's vision capabilities.

    Returns a dict with:
        - supplier: str
        - invoice_number: str
        - invoice_date: str (YYYY-MM-DD format)
        - invoice_value: float
        - currency: str
        - description: str (what the invoice is for)
        - raw_text: str (extracted text from invoice)
    """
    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Please set the environment variable or pass api_key parameter.")

    client = anthropic.Anthropic(api_key=api_key)

    # Prepare image(s) based on file type
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.pdf':
        images = pdf_to_images(file_path)
    elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        images = [encode_image_to_base64(file_path)]
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # Build message content with images
    content = []
    for image_data, media_type in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data
            }
        })

    content.append({
        "type": "text",
        "text": """Analyze this invoice and extract the following information. Return ONLY a valid JSON object with these exact keys:

{
    "supplier": "Name of the company/vendor issuing the invoice",
    "supplier_vat": "RO12345678",
    "customer": "Name of the company/person being billed (the buyer/client receiving the invoice)",
    "customer_vat": "RO12345678",
    "invoice_number": "Invoice number/reference (include series if present, e.g., 'FBADS-733-103901503')",
    "invoice_date": "Date in YYYY-MM-DD format",
    "invoice_value": 123.45,
    "currency": "RON/EUR/USD etc",
    "description": "Brief description of what the invoice is for",
    "raw_text": "Key text extracted from the invoice"
}

CRITICAL - EXAMINE ALL PAGES CAREFULLY:
- For multi-page documents, the customer company name and VAT are often at the BOTTOM/FOOTER of the LAST page
- Meta/Facebook invoices: Look for "S.C. [COMPANY NAME] S.R.L." and "VAT: RO..." at the bottom of the last page
- The top of page 1 may show an account name (e.g., "Factura pentru Carcloud") - this is NOT the customer company name
- The actual customer is the registered company with VAT shown in the footer (e.g., "S.C. AUTOWORLD NEXT S.R.L." with "VAT: RO50186814")

CRITICAL - VAT NUMBER FORMAT:
- supplier_vat and customer_vat MUST be normalized to format: COUNTRYCODE + NUMBERS with NO SPACES
- Examples of correct format: "RO12345678", "RO50022994", "DE123456789"
- Convert "RO 225615" -> "RO225615"
- Convert "CUI 225615" -> "225615" (just numbers if no country code visible)
- Convert "CIF: RO 50022994" -> "RO50022994"
- Remove all spaces, dashes, dots, colons from VAT numbers
- Look for CIF, CUI, VAT, Cod Fiscal, Tax ID, "VAT Reg. No." labels near company info
- If country prefix (like RO, DE, IE, etc.) is present, include it directly before numbers

Other important notes:
- invoice_value should be a number (no quotes), representing the total amount
- customer is the REGISTERED COMPANY being invoiced (with official name like "S.C. XXX S.R.L."), not just an account name
- customer_vat is the VAT/CUI/Tax ID of the customer (buyer) - MUST be found, check footer sections
- supplier_vat is the VAT/CUI/Tax ID of the supplier (seller)
- If you can't find a field, use null
- For invoice_number, include any series/prefix (look for "Factura nr." or similar)
- Return ONLY the JSON, no other text"""
    })

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": content}
        ]
    )

    # Parse the response
    response_text = response.content[0].text.strip()

    # Try to extract JSON from response
    try:
        # Handle case where response might have markdown code blocks
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]

        result = json.loads(response_text)

        # Post-process: normalize VAT numbers to ensure consistent format
        if result.get('supplier_vat'):
            result['supplier_vat'] = normalize_vat_number(result['supplier_vat'])
        if result.get('customer_vat'):
            result['customer_vat'] = normalize_vat_number(result['customer_vat'])

        # Post-process: normalize invoice_date to YYYY-MM-DD format
        if result.get('invoice_date'):
            result['invoice_date'] = parse_romanian_date(result['invoice_date'])

        return result
    except json.JSONDecodeError as e:
        return {
            "supplier": None,
            "invoice_number": None,
            "invoice_date": None,
            "invoice_value": None,
            "currency": None,
            "description": None,
            "raw_text": response_text,
            "parse_error": str(e)
        }


def parse_invoice_from_bytes(file_bytes: bytes, filename: str, api_key: Optional[str] = None) -> dict:
    """Parse invoice from uploaded file bytes."""
    ext = os.path.splitext(filename)[1].lower()

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        return parse_invoice(tmp_path, api_key)
    finally:
        os.unlink(tmp_path)


def extract_missing_fields_with_ai(file_path: str, missing_fields: list, api_key: Optional[str] = None) -> dict:
    """
    Use AI to extract only specific missing fields from an invoice.
    This is a targeted extraction to fill gaps left by template parsing.

    Args:
        file_path: Path to the invoice file
        missing_fields: List of field names to extract (e.g., ['invoice_number', 'invoice_value'])
        api_key: Optional Anthropic API key

    Returns:
        Dict with only the requested fields
    """
    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')

    if not api_key:
        return {}

    client = anthropic.Anthropic(api_key=api_key)

    # Prepare image(s) based on file type
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.pdf':
        images = pdf_to_images(file_path)
    elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        images = [encode_image_to_base64(file_path)]
    else:
        return {}

    # Build message content with images
    content = []
    for image_data, media_type in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data
            }
        })

    # Build field descriptions for the prompt
    field_descriptions = {
        'invoice_number': '"invoice_number": "Invoice number/reference (include series if present, e.g., \'VGSR 3459\' or \'FBADS-733-103901503\')"',
        'invoice_date': '"invoice_date": "Date in YYYY-MM-DD format"',
        'invoice_value': '"invoice_value": 123.45 (total amount as a number, the GROSS total with VAT included)',
        'customer_vat': '"customer_vat": "RO12345678" (VAT/CUI of the buyer/client, normalized with country code and no spaces)',
        'supplier': '"supplier": "Name of the company issuing the invoice"',
        'supplier_vat': '"supplier_vat": "RO12345678" (VAT/CUI of the seller, normalized)',
        'currency': '"currency": "RON/EUR/USD"'
    }

    fields_to_extract = [field_descriptions.get(f, f'"{f}": "value"') for f in missing_fields if f in field_descriptions]

    if not fields_to_extract:
        return {}

    prompt = f"""Analyze this invoice and extract ONLY the following specific fields. Return ONLY a valid JSON object.

Extract these fields:
{{
    {','.join(fields_to_extract)}
}}

IMPORTANT:
- For invoice_value, extract the TOTAL amount (with VAT) as a number
- For VAT numbers (customer_vat, supplier_vat), normalize format: COUNTRYCODE + NUMBERS, no spaces (e.g., "RO50022994")
- For invoice_number, include any series/prefix (e.g., "VGSR 3459" not just "3459")
- For invoice_date, use YYYY-MM-DD format
- Look carefully at ALL pages - customer info is often in the footer of the last page
- If you cannot find a field, use null
- Return ONLY the JSON object, no other text"""

    content.append({"type": "text", "text": prompt})

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[
            {"role": "user", "content": content}
        ]
    )

    # Parse the response
    response_text = response.content[0].text.strip()

    try:
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]

        result = json.loads(response_text)

        # Post-process VAT numbers
        if result.get('supplier_vat'):
            result['supplier_vat'] = normalize_vat_number(result['supplier_vat'])
        if result.get('customer_vat'):
            result['customer_vat'] = normalize_vat_number(result['customer_vat'])

        # Post-process date
        if result.get('invoice_date'):
            result['invoice_date'] = parse_romanian_date(result['invoice_date'])

        return result
    except json.JSONDecodeError:
        return {}


def apply_template(template: dict, text: str = None) -> dict:
    """
    Apply a template to return fixed invoice data.
    Template contains pre-configured values that bypass AI parsing.

    For format-based templates (template_type='format'), supplier info
    will be extracted from text using regex patterns.

    Returns a dict with the same structure as parse_invoice() but with
    template values. Variable fields (invoice_number, date, value) should
    be filled in by the user manually or via regex extraction.
    """
    result = {
        'supplier': template.get('supplier'),
        'supplier_vat': template.get('supplier_vat'),
        'customer': None,  # Will be matched via customer_vat
        'customer_vat': template.get('customer_vat'),
        'invoice_number': None,  # User must enter this
        'invoice_date': None,  # User must enter this
        'invoice_value': None,  # User must enter this
        'currency': template.get('currency', 'RON'),
        'description': template.get('description'),
        'raw_text': None,
        'template_used': template.get('name'),
        'template_type': template.get('template_type', 'fixed')
    }

    # For format-based templates, extract supplier info from text using regex
    if template.get('template_type') == 'format' and text:
        # Extract supplier name
        if template.get('supplier_regex'):
            try:
                match = re.search(template['supplier_regex'], text, re.IGNORECASE)
                if match:
                    result['supplier'] = match.group(1) if match.groups() else match.group(0)
                    result['supplier'] = result['supplier'].strip()
            except Exception:
                pass

        # Extract supplier VAT
        if template.get('supplier_vat_regex'):
            try:
                match = re.search(template['supplier_vat_regex'], text, re.IGNORECASE)
                if match:
                    vat = match.group(1) if match.groups() else match.group(0)
                    result['supplier_vat'] = normalize_vat_number(vat)
            except Exception:
                pass

        # Extract currency
        if template.get('currency_regex'):
            try:
                match = re.search(template['currency_regex'], text, re.IGNORECASE)
                if match:
                    result['currency'] = (match.group(1) if match.groups() else match.group(0)).upper()
            except Exception:
                pass

    # Extract customer VAT using regex (for all template types when regex is provided)
    if text and template.get('customer_vat_regex') and not result.get('customer_vat'):
        try:
            match = re.search(template['customer_vat_regex'], text, re.IGNORECASE | re.DOTALL)
            if match:
                # Get the first non-None group
                vat = None
                for g in match.groups():
                    if g:
                        vat = g
                        break
                if vat:
                    result['customer_vat'] = normalize_vat_number(vat)
        except Exception:
            pass

    return result


def parse_romanian_date(date_str: str) -> str:
    """
    Parse various date formats and convert to YYYY-MM-DD.
    Handles formats like:
    - Romanian: '22 nov. 2025', '22 noiembrie 2025'
    - English: 'Nov 21, 2025', 'November 1, 2025'
    - Numeric: '22.11.2025', '22/11/2025', '22-11-2025'
    - ISO: '2025-11-22'
    """
    # Month names (Romanian and English)
    months = {
        # Romanian
        'ian': '01', 'ianuarie': '01',
        'feb': '02', 'februarie': '02',
        'mar': '03', 'martie': '03',
        'apr': '04', 'aprilie': '04',
        'mai': '05',
        'iun': '06', 'iunie': '06',
        'iul': '07', 'iulie': '07',
        'aug': '08', 'august': '08',
        'sep': '09', 'septembrie': '09', 'sept': '09',
        'oct': '10', 'octombrie': '10',
        'noi': '11', 'noiembrie': '11',
        'dec': '12', 'decembrie': '12',
        # English
        'jan': '01', 'january': '01',
        'february': '02',
        'march': '03',
        'april': '04',
        'may': '05',
        'jun': '06', 'june': '06',
        'jul': '07', 'july': '07',
        'august': '08',
        'september': '09',
        'october': '10',
        'nov': '11', 'november': '11',
        'december': '12',
    }

    date_str = date_str.strip()

    # Try YYYY-MM-DD (already correct format) - check first
    iso_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
    if iso_match:
        return date_str

    # Try English format: "Nov 21, 2025" or "November 1, 2025"
    en_match = re.match(r'(\w+)\s+(\d{1,2}),?\s*(\d{4})', date_str)
    if en_match:
        month_str = en_match.group(1).lower().rstrip('.')
        day = en_match.group(2).zfill(2)
        year = en_match.group(3)

        month = months.get(month_str)
        if month:
            return f"{year}-{month}-{day}"

    # Try Romanian/European format: "22 nov. 2025" or "22 noiembrie 2025"
    ro_match = re.match(r'(\d{1,2})\s+(\w+)\.?\s*,?\s*(\d{4})', date_str)
    if ro_match:
        day = ro_match.group(1).zfill(2)
        month_str = ro_match.group(2).lower().rstrip('.')
        year = ro_match.group(3)

        month = months.get(month_str)
        if month:
            return f"{year}-{month}-{day}"

    # Try DD.MM.YYYY or DD/MM/YYYY or DD-MM-YYYY
    numeric_match = re.match(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})', date_str)
    if numeric_match:
        day = numeric_match.group(1).zfill(2)
        month = numeric_match.group(2).zfill(2)
        year = numeric_match.group(3)
        return f"{year}-{month}-{day}"

    return date_str  # Return as-is if can't parse


def parse_invoice_value(value_str: str) -> float:
    """
    Parse invoice value from various formats.
    Handles: '874,90 RON', '1.234,56', '1234.56', '1,234.56', '3 600.99'
    """
    # Remove currency codes and whitespace at end
    value_str = re.sub(r'[A-Z]{3}\s*$', '', value_str.strip())
    value_str = re.sub(r'\s*(?:Lei|RON|EUR|USD)\s*$', '', value_str, flags=re.IGNORECASE)
    value_str = value_str.strip()

    # Remove spaces used as thousand separators (e.g., "3 600.99" -> "3600.99")
    value_str = re.sub(r'(\d)\s+(\d)', r'\1\2', value_str)

    # Detect format based on decimal separator position
    # European format: 1.234,56 (dot as thousand sep, comma as decimal)
    # US format: 1,234.56 (comma as thousand sep, dot as decimal)

    if ',' in value_str and '.' in value_str:
        # Both separators present - determine which is decimal
        last_comma = value_str.rfind(',')
        last_dot = value_str.rfind('.')

        if last_comma > last_dot:
            # European: 1.234,56
            value_str = value_str.replace('.', '').replace(',', '.')
        else:
            # US: 1,234.56
            value_str = value_str.replace(',', '')
    elif ',' in value_str:
        # Only comma - could be European decimal or thousand sep
        # Check if 2 digits after comma (likely decimal)
        if re.search(r',\d{2}$', value_str):
            value_str = value_str.replace(',', '.')
        else:
            value_str = value_str.replace(',', '')

    # Remove any remaining non-numeric chars except dot
    value_str = re.sub(r'[^\d.]', '', value_str)

    return float(value_str)


def get_patterns_from_templates() -> tuple[list, list, list]:
    """
    Load regex patterns from all templates in the database.
    Returns tuple of (invoice_number_patterns, date_patterns, value_patterns).
    Each pattern from templates is added to the beginning of the list (higher priority).
    """
    try:
        from database import get_all_invoice_templates
        templates = get_all_invoice_templates()

        number_patterns = []
        date_patterns = []
        value_patterns = []

        for t in templates:
            if t.get('invoice_number_regex'):
                pattern = t['invoice_number_regex']
                if pattern not in number_patterns:
                    number_patterns.append(pattern)
            if t.get('invoice_date_regex'):
                pattern = t['invoice_date_regex']
                if pattern not in date_patterns:
                    date_patterns.append(pattern)
            if t.get('invoice_value_regex'):
                pattern = t['invoice_value_regex']
                if pattern not in value_patterns:
                    value_patterns.append(pattern)

        return number_patterns, date_patterns, value_patterns
    except Exception:
        return [], [], []


def parse_with_template(file_path: str, template: dict) -> dict:
    """
    Parse invoice using template regex patterns.
    Falls back to default patterns if no custom regex is provided.
    Patterns are dynamically loaded from all templates in the database.
    """
    import PyPDF2

    # Try to extract text from PDF for regex matching
    ext = os.path.splitext(file_path)[1].lower()
    text = ''

    if ext == '.pdf':
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ''
        except Exception:
            pass

    # Apply template with extracted text (for format-based templates)
    result = apply_template(template, text)

    if not text:
        return result

    result['raw_text'] = text[:2000]  # Store first 2000 chars

    # Load patterns from all templates in database (dynamic patterns)
    db_number_patterns, db_date_patterns, db_value_patterns = get_patterns_from_templates()

    # Base fallback patterns for common invoice formats
    base_invoice_number_patterns = [
        r'Factura\s+(\d+/\d+)',  # OLX/Autovit: Factura 2026/1200126972
        r'([A-Z]{2,4}\d{4,})\s+FACTURA',  # SmartBill: BRN0510 FACTURA, SI10316 FACTURA
        r'Seria\s+([A-Z]+)\s+nr\.?\s*(\d+)',  # Canopy: Seria CPY nr. 15562
        r'Serie:\s*([A-Z]+).*?Num[aă]r:\s*(\d+)',  # FirstClean: Serie: FCL ... Număr: 2701
        r'Invoice\s+no\.?:?\s*(\d+)',  # Dreamstime: Invoice no.: 28225130
        r'Factura\s+nr\.?\s*([A-Z0-9\-]+)',  # Romanian: Factura nr. FBADS-123
        r'Invoice\s+(?:No\.?|Number|#)\s*:?\s*([A-Z0-9\-]+)',  # English
        r'Nr\.\s*factur[aă]\s*:?\s*([A-Z0-9\-]+)',  # Romanian alt
        r'ID\s+tranzac[tț]ie\s+(\d+\-\d+)',  # Meta: ID tranzacţie 25389473860740088-...
    ]

    base_date_patterns = [
        r'Data factura:\s*(\d{2}\.\d{2}\.\d{4})',  # OLX/Autovit: Data factura: 05.09.2025
        r'Data\s+emiterii:\s*(\d{2}/\d{2}/\d{4})',  # SmartBill: Data emiterii: 31/10/2025
        r'Dat[aă]:\s*(\d{2}-\d{2}-\d{4})',  # FirstClean: Dată: 02-12-2025
        r'Data\s+\(zi/luna/an\):\s*(\d{2}/\d{2}/\d{4})',  # Canopy: Data (zi/luna/an): 02/12/2025
        r'Date:\s*(\d{2}/\d{2}/\d{4})',  # Dreamstime: Date: 08/07/2025
        r'Data\s+facturii[/:]?\s*(\d{1,2}\s+\w+\.?\s*,?\s*\d{4})',  # Romanian: Data facturii 22 nov. 2025
        r'(\d{1,2}\s+\w{3}\.?\s*\d{4})',  # Meta: 22 nov. 2025
        r'Data\s+facturii[/:]?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})',  # Data facturii 22.11.2025
        r'Invoice\s+[Dd]ate\s*:?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})',
        r'Date\s*:?\s*(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})',
    ]

    base_value_patterns = [
        r'TOTAL\s+PLATA\s+([\d\s.,]+)\s*(?:Lei|RON)?',  # SmartBill: TOTAL PLATA 3 600.99 Lei
        r'Total\s+plata\s+([\d\s.,]+)',  # Canopy: Total plata 3386.94
        r'Efectuat[aă]?\s*([\d.,]+)\s*(?:RON|EUR|USD)?',  # Meta format: Efectuată 874,90 RON
        r'Total\s+([\d.,]+)\s*(?:RON|EUR|USD|Lei)?',  # Generic: Total 2.758,91
        r'Total\s*:?\s*([\d.,]+)\s*(?:RON|EUR|USD)?',
        r'Total\s+(?:de\s+plat[aă]|amount)\s*:?\s*([\d.,]+)',
        r'Valoare\s+total[aă]?\s*:?\s*([\d.,]+)',
        r'Amount\s+Due\s*:?\s*([\d.,]+)',
        r'(\d+(?:[.,]\d+)?)\s*(?:RON|EUR|USD)\s*$',  # Dreamstime: 114 RON at end of line
    ]

    # Combine database patterns (priority) with base patterns (fallback)
    # Remove duplicates while preserving order
    def merge_patterns(db_patterns: list, base_patterns: list) -> list:
        seen = set()
        result = []
        for p in db_patterns + base_patterns:
            if p not in seen:
                seen.add(p)
                result.append(p)
        return result

    default_invoice_number_patterns = merge_patterns(db_number_patterns, base_invoice_number_patterns)
    default_date_patterns = merge_patterns(db_date_patterns, base_date_patterns)
    default_value_patterns = merge_patterns(db_value_patterns, base_value_patterns)

    # Try to extract invoice number
    invoice_number_regex = template.get('invoice_number_regex')
    if invoice_number_regex:
        patterns_to_try = [invoice_number_regex]
    else:
        patterns_to_try = default_invoice_number_patterns

    for pattern in patterns_to_try:
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                groups = match.groups()
                if len(groups) > 1:
                    # Multiple groups - concatenate them (e.g., "CPY" + "15562" -> "CPY15562")
                    result['invoice_number'] = ''.join(g for g in groups if g)
                elif groups:
                    result['invoice_number'] = groups[0]
                else:
                    result['invoice_number'] = match.group(0)
                break
        except Exception:
            pass

    # Try to extract invoice date
    invoice_date_regex = template.get('invoice_date_regex')
    if invoice_date_regex:
        patterns_to_try = [invoice_date_regex]
    else:
        patterns_to_try = default_date_patterns

    for pattern in patterns_to_try:
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1) if match.groups() else match.group(0)
                # Use smart date parser
                result['invoice_date'] = parse_romanian_date(date_str)
                break
        except Exception:
            pass

    # If no date found yet, try general date detection in header area
    if not result.get('invoice_date'):
        # Look for date near "Data facturii" or in first 500 chars
        header_text = text[:500]
        date_match = re.search(r'(\d{1,2}\s+\w{3,}\.?\s*,?\s*\d{4})', header_text)
        if date_match:
            result['invoice_date'] = parse_romanian_date(date_match.group(1))

    # Try to extract invoice value
    invoice_value_regex = template.get('invoice_value_regex')
    if invoice_value_regex:
        patterns_to_try = [invoice_value_regex]
    else:
        patterns_to_try = default_value_patterns

    for pattern in patterns_to_try:
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1) if match.groups() else match.group(0)
                result['invoice_value'] = parse_invoice_value(value_str)
                break
        except Exception:
            pass

    return result


def parse_invoice_with_template_from_bytes(file_bytes: bytes, filename: str, template: dict) -> dict:
    """Parse invoice from uploaded file bytes using a template."""
    ext = os.path.splitext(filename)[1].lower()

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        return parse_with_template(tmp_path, template)
    finally:
        os.unlink(tmp_path)


def extract_text_from_file(file_path: str) -> str:
    """Extract text from PDF or return empty string for images."""
    import PyPDF2

    ext = os.path.splitext(file_path)[1].lower()
    text = ''

    if ext == '.pdf':
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ''
        except Exception:
            pass

    return text


def extract_vat_numbers_from_text(text: str) -> list[str]:
    """
    Extract all potential VAT numbers from text.
    Returns list of normalized VAT numbers found.
    """
    vat_numbers = []

    # Pattern to match various VAT formats
    # Matches: RO12345678, IE9692928F, VAT: RO12345678, CUI: 12345678, etc.
    patterns = [
        r'VAT[^:]*?[:\s]+([A-Z]{2}[\s]?\d+[A-Z]*)',  # VAT Reg. No. IE9692928F or VAT: RO12345678
        r'CUI[:\s]*([A-Z]{0,2}[\s]?\d+)',  # CUI: 12345678 or CUI: RO12345678
        r'CIF[:\s]*([A-Z]{0,2}[\s]?\d+)',  # CIF: RO12345678
        r'\b([A-Z]{2}\d{6,12}[A-Z]?)\b',  # Direct VAT like RO12345678, IE9692928F
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            normalized = normalize_vat_number(match)
            if normalized and normalized not in vat_numbers:
                vat_numbers.append(normalized)

    return vat_numbers


def extract_customer_vat_from_text(text: str, supplier_vat: str = None) -> Optional[str]:
    """
    Extract customer VAT from invoice text using regex patterns.
    This is used as a fallback when AI doesn't extract customer_vat.

    Args:
        text: Extracted text from the invoice
        supplier_vat: Optional supplier VAT to exclude from results

    Returns:
        Normalized customer VAT or None if not found
    """
    if not text:
        return None

    # Customer VAT patterns - look for VAT numbers near customer/buyer indicators
    # These patterns prioritize customer-related VAT numbers
    customer_patterns = [
        # Romanian customer patterns
        r'(?:client|cumparator|buyer|bill\s*to|factura\s*pentru)[^A-Z]*?(?:CUI|CIF|VAT)[:\s]*([A-Z]{0,2}[\s]?\d{6,12})',
        r'(?:client|cumparator|buyer|bill\s*to)[^A-Z]*?([A-Z]{2}\d{6,12})',
        # Generic labeled VAT patterns (customer section)
        r'C\.?I\.?F\.?[:\s]*([A-Z]{0,2}[\s]?\d{6,12})',  # C.I.F.: RO50186814
        r'CUI[:\s]*([A-Z]{0,2}[\s]?\d{6,12})',  # CUI: RO50186814
        r'(?:VAT|TVA)[^A-Z]*?[:\s]+([A-Z]{2}[\s]?\d{6,12})',  # VAT: RO50186814
        r'Cod\s+fiscal[:\s]*([A-Z]{0,2}[\s]?\d{6,12})',  # Cod fiscal: RO50186814
        # Direct RO VAT pattern (common in Romanian invoices)
        r'\b(RO\d{6,10})\b',  # Direct RO12345678 pattern
    ]

    # Normalize supplier VAT for comparison
    normalized_supplier_vat = normalize_vat_number(supplier_vat) if supplier_vat else None

    found_vats = []
    for pattern in customer_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            normalized = normalize_vat_number(match)
            if normalized and normalized not in found_vats:
                # Skip if this is the supplier VAT
                if normalized_supplier_vat and normalized == normalized_supplier_vat:
                    continue
                # Skip if it's just the numbers matching supplier
                if normalized_supplier_vat:
                    supplier_numbers = re.sub(r'[^0-9]', '', normalized_supplier_vat)
                    vat_numbers = re.sub(r'[^0-9]', '', normalized)
                    if supplier_numbers and vat_numbers and supplier_numbers == vat_numbers:
                        continue
                found_vats.append(normalized)

    # Return the first valid customer VAT found
    # Prefer VATs that start with RO (Romanian customers)
    for vat in found_vats:
        if vat.startswith('RO'):
            return vat

    return found_vats[0] if found_vats else None


def find_matching_template(text: str, templates: list[dict]) -> Optional[dict]:
    """
    Find a template that matches the invoice based on supplier VAT or text markers.

    Args:
        text: Extracted text from the invoice
        templates: List of all available templates

    Returns:
        Matching template dict or None if no match found
    """
    if not text or not templates:
        return None

    text_lower = text.lower()

    # First, check for format-based templates with text markers (like eFactura)
    for template in templates:
        if template.get('template_type') == 'format':
            template_supplier_vat = template.get('supplier_vat', '')
            # For format templates, check if the marker text exists in the invoice
            # e.g., "RO eFactura" or "efactura"
            if template_supplier_vat:
                marker = template_supplier_vat.lower()
                # Check for exact marker or partial match
                if marker in text_lower or marker.replace(' ', '') in text_lower.replace(' ', ''):
                    return template

    # Extract all VAT numbers from the invoice text
    found_vats = extract_vat_numbers_from_text(text)

    if not found_vats:
        return None

    # Try to match against template supplier_vat (for fixed templates)
    for template in templates:
        template_supplier_vat = template.get('supplier_vat')
        if not template_supplier_vat:
            continue

        # Skip format templates (already checked above)
        if template.get('template_type') == 'format':
            continue

        # Normalize template VAT for comparison
        normalized_template_vat = normalize_vat_number(template_supplier_vat)
        if not normalized_template_vat:
            continue

        # Check if any found VAT matches the template's supplier VAT
        for found_vat in found_vats:
            # Exact match
            if found_vat == normalized_template_vat:
                return template

            # Numbers-only match (handles cases like '9692628' matching 'IE9692628')
            found_numbers = re.sub(r'[^0-9]', '', found_vat)
            template_numbers = re.sub(r'[^0-9]', '', normalized_template_vat)

            if found_numbers and template_numbers and found_numbers == template_numbers:
                return template

    return None


def generate_template_from_invoice(file_bytes: bytes, filename: str, api_key: Optional[str] = None) -> dict:
    """
    Use AI to analyze a sample invoice and generate regex patterns for a new template.

    This function:
    1. Extracts text from the invoice using PyPDF2
    2. Uses Claude to analyze the invoice and generate:
       - Supplier info (name, VAT)
       - Customer VAT pattern
       - Regex patterns for invoice number, date, and value
       - Currency

    Returns a dict with template fields ready to be saved.
    """
    import PyPDF2

    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Please set the environment variable or pass api_key parameter.")

    client = anthropic.Anthropic(api_key=api_key)

    ext = os.path.splitext(filename)[1].lower()

    # Create temp file
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # Extract text from PDF
        text = ''
        if ext == '.pdf':
            try:
                with open(tmp_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text += page.extract_text() or ''
            except Exception:
                pass

        # Also get image for visual analysis
        if ext == '.pdf':
            images = pdf_to_images(tmp_path)
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            images = [encode_image_to_base64(tmp_path)]
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        # Build message content with images
        content = []
        for image_data, media_type in images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data
                }
            })

        # Include extracted text for reference
        text_sample = text[:3000] if text else "No text could be extracted"

        content.append({
            "type": "text",
            "text": f"""Analyze this invoice and generate regex patterns for parsing similar invoices from this supplier.

EXTRACTED TEXT (for regex pattern creation):
```
{text_sample}
```

Return ONLY a valid JSON object with these exact keys:

{{
    "name": "Template name based on supplier (e.g., 'Meta Ads Template', 'OLX Invoice Template')",
    "template_type": "fixed",
    "supplier": "Supplier/vendor company name",
    "supplier_vat": "Supplier VAT number normalized (e.g., RO12345678, IE9692928F)",
    "customer_vat_regex": "Python regex pattern with capture group to extract customer VAT from the text",
    "currency": "RON/EUR/USD",
    "description": "Brief description of what this template is for",
    "invoice_number_regex": "Python regex pattern with capture group to extract invoice number from the text",
    "invoice_date_regex": "Python regex pattern with capture group to extract invoice date from the text",
    "invoice_value_regex": "Python regex pattern with capture group to extract total amount from the text",
    "date_format": "Expected date format like %d.%m.%Y or %d/%m/%Y or %d %b. %Y"
}}

CRITICAL REGEX GUIDELINES:
1. Use capture groups () to capture the actual values
2. The patterns must work with Python's re.search() on the EXTRACTED TEXT above
3. Escape special regex characters: \\. for literal dot, \\( for literal parenthesis
4. Use \\s* for flexible whitespace, \\d+ for digits
5. Test your patterns mentally against the extracted text
6. For invoice numbers with series (e.g., "Seria CPY nr. 15562"), capture both parts: Seria\\s+([A-Z]+)\\s+nr\\.?\\s*(\\d+)
7. For Romanian dates like "22 nov. 2025", use: (\\d{{1,2}}\\s+\\w{{3}}\\.?\\s*\\d{{4}})
8. For values, capture the number part: Total\\s+([\\d.,]+)

EXAMPLES OF GOOD PATTERNS:
- Invoice number "Factura 2026/1200126972": Factura\\s+(\\d+/\\d+)
- Invoice number "Seria CPY nr. 15562": Seria\\s+([A-Z]+)\\s+nr\\.?\\s*(\\d+)
- Invoice number "FBADS-416-105093174": Factura\\s+nr\\.?\\s*(FBADS-\\d+-\\d+)
- Date "Data factura: 05.09.2025": Data\\s+factura:\\s*(\\d{{2}}\\.\\d{{2}}\\.\\d{{4}})
- Date "22 nov. 2025": (\\d{{1,2}}\\s+\\w{{3}}\\.?\\s*,?\\s*\\d{{4}})
- Date "Data emiterii: 31/10/2025": Data\\s+emiterii:\\s*(\\d{{2}}/\\d{{2}}/\\d{{4}})
- Value "Total 2.758,91 RON": Total\\s+([\\d.,]+)\\s*(?:RON|EUR)?
- Value "Efectuată 874,90 RON": Efectuat[aă]?\\s*([\\d.,]+)\\s*RON
- Value "TOTAL PLATA 3 600.99 Lei": TOTAL\\s+PLATA\\s+([\\d\\s.,]+)\\s*Lei
- Customer VAT "CIF: RO50022994": CIF:\\s*(RO\\d+)
- Customer VAT "C.I.F.: RO50022994": C\\.I\\.F\\.:\\s*(RO\\d+)
- Customer VAT "VAT: RO50186814": VAT:\\s*(RO\\d+)

Return ONLY the JSON, no other text."""
        })

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": content}
            ]
        )

        # Parse the response
        response_text = response.content[0].text.strip()

        # Try to extract JSON from response
        try:
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0]
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0]

            result = json.loads(response_text)

            # Normalize VAT numbers
            if result.get('supplier_vat'):
                result['supplier_vat'] = normalize_vat_number(result['supplier_vat'])
            if result.get('customer_vat'):
                result['customer_vat'] = normalize_vat_number(result['customer_vat'])

            # Add the raw text for verification
            result['_extracted_text'] = text[:2000]
            result['_ai_generated'] = True

            return result

        except json.JSONDecodeError as e:
            return {
                'name': None,
                'template_type': 'fixed',
                'supplier': None,
                'supplier_vat': None,
                'customer_vat_regex': None,
                'currency': 'RON',
                'description': None,
                'invoice_number_regex': None,
                'invoice_date_regex': None,
                'invoice_value_regex': None,
                'date_format': '%d.%m.%Y',
                '_error': str(e),
                '_raw_response': response_text,
                '_extracted_text': text[:2000],
                '_ai_generated': True
            }
    finally:
        os.unlink(tmp_path)


def auto_detect_and_parse(file_bytes: bytes, filename: str, templates: list[dict], api_key: Optional[str] = None) -> dict:
    """
    Automatically detect the appropriate template and parse the invoice.

    1. First extracts text from the file
    2. Tries to find a matching template based on supplier VAT
    3. If found, uses template-based parsing (fast, no AI)
    4. If not found, falls back to AI parsing

    Args:
        file_bytes: The uploaded file content
        filename: Original filename
        templates: List of all available templates
        api_key: Optional Anthropic API key

    Returns:
        Parsed invoice data with 'auto_detected_template' field if template was matched
    """
    ext = os.path.splitext(filename)[1].lower()

    # Create temp file for processing
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # Extract text from the file
        text = extract_text_from_file(tmp_path)

        # Try to find a matching template
        matched_template = find_matching_template(text, templates)

        if matched_template:
            # Use template-based parsing
            result = parse_with_template(tmp_path, matched_template)
            result['auto_detected_template'] = matched_template.get('name')
            result['auto_detected_template_id'] = matched_template.get('id')

            # Check for critical missing fields - use AI to fill gaps
            missing_fields = []
            if not result.get('invoice_number'):
                missing_fields.append('invoice_number')
            if not result.get('invoice_date'):
                missing_fields.append('invoice_date')
            if not result.get('invoice_value'):
                missing_fields.append('invoice_value')
            if not result.get('customer_vat'):
                missing_fields.append('customer_vat')

            if missing_fields:
                # Use AI to extract only the missing fields
                try:
                    ai_result = extract_missing_fields_with_ai(tmp_path, missing_fields, api_key)
                    for field in missing_fields:
                        if ai_result.get(field) and not result.get(field):
                            result[field] = ai_result[field]
                            result[f'{field}_source'] = 'ai_fallback'
                except Exception as e:
                    # AI fallback failed, continue with template results
                    print(f"AI fallback failed for missing fields: {e}")

            return result
        else:
            # Fall back to AI parsing
            result = parse_invoice(tmp_path, api_key)
            result['auto_detected_template'] = None
            result['auto_detected_template_id'] = None

            # Fallback: If AI didn't extract customer_vat, try regex extraction
            if not result.get('customer_vat') and text:
                supplier_vat = result.get('supplier_vat')
                fallback_customer_vat = extract_customer_vat_from_text(text, supplier_vat)
                if fallback_customer_vat:
                    result['customer_vat'] = fallback_customer_vat
                    result['customer_vat_source'] = 'regex_fallback'

            return result
    finally:
        os.unlink(tmp_path)


def match_campaigns_with_ai(source_campaigns: list, target_campaigns: list, api_key: str = None) -> dict:
    """
    Use AI to match campaign names from source to target based on semantic similarity.

    Args:
        source_campaigns: List of campaign names from the source (pattern) invoice
        target_campaigns: List of campaign names from the target invoice to apply pattern to
        api_key: Optional Anthropic API key

    Returns:
        Dictionary mapping target campaign index to source campaign index
        e.g., {0: 1, 1: 0, 2: 2} means target[0] matches source[1], target[1] matches source[0], etc.
    """
    if not api_key:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Match advertising campaign names from a source list to a target list based on semantic similarity.
The campaigns are typically advertising campaigns with similar naming conventions like "[CA] Leads - Brand Name" or "CAMPAIGN NAME - DESCRIPTION".

SOURCE CAMPAIGNS (from the pattern invoice):
{json.dumps(source_campaigns, indent=2)}

TARGET CAMPAIGNS (to apply the pattern to):
{json.dumps(target_campaigns, indent=2)}

For each TARGET campaign, find the best matching SOURCE campaign based on:
1. Similar campaign type (e.g., "Leads", "Traffic", "Awareness")
2. Similar brand/product (e.g., "Mazda CX80" matches "Mazda CX60", "Volvo" matches "Volvo")
3. Similar structure/format

Return a JSON object mapping each target index to the best matching source index.
If a target has no good match, map it to the first source index (0) as a fallback.

Example response format:
{{"0": 1, "1": 0, "2": 2, "3": 0}}

IMPORTANT: Return ONLY the JSON object, no explanation or additional text."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract JSON from response
        response_text = response.content[0].text.strip()

        # Try to parse the response as JSON
        try:
            # Remove any markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)
            # Convert string keys to int if needed
            return {int(k): int(v) for k, v in result.items()}
        except json.JSONDecodeError:
            # Fallback: return sequential mapping
            return {i: i % len(source_campaigns) for i in range(len(target_campaigns))}

    except Exception as e:
        print(f"AI campaign matching error: {e}")
        # Fallback: return sequential mapping (cycle through pattern)
        return {i: i % len(source_campaigns) for i in range(len(target_campaigns))}
