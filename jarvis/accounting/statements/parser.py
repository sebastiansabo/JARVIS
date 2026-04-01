"""Bank Statement Parser for UniCredit PDF statements.

Extracts transactions from UniCredit bank statement PDFs.
Falls back to OCR (tesseract) for vector-path PDFs where PyPDF2 returns empty text.
OCR text has a column-based layout that requires separate parsing logic.
"""
import re
import logging
from datetime import datetime
from io import BytesIO
from typing import Optional

import PyPDF2

logger = logging.getLogger('jarvis.statements.parser')

# Header extraction patterns (for PyPDF2 inline text)
COMPANY_PATTERN = re.compile(r'Titular de cont\s+(.+?)(?:\n|CUI)', re.IGNORECASE)
CUI_PATTERN = re.compile(r'CUI/CNP\s+(\d+)')
ACCOUNT_PATTERN = re.compile(r'Cont ales\s+(RO\d{2}\s*[A-Z]{4}\s*[\d\s]+)')
PERIOD_PATTERN = re.compile(r'De la\s+Pana la.*?(\d{2}\.\d{2}\.\d{4})\s+(\d{2}\.\d{2}\.\d{4})', re.DOTALL)

# Balance extraction
OPENING_BALANCE_PATTERN = re.compile(r'Sold deschidere\s+\d{2}\.\d{2}\.\d{4}\s+([\d.,]+)\s*RON')
CLOSING_BALANCE_PATTERN = re.compile(r'Sold inchidere\s+\d{2}\.\d{2}\.\d{4}\s+([\d.,]+)\s*RON')
CREDIT_TOTAL_PATTERN = re.compile(r'Credit total.*?\(([\d]+)\)\s+([\d.,]+)\s*RON')
DEBIT_TOTAL_PATTERN = re.compile(r'Debit total.*?\(([\d]+)\)\s+([\d.,]+)\s*RON')

# Card number pattern (masked)
CARD_PATTERN = re.compile(r'Card[:\s]*([\d]{4}-[\dX]{2}XX-XXXX-[\d]{4})')

# Auth code pattern
AUTH_CODE_PATTERN = re.compile(r'Auth code\s+(\d+)')

# Foreign currency with exchange rate
FOREX_PATTERN = re.compile(r'([\d.,]+)\s*(EUR|USD)\s*@([\d.,]+)\s*EUR-RON')


def parse_value(value_str: str) -> float:
    """Parse European number format (1.234,56) to float."""
    if not value_str:
        return 0.0
    # Remove spaces
    value_str = value_str.replace(' ', '')
    # Handle European format: 1.234,56 -> 1234.56
    if ',' in value_str and '.' in value_str:
        value_str = value_str.replace('.', '').replace(',', '.')
    elif ',' in value_str:
        value_str = value_str.replace(',', '.')
    try:
        return float(value_str)
    except ValueError:
        logger.warning(f'Could not parse value: {value_str}')
        return 0.0


def parse_date(date_str: str) -> Optional[str]:
    """Parse DD.MM.YYYY to YYYY-MM-DD."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), '%d.%m.%Y')
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        logger.warning(f'Could not parse date: {date_str}')
        return None


def extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, bool]:
    """Extract all text from a PDF file.

    Tries PyPDF2 first; falls back to OCR (pdf2image + tesseract)
    for vector-path PDFs that contain no extractable text.

    Returns:
        (text, used_ocr) tuple
    """
    reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or '')
    text = '\n'.join(text_parts)

    # If PyPDF2 got meaningful text, use it
    if text.strip():
        return text, False

    # Fall back to OCR for vector-path PDFs
    logger.info('PyPDF2 returned empty text, falling back to OCR')
    try:
        from pdf2image import convert_from_bytes
        import pytesseract

        images = convert_from_bytes(pdf_bytes, dpi=300)
        ocr_parts = []
        for img in images:
            ocr_parts.append(pytesseract.image_to_string(img, lang='eng'))
        return '\n'.join(ocr_parts), True
    except Exception as e:
        logger.error(f'OCR fallback failed: {e}')
        return '', True


# ============== PyPDF2 (inline) parsing ==============

def extract_header_info(text: str) -> dict:
    """Extract company and account information from statement header."""
    info = {
        'company_name': None,
        'company_cui': None,
        'account_number': None,
        'period_from': None,
        'period_to': None,
    }

    # Company name
    match = COMPANY_PATTERN.search(text)
    if match:
        info['company_name'] = match.group(1).strip()

    # CUI
    match = CUI_PATTERN.search(text)
    if match:
        info['company_cui'] = match.group(1).strip()

    # Account number (IBAN)
    match = ACCOUNT_PATTERN.search(text)
    if match:
        # Clean up IBAN - remove extra spaces
        iban = match.group(1).strip()
        info['account_number'] = re.sub(r'\s+', '', iban)

    # Period
    match = PERIOD_PATTERN.search(text)
    if match:
        info['period_from'] = parse_date(match.group(1))
        info['period_to'] = parse_date(match.group(2))

    return info


def extract_summary(text: str) -> dict:
    """Extract balance summary from statement."""
    summary = {
        'opening_balance': None,
        'closing_balance': None,
        'credit_count': 0,
        'credit_total': None,
        'debit_count': 0,
        'debit_total': None,
    }

    match = OPENING_BALANCE_PATTERN.search(text)
    if match:
        summary['opening_balance'] = parse_value(match.group(1))

    match = CLOSING_BALANCE_PATTERN.search(text)
    if match:
        summary['closing_balance'] = parse_value(match.group(1))

    match = CREDIT_TOTAL_PATTERN.search(text)
    if match:
        summary['credit_count'] = int(match.group(1))
        summary['credit_total'] = parse_value(match.group(2))

    match = DEBIT_TOTAL_PATTERN.search(text)
    if match:
        summary['debit_count'] = int(match.group(1))
        summary['debit_total'] = parse_value(match.group(2))

    return summary


def extract_transactions(text: str, header_info: dict, filename: str = None) -> list[dict]:
    """
    Extract individual transactions from statement text.

    UniCredit format (line by line):
    DD.MM.YYYY DD.MM.YYYY Description...
                         continued description...
                         Value Currency
                         -Value RON (for debits)
    """
    transactions = []

    # Split into lines for processing
    lines = text.split('\n')

    # Transaction state machine
    current_txn = None
    description_lines = []

    # Pattern for transaction start (two dates at line start)
    date_line_pattern = re.compile(r'^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}\.\d{2}\.\d{4})\s+(.*)$')

    # Pattern for value line (ends with currency and amount)
    value_pattern = re.compile(r'([\d.,]+)\s*(RON|EUR|USD)\s*$')

    # Pattern for RON conversion (negative debit)
    ron_debit_pattern = re.compile(r'-([\d.,]+)\s*RON\s*$')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines and headers
        if not line or 'printat de' in line.lower() or 'UniCredit Bank' in line:
            i += 1
            continue

        # Skip summary and header lines
        if any(skip in line for skip in ['Sold deschidere', 'Sold inchidere',
                                          'Credit total', 'Debit total',
                                          'Totalul tranzactiilor', 'Data inregistrarii',
                                          'Lista Tranzactii', 'Istoric',
                                          'Titular de cont', 'CUI/CNP', 'Cont ales',
                                          'CONT:', 'IBAN:', 'LA:UNICREDIT',
                                          'Nr op.:', 'pag.', 'Pagina']):
            i += 1
            continue

        # Check for new transaction (starts with two dates)
        date_match = date_line_pattern.match(line)
        if date_match:
            # Save previous transaction if exists
            if current_txn and description_lines:
                current_txn['description'] = ' '.join(description_lines)
                _finalize_transaction(current_txn, header_info, filename)
                if current_txn.get('amount') and _is_valid_amount(current_txn.get('amount')):
                    transactions.append(current_txn)

            # Start new transaction
            current_txn = {
                'transaction_date': parse_date(date_match.group(1)),
                'value_date': parse_date(date_match.group(2)),
                'amount': None,
                'currency': 'RON',
                'original_amount': None,
                'original_currency': None,
                'exchange_rate': None,
                'card_number': None,
                'auth_code': None,
            }
            description_lines = [date_match.group(3).strip()] if date_match.group(3).strip() else []
            i += 1
            continue

        # If we have a current transaction, collect description and look for value
        if current_txn is not None:
            # Check for RON debit value (negative)
            ron_match = ron_debit_pattern.search(line)
            if ron_match:
                current_txn['amount'] = -parse_value(ron_match.group(1))
                current_txn['currency'] = 'RON'
                i += 1
                continue

            # Check for value line (positive or foreign currency)
            value_match = value_pattern.search(line)
            if value_match:
                amount = parse_value(value_match.group(1))
                currency = value_match.group(2)

                # Check for foreign currency conversion
                forex_match = FOREX_PATTERN.search(line)
                if forex_match:
                    current_txn['original_amount'] = parse_value(forex_match.group(1))
                    current_txn['original_currency'] = forex_match.group(2)
                    current_txn['exchange_rate'] = parse_value(forex_match.group(3))
                    # The RON amount will come in next line as debit
                elif currency != 'RON':
                    # Foreign currency without conversion shown yet
                    current_txn['original_amount'] = amount
                    current_txn['original_currency'] = currency
                else:
                    # Credit in RON (positive)
                    if current_txn['amount'] is None:
                        current_txn['amount'] = amount
                        current_txn['currency'] = currency

                # Remove value from description
                desc_part = line[:value_match.start()].strip()
                if desc_part:
                    description_lines.append(desc_part)

                i += 1
                continue

            # Regular description line
            if line and not line.startswith('Data'):
                description_lines.append(line)

        i += 1

    # Don't forget last transaction
    if current_txn and description_lines:
        current_txn['description'] = ' '.join(description_lines)
        _finalize_transaction(current_txn, header_info, filename)
        if current_txn.get('amount') and _is_valid_amount(current_txn.get('amount')):
            transactions.append(current_txn)

    return transactions


# ============== OCR (column-based) parsing ==============
# OCR via tesseract extracts table columns separately:
#   - Left side: dates + descriptions
#   - Right columns: amounts, then currencies
# Header labels and values are also on separate lines.

def _extract_header_ocr(text: str) -> dict:
    """Extract header info from OCR text where labels and values are separated."""
    info = {
        'company_name': None,
        'company_cui': None,
        'account_number': None,
        'period_from': None,
        'period_to': None,
    }
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    for i, line in enumerate(lines):
        # IBAN line (RO + 4-letter bank code + digits)
        iban_match = re.match(r'(RO\d{2}\s*[A-Z]{4}[\d\s]+)', line)
        if iban_match and not info['account_number']:
            iban = iban_match.group(1).split('|')[0].strip()
            info['account_number'] = re.sub(r'\s+', '', iban)
            # Company name is the next non-empty, non-numeric, non-address line
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j]
                if (candidate and not re.match(r'^\d+$', candidate)
                        and not candidate.startswith('STR')):
                    info['company_name'] = candidate
                    break

        # CUI - standalone 5-10 digit line
        if re.match(r'^\d{5,10}$', line) and not info['company_cui']:
            info['company_cui'] = line

        # Period - two dates on one line (OCR may prefix with © or O)
        period_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}\.\d{2}\.\d{4})', line)
        if period_match and not info['period_from']:
            info['period_from'] = parse_date(period_match.group(1))
            info['period_to'] = parse_date(period_match.group(2))

    return info


def _extract_transactions_ocr(text: str, header_info: dict, filename: str = None) -> list[dict]:
    """Extract transactions from OCR text with column-based layout.

    OCR layout sections (in order):
      1. Transaction descriptions (between date lines, ends at "Sold deschidere")
      2. "Valoare Tranz." header, then standalone amounts
      3. "Valuta" header, then standalone currencies (RON/EUR/USD)
    Amounts and currencies match transactions by position (index).
    """
    lines = text.split('\n')
    date_pattern = re.compile(r'^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}\.\d{2}\.\d{4})\s*(.*)')
    amount_pattern = re.compile(r'^-?[\d.,]+$')
    currency_pattern = re.compile(r'^(RON|EUR|USD)$')

    # --- Phase 1: Extract transaction descriptions ---
    transactions = []
    current_txn = None
    desc_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Stop collecting transactions at summary section
        if 'Sold deschidere' in stripped:
            break

        date_match = date_pattern.match(stripped)
        if date_match:
            # Save previous transaction
            if current_txn is not None:
                current_txn['description'] = ' '.join(desc_lines)
                transactions.append(current_txn)

            current_txn = {
                'transaction_date': parse_date(date_match.group(1)),
                'value_date': parse_date(date_match.group(2)),
                'amount': None,
                'currency': 'RON',
                'original_amount': None,
                'original_currency': None,
                'exchange_rate': None,
                'card_number': None,
                'auth_code': None,
            }
            desc_lines = [date_match.group(3).strip()] if date_match.group(3).strip() else []
        elif current_txn is not None:
            desc_lines.append(stripped)

    # Last transaction
    if current_txn is not None:
        current_txn['description'] = ' '.join(desc_lines)
        transactions.append(current_txn)

    # --- Phase 2: Extract amounts (standalone numbers after "Valoare Tranz.") ---
    amounts = []
    in_amounts = False
    for line in lines:
        stripped = line.strip()
        if 'Valoare Tranz' in stripped:
            in_amounts = True
            continue
        if in_amounts:
            if stripped == 'Valuta':
                break
            if amount_pattern.match(stripped):
                amounts.append(stripped)

    # --- Phase 3: Extract currencies (after "Valuta") ---
    currencies = []
    in_currencies = False
    for line in lines:
        stripped = line.strip()
        if stripped == 'Valuta':
            in_currencies = True
            continue
        if in_currencies:
            if currency_pattern.match(stripped):
                currencies.append(stripped)
            elif stripped:
                break  # Non-currency line ends the section

    # --- Phase 4: Pair amounts/currencies to transactions by index ---
    for i, txn in enumerate(transactions):
        if i < len(amounts):
            val = amounts[i]
            if val.startswith('-'):
                txn['amount'] = -parse_value(val[1:])
            else:
                txn['amount'] = parse_value(val)
        if i < len(currencies):
            txn['currency'] = currencies[i]

        # Check for forex info in description
        forex_match = FOREX_PATTERN.search(txn.get('description', ''))
        if forex_match:
            txn['original_amount'] = parse_value(forex_match.group(1))
            txn['original_currency'] = forex_match.group(2)
            txn['exchange_rate'] = parse_value(forex_match.group(3))

        _finalize_transaction(txn, header_info, filename)

    return transactions


def _extract_summary_ocr(text: str) -> dict:
    """Extract balance summary from OCR text.

    In OCR layout, summary labels and their amounts are in separate columns.
    Labels: "Sold deschidere", "Credit total (N)", "Debit total (N)", "Sold inchidere"
    Amounts: "X.XXX,XX RON" lines at the end of the text.
    """
    summary = {
        'opening_balance': None,
        'closing_balance': None,
        'credit_count': 0,
        'credit_total': None,
        'debit_count': 0,
        'debit_total': None,
    }

    lines = [l.strip() for l in text.split('\n')]

    # Extract counts from summary labels
    for line in lines:
        credit_match = re.search(r'Credit total.*?\((\d+)\)', line)
        if credit_match:
            summary['credit_count'] = int(credit_match.group(1))
        debit_match = re.search(r'Debit total.*?\((\d+)\)', line)
        if debit_match:
            summary['debit_count'] = int(debit_match.group(1))

    # Summary amounts are the "X.XXX,XX RON" lines at the bottom of the text.
    # Order: opening_balance, credit_total, debit_total, net_total, closing_balance
    amount_ron_pattern = re.compile(r'^(-?[\d.,]+)\s*RON$')
    summary_amounts = []
    for line in reversed(lines):
        match = amount_ron_pattern.match(line)
        if match:
            summary_amounts.insert(0, match.group(1))
        elif line and summary_amounts:
            break  # Non-amount line after collecting some = done

    if len(summary_amounts) >= 5:
        summary['opening_balance'] = parse_value(summary_amounts[0])
        summary['credit_total'] = parse_value(summary_amounts[1])
        summary['debit_total'] = parse_value(summary_amounts[2].lstrip('-'))
        # summary_amounts[3] is net total (skip)
        summary['closing_balance'] = parse_value(summary_amounts[4])
    elif len(summary_amounts) >= 2:
        summary['opening_balance'] = parse_value(summary_amounts[0])
        summary['closing_balance'] = parse_value(summary_amounts[-1])

    return summary


# ============== Shared helpers ==============

def _is_valid_amount(amount: float) -> bool:
    """Check if amount is within reasonable bounds for a transaction."""
    if amount is None:
        return False
    abs_amount = abs(amount)
    # Reject amounts over 10 million (likely parsing errors like IBANs or balances)
    MAX_REASONABLE_AMOUNT = 10_000_000
    if abs_amount > MAX_REASONABLE_AMOUNT:
        logger.warning(f'Rejecting transaction with unreasonable amount: {amount}')
        return False
    return True


def _finalize_transaction(txn: dict, header_info: dict, filename: str = None):
    """Add header info and extract card/auth details from description."""
    # Add header info
    txn['company_name'] = header_info.get('company_name')
    txn['company_cui'] = header_info.get('company_cui')
    txn['account_number'] = header_info.get('account_number')
    txn['statement_file'] = filename

    desc = txn.get('description', '')

    # Extract card number
    card_match = CARD_PATTERN.search(desc)
    if card_match:
        txn['card_number'] = card_match.group(1)

    # Extract auth code
    auth_match = AUTH_CODE_PATTERN.search(desc)
    if auth_match:
        txn['auth_code'] = auth_match.group(1)

    # Classify transaction type
    txn['transaction_type'] = classify_transaction(desc)


def classify_transaction(description: str) -> str:
    """Classify transaction type based on description."""
    desc_lower = description.lower()

    if 'pos purchase' in desc_lower:
        return 'card_purchase'
    elif '+cms' in desc_lower:
        return 'card_purchase'  # CMS = Card Management System (check before 'fee')
    elif 'alim card' in desc_lower:
        return 'internal'
    elif 'return' in desc_lower or 'deposit' in desc_lower:
        return 'refund'
    elif 'comision' in desc_lower or 'fee' in desc_lower:
        return 'fee'
    else:
        return 'other'


# ============== Main entry point ==============

def parse_statement(pdf_bytes: bytes, filename: str = None) -> dict:
    """
    Parse a complete bank statement PDF.

    Automatically detects whether to use inline parsing (PyPDF2) or
    column-based parsing (OCR) based on text extraction results.

    Args:
        pdf_bytes: Raw PDF file content
        filename: Optional filename for reference

    Returns:
        {
            'company_name': str,
            'company_cui': str,
            'account_number': str,
            'period': {'from': date, 'to': date},
            'transactions': [Transaction],
            'summary': {
                'opening_balance': float,
                'closing_balance': float,
                'credit_count': int,
                'credit_total': float,
                'debit_count': int,
                'debit_total': float
            },
            'filename': str
        }
    """
    # Extract text
    text, used_ocr = extract_text_from_pdf(pdf_bytes)

    if used_ocr:
        # OCR text has column-based layout — use dedicated parsers
        header = _extract_header_ocr(text)
        transactions = _extract_transactions_ocr(text, header, filename)
        summary = _extract_summary_ocr(text)
    else:
        # PyPDF2 text has inline layout — use original parsers
        header = extract_header_info(text)
        transactions = extract_transactions(text, header, filename)
        summary = extract_summary(text)

    return {
        'company_name': header.get('company_name'),
        'company_cui': header.get('company_cui'),
        'account_number': header.get('account_number'),
        'period': {
            'from': header.get('period_from'),
            'to': header.get('period_to')
        },
        'transactions': transactions,
        'summary': summary,
        'filename': filename,
        'raw_text': text[:5000]  # First 5000 chars for debugging
    }
