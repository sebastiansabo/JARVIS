"""Bank Statement Parser for UniCredit PDF statements.

Extracts transactions from UniCredit bank statement PDFs.

PyPDF2's default text extraction concatenates runs in content-stream order
and inserts no space between columns, which scrambles the table (a right-
aligned Valoare amount can glue onto an unrelated left-column run). We instead
rebuild each page from the absolute text coordinates (see
``_reconstruct_page_text``) so every transaction's signed amount lands back on
its own date row. Vector-path PDFs that carry no text layer fall back to OCR
(tesseract). Both paths produce the same *inline* layout — signed amount on the
date row, label-prefixed header, inline summary — so one set of parsers
(``_extract_*_ocr``) handles both.
"""
import re
import logging
from datetime import datetime
from io import BytesIO
from typing import Optional

import PyPDF2

logger = logging.getLogger('jarvis.statements.parser')

# Card number pattern (masked)
CARD_PATTERN = re.compile(r'Card[:\s]*([\d]{4}-[\dX]{2}XX-XXXX-[\d]{4})')

# Auth code pattern
AUTH_CODE_PATTERN = re.compile(r'Auth code\s+(\d+)')

# Foreign currency with exchange rate
FOREX_PATTERN = re.compile(r'([\d.,]+)\s*(EUR|USD)\s*@([\d.,]+)\s*EUR-RON')


def parse_value(value_str: str) -> float:
    """Parse a European-format number (e.g. ``1.234,56``) to float.

    Robust to OCR noise where the thousands separator is misread as a comma
    (``2,003,36`` instead of ``2.003,36``): the *last* separator is treated as
    the decimal point and every earlier '.'/',' as a grouping separator. A
    trailing group of 3 digits is treated as grouping (integer value), since
    statement amounts always carry two decimals.
    """
    if not value_str:
        return 0.0
    value_str = value_str.strip().replace(' ', '')

    negative = value_str.startswith('-')
    if negative:
        value_str = value_str[1:]

    last_sep = max(value_str.rfind('.'), value_str.rfind(','))
    if last_sep == -1:
        int_part, frac_part = value_str, ''
    else:
        int_part = value_str[:last_sep]
        frac_part = value_str[last_sep + 1:]
        # A 3-digit trailing group is a thousands separator, not a decimal.
        if len(frac_part) == 3 and re.search(r'[.,]', int_part):
            int_part, frac_part = int_part + frac_part, ''

    int_digits = re.sub(r'[.,]', '', int_part)
    normalized = int_digits + ('.' + frac_part if frac_part else '')

    try:
        result = float(normalized)
        return -result if negative else result
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


def _compose(tm, cm):
    """Compose two PDF affine matrices (6-tuples): returns ``tm · cm``.

    The text visitor hands us the text matrix (tm) and the current
    transformation matrix (cm) separately; a run's absolute device position is
    their product. Statements drawn inside a form XObject give a non-identity
    cm, so composing is required to get consistent row coordinates.
    """
    a0, a1, a2, a3, a4, a5 = tm
    b0, b1, b2, b3, b4, b5 = cm
    return (a0 * b0 + a1 * b2, a0 * b1 + a1 * b3,
            a2 * b0 + a3 * b2, a2 * b1 + a3 * b3,
            a4 * b0 + a5 * b2 + b4, a4 * b1 + a5 * b3 + b5)


# Runs on the same visual row can drift by a fraction of a point; cluster
# within this many PDF points (statement line spacing is ~12pt, so no risk of
# merging adjacent rows).
_ROW_TOLERANCE = 2.5


def _reconstruct_page_text(page) -> str:
    """Rebuild a page's text grouped by absolute row position.

    PyPDF2's default extraction glues columns together (e.g.
    ``Ref.:573767052`` + ``4.000,00`` -> ``Ref.:5737670524.000,00``), making
    the amount unrecoverable. We capture each run's absolute (x, y) via a text
    visitor, cluster runs into visual rows by y (top-to-bottom), order each
    row left-to-right, and join its runs with a single space — so every
    transaction's amount is restored to its own date row.

    Falls back to plain ``extract_text()`` when no positioned runs are
    available (e.g. a stubbed page, or a PDF the visitor can't walk).
    """
    runs = []

    def visitor(text, cm, tm, font_dict, font_size):
        if text and text.strip():
            m = _compose(tm, cm)
            runs.append((m[5], m[4], text.strip()))  # (y, x, text)

    try:
        plain = page.extract_text(visitor_text=visitor)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f'Positioned text extraction failed, using plain text: {e}')
        return page.extract_text() or ''

    if not runs:
        return plain or ''

    # Cluster into rows: top-to-bottom, then left-to-right within each row.
    runs.sort(key=lambda r: (-r[0], r[1]))
    rows = []
    current = []
    current_y = None
    for y, x, text in runs:
        if current_y is None or abs(y - current_y) <= _ROW_TOLERANCE:
            current.append((x, text))
            if current_y is None:
                current_y = y
        else:
            rows.append(current)
            current = [(x, text)]
            current_y = y
    if current:
        rows.append(current)

    lines = []
    for row in rows:
        row.sort(key=lambda cell: cell[0])
        lines.append(' '.join(text for _, text in row))
    return '\n'.join(lines)


def extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, bool]:
    """Extract all text from a PDF file.

    Reconstructs each page by absolute text position (PyPDF2); falls back to
    OCR (pdf2image + tesseract) for vector-path PDFs that carry no text layer.

    Returns:
        (text, used_ocr) tuple
    """
    reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
    text = '\n'.join(_reconstruct_page_text(page) for page in reader.pages)

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


# ============== Inline-layout parsing ==============
# Used for BOTH reconstructed PyPDF2 text and OCR text: each transaction's
# date, (optional) description and signed amount share the date row, header
# fields are label-prefixed, and the summary totals are inline.
# OCR via tesseract extracts table columns separately:
#   - Left side: dates + descriptions
#   - Right columns: amounts, then currencies
# Header labels and values are also on separate lines.

def _extract_header_ocr(text: str) -> dict:
    """Extract header info from OCR text.

    Handles two OCR layouts:
      - Inline/labeled: "Cont ales RO..", "Titular de cont ..", "CUI/CNP 123"
        (labels and values on the same line).
      - Column-separated: IBAN / company / CUI each on their own line.
    Inline/labeled patterns take priority; the positional logic below fills
    anything still missing so the original column layout keeps working.
    """
    info = {
        'company_name': None,
        'company_cui': None,
        'account_number': None,
        'period_from': None,
        'period_to': None,
    }

    # --- Inline/labeled layout: search anywhere on the line ---
    acc_match = re.search(r'Cont ales\s+(RO\d{2}\s*[A-Z]{4}[\d\s]+)', text)
    if acc_match:
        info['account_number'] = re.sub(r'\s+', '', acc_match.group(1).split('|')[0])

    name_match = re.search(r'Titular de cont\s+(.+)', text)
    if name_match:
        info['company_name'] = name_match.group(1).strip()

    cui_match = re.search(r'CUI/?CNP[:\s]+(\d{5,10})', text)
    if cui_match:
        info['company_cui'] = cui_match.group(1)

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
    # Inline layout: the transaction value (signed) sits at the end of the row,
    # e.g. "... 5586-84XX-XXXX-3100 -1.247,80 RON" or "..., 4.000,00 RON".
    inline_value_pattern = re.compile(r'(-?[\d.,]+)\s*(RON|EUR|USD)\s*$')

    # --- Phase 1: Extract transaction descriptions (and inline amounts) ---
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
            first_desc = date_match.group(3).strip()
            # Inline layout: read the signed value from the end of the date row.
            # (Column layout has no trailing value here -> filled in Phase 4.)
            value_match = inline_value_pattern.search(first_desc)
            if value_match:
                current_txn['amount'] = parse_value(value_match.group(1))
                current_txn['currency'] = value_match.group(2)
                first_desc = first_desc[:value_match.start()].strip()
            desc_lines = [first_desc] if first_desc else []
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

    # --- Phase 4: Pair column amounts/currencies to transactions that still
    # lack an inline value (index-aligned). Inline-layout statements already
    # have every amount set in Phase 1, so this becomes a no-op for them. ---
    unpriced = [txn for txn in transactions if txn['amount'] is None]
    for i, txn in enumerate(unpriced):
        if i < len(amounts):
            val = amounts[i]
            if val.startswith('-'):
                txn['amount'] = -parse_value(val[1:])
            else:
                txn['amount'] = parse_value(val)
        if i < len(currencies):
            txn['currency'] = currencies[i]

    for txn in transactions:
        # Check for forex info in description
        forex_match = FOREX_PATTERN.search(txn.get('description', ''))
        if forex_match:
            txn['original_amount'] = parse_value(forex_match.group(1))
            txn['original_currency'] = forex_match.group(2)
            txn['exchange_rate'] = parse_value(forex_match.group(3))

        _finalize_transaction(txn, header_info, filename)

    # Drop rows that never resolved a usable amount — e.g. the statement-period
    # header line ("01.09.2026 30.09.2026 Tip Toate ...") which a reconstructed
    # layout surfaces as a false date row — so they don't become NULL-amount
    # ghost transactions. Mirrors the validity gate the legacy path applied.
    return [txn for txn in transactions if _is_valid_amount(txn.get('amount'))]


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

    # Inline/labeled layout: label + date + amount all on one line, e.g.
    #   "Sold deschidere 03.08.2026 1.729,72 RON"
    #   "Credit total pentru tranzactiile selectate (4) 11.000,01 RON"
    m = re.search(r'Sold deschidere\s+\d{2}\.\d{2}\.\d{4}\s+([\d.,]+)\s*RON', text)
    if m:
        summary['opening_balance'] = parse_value(m.group(1))
    m = re.search(r'Sold inchidere\s+\d{2}\.\d{2}\.\d{4}\s+([\d.,]+)\s*RON', text)
    if m:
        summary['closing_balance'] = parse_value(m.group(1))
    m = re.search(r'Credit total.*?\(\s*\d+\s*\)\s+([\d.,]+)\s*RON', text)
    if m:
        summary['credit_total'] = parse_value(m.group(1))
    m = re.search(r'Debit total.*?\(\s*\d+\s*\)\s+(-?[\d.,]+)\s*RON', text)
    if m:
        summary['debit_total'] = abs(parse_value(m.group(1)))

    # If the inline patterns already resolved the balances, we're done.
    if summary['opening_balance'] is not None and summary['closing_balance'] is not None:
        return summary

    # Column layout fallback:
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

def _reconcile_against_summary(transactions: list, summary: dict,
                               filename: str = None) -> None:
    """Cross-check parsed transactions against the statement's own totals.

    Every UniCredit statement declares authoritative credit/debit counts and
    totals ("Credit total ... (4) 10.000,01 RON"). If the parsed rows don't
    reconcile to them, a transaction was dropped or an amount mis-parsed (e.g.
    a layout variant the reconstruction mishandles). We log a warning rather
    than raise, so the import still succeeds but the discrepancy is visible.
    """
    TOL = 0.01  # cent tolerance for float rounding

    credits = [t['amount'] for t in transactions if (t.get('amount') or 0) > 0]
    debits = [t['amount'] for t in transactions if (t.get('amount') or 0) < 0]

    def _mismatch(label, got_count, got_total, want_count, want_total):
        if want_total is None:
            return None  # nothing authoritative to compare against
        if got_count != want_count or abs(got_total - want_total) > TOL:
            return (f'{label}: parsed {got_count} totalling {got_total:.2f}, '
                    f'statement declares {want_count} totalling {want_total:.2f}')
        return None

    problems = [p for p in (
        _mismatch('credits', len(credits), sum(credits),
                  summary.get('credit_count'), summary.get('credit_total')),
        _mismatch('debits', len(debits), abs(sum(debits)),
                  summary.get('debit_count'), summary.get('debit_total')),
    ) if p]

    if problems:
        logger.warning(
            'Statement %s did not reconcile to its declared totals — %s',
            filename or '(unknown)', '; '.join(problems))


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

    Both the reconstructed PyPDF2 text and the OCR fallback produce the same
    inline layout, so one set of parsers handles both.

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
    # Extract text (position-reconstructed PyPDF2, or OCR for vector PDFs)
    text, _used_ocr = extract_text_from_pdf(pdf_bytes)

    header = _extract_header_ocr(text)
    transactions = _extract_transactions_ocr(text, header, filename)
    summary = _extract_summary_ocr(text)

    # Surface any statement whose parsed rows don't add up to its own declared
    # credit/debit totals (dropped or mis-parsed transaction).
    _reconcile_against_summary(transactions, summary, filename)

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
