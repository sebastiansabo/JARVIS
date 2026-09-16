"""EuroFib MEDLINE-format batch export — pure CSV builder.

See docs/superpowers/plans/2026-09-04-suppliers-master-phase1_1.md ("EuroFib export —
MEDLINE format") for the verbatim column list and per-invoice mapping rules this implements.

v1 assumption: one net/VAT pair per invoice (single VAT rate). Invoices with more than one
VAT rate are out of scope here — callers must pre-aggregate or skip them before calling
`build_csv`.

Delimiter assumption: EuroFib/MEDLINE imports conventionally use `;` (semicolon) — flag this
to the user before relying on it in production if their EuroFib import profile expects a
different delimiter.
"""
import csv
import io
import re

# 56-column MEDLINE header, verbatim from the plan. Column 0 is an unnamed "new document"
# marker column (holds "x" on the first row of a document, blank otherwise).
HEADER = [
    "", "klient", "konto", "soll_haben", "buchdatum", "belegart", "belegdatum", "belegnummer",
    "betrag", "steuercode", "steuerbetrag", "fwcd", "fwbetrag", "fw_steuercode", "fwsteuerbetrag",
    "gegenkonto", "text", "brutto_netto", "nettotage", "valuta", "leistung", "leistung_von",
    "leistung_bis", "zuordnung", "extbeleg", "valuta_beginn", "sktage1", "skproz1", "sktage2",
    "skproz2", "freigabe", "kursdatum", "kurs", "kurs_per", "kurs_fix", "kostenstelle",
    "kostentraeger", "mengen_kz", "mengen_stuck", "zession", "scannummer", "ueberw_banr",
    "nb_code", "mahncode", "opo_info", "skonto_basis", "skonto_fwbasis", "kost_variator",
    "kost_variator_k", "skonto", "skonto_fw", "vb_factoring", "kurs_steuer", "kundendaten",
    "vertreter", "uid",
]
assert len(HEADER) == 56

_MARKER_INDEX = 0
_COL_INDEX = {name: i for i, name in enumerate(HEADER) if name}

# Config fields required for a postable Table-2 config (mirrors
# SupplierMasterRepository.list_budgeted_invoices' completeness filter).
_REQUIRED_CONFIG_FIELDS = ('konto_debit', 'konto_credit', 'klient', 'steuercode', 'belegart')


def _s(value):
    """String-coerce, never int() — preserves leading zeros. None -> ''."""
    return '' if value is None else str(value)


def _money(value):
    """Format an amount to 2 decimals as a string. None -> ''."""
    if value is None:
        return ''
    return f"{float(value):.2f}"


def _belegnummer(invoice_number):
    """Belegnummer/extbeleg = digits only, rightmost up to 6 (e.g. 'MEDL2 195' -> '2195')."""
    digits = re.sub(r'\D', '', '' if invoice_number is None else str(invoice_number))
    return digits[-6:]


def _date_str(value):
    """DD.MM.YYYY (e.g. '31.08.2026'). Accepts date/datetime objects or 'YYYY-MM-DD'
    strings. None/blank -> ''."""
    if value is None or value == '':
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%d.%m.%Y')
    s = str(value)[:10]
    parts = s.split('-')
    if len(parts) == 3 and len(parts[0]) == 4:
        y, m, d = parts
        return f"{d}.{m}.{y}"
    return s


def line_item_text(item):
    """EuroFib `text` for one e-Factura line: its article name (cbc:Name) joined with its
    description (cbc:Description) as 'name — description'. When only one field carries text that
    one is used; a name-less/desc-less item yields ''."""
    if not isinstance(item, dict):
        return ''
    name = (item.get('name') or '').strip()
    desc = (item.get('description') or '').strip()
    parts = [p for p in (name, desc) if p]
    # The XML parser collapses a name-less line into `name`, so name==desc can only happen on odd
    # source data; guard against emitting "X — X".
    if len(parts) == 2 and parts[0] == parts[1]:
        parts = parts[:1]
    return ' — '.join(parts)


def first_line_text(line_items):
    """EuroFib `text` sourced from the invoice's FIRST line (see line_item_text).

    `line_items` is the invoices.line_items shape — a list of {name, description, ...} dicts (or
    its JSON string). An empty/absent first line yields ''. Callers fall back to the schema's
    text_template when this returns ''."""
    if isinstance(line_items, str):
        import json
        try:
            line_items = json.loads(line_items)
        except (ValueError, TypeError):
            return ''
    if not line_items or not isinstance(line_items, (list, tuple)):
        return ''
    return line_item_text(line_items[0])


def _resolve_text(template, invoice):
    """Resolve {invoice_number}/{supplier} placeholders in a text_template; if the template
    doesn't parse (unknown placeholder) or is empty, fall back to the literal template."""
    if not template:
        return ''
    try:
        return template.format(
            invoice_number=invoice.get('invoice_number', ''),
            supplier=invoice.get('supplier', ''),
        )
    except (KeyError, IndexError):
        return template


def _new_row():
    return [''] * len(HEADER)


def _set(row, **kwargs):
    for key, value in kwargs.items():
        row[_COL_INDEX[key]] = value
    return row


def build_medline_rows(invoice: dict, config: dict) -> list:
    """Build the two MEDLINE rows (credit/Haben then debit/Soll) for a single invoice.

    invoice: {supplier, invoice_number, invoice_date, due_date, net_amount, vat_amount,
              gross_amount, line_description?}. MEDLINE `text` is the schema's text_template
              (primary); when the template is empty it falls back to line_description (the
              invoice's first-line article name + description).
    config: an effective Table-2 konto dict (konto_debit, konto_credit, klient,
            gegenkonto_debit, gegenkonto_credit, kostenstelle_debit, kostenstelle_credit,
            extbeleg_debit, extbeleg_credit, steuercode, text_template, belegart).

    Returns [credit_row, debit_row], each a 56-element list positioned per HEADER. All
    account/cost-centre codes are emitted as strings (never int()).
    """
    invoice_number = invoice.get('invoice_number')
    invoice_date = _date_str(invoice.get('invoice_date'))
    due_date = _date_str(invoice.get('due_date'))
    belegart = _s(config.get('belegart'))
    # Same kostenstelle on both lines (Debit value wins, else Credit).
    kostenstelle = _s(config.get('kostenstelle_debit')) or _s(config.get('kostenstelle_credit'))
    # Same extbeleg (invoice number) on both lines when configured on either side.
    extbeleg_val = _belegnummer(invoice_number) if (
        config.get('extbeleg_credit') == 'invoice_number' or config.get('extbeleg_debit') == 'invoice_number'
    ) else ''
    # The schema's Text Template is the primary EuroFib `text`; the invoice's first-line article
    # (name + description) is the fallback used only when the schema has no template.
    text = _resolve_text(config.get('text_template'), invoice) or _s(invoice.get('line_description'))

    credit = _new_row()
    credit[_MARKER_INDEX] = 'x'
    _set(
        credit,
        klient=_s(config.get('klient')),
        konto=_s(config.get('konto_credit')),
        soll_haben='h',
        buchdatum=invoice_date,
        belegart=belegart,
        belegdatum=invoice_date,
        belegnummer=_belegnummer(invoice_number),
        betrag=_money(invoice.get('gross_amount')),
        gegenkonto=_s(config.get('gegenkonto_credit')),
        text=text,
        brutto_netto='B',
        valuta=due_date,
        extbeleg=extbeleg_val,
        kostenstelle=kostenstelle,
    )

    debit = _new_row()
    _set(
        debit,
        konto=_s(config.get('konto_debit')),
        soll_haben='s',
        buchdatum=invoice_date,
        belegart=belegart,
        belegdatum=invoice_date,
        belegnummer=_belegnummer(invoice_number),
        betrag=_money(invoice.get('net_amount')),
        steuercode=_s(config.get('steuercode')),
        steuerbetrag=_money(invoice.get('vat_amount')),
        gegenkonto=_s(config.get('gegenkonto_debit')),
        kostenstelle=kostenstelle,
        extbeleg=extbeleg_val,
        brutto_netto='N',
        valuta=due_date,
    )

    return [credit, debit]


def build_medline_rows_per_line(invoice: dict, base_config: dict, line_configs: list) -> list:
    """Per-line MEDLINE posting: one supplier-payable credit (gross total, from base_config) plus
    one debit per line (its net+VAT posted to that line's expense account/steuercode).

    line_configs: list of {'net': float, 'vat': float, 'text': str, 'config': konto dict}.
    Returns [credit_row, debit_row, ...]. Empty line_configs -> [] (caller skips the invoice).
    """
    if not line_configs:
        return []
    invoice_number = invoice.get('invoice_number')
    invoice_date = _date_str(invoice.get('invoice_date'))
    due_date = _date_str(invoice.get('due_date'))
    belegart = _s(base_config.get('belegart'))
    extbeleg_val = _belegnummer(invoice_number) if (
        base_config.get('extbeleg_credit') == 'invoice_number'
        or base_config.get('extbeleg_debit') == 'invoice_number') else ''
    gross_total = sum(round(float(l['net']) + float(l['vat']), 2) for l in line_configs)

    credit = _new_row()
    credit[_MARKER_INDEX] = 'x'
    _set(credit,
         klient=_s(base_config.get('klient')), konto=_s(base_config.get('konto_credit')),
         soll_haben='h', buchdatum=invoice_date, belegart=belegart, belegdatum=invoice_date,
         belegnummer=_belegnummer(invoice_number), betrag=_money(gross_total),
         gegenkonto=_s(base_config.get('gegenkonto_credit')),
         text=_resolve_text(base_config.get('text_template'), invoice) or _s(line_configs[0].get('text')),
         brutto_netto='B', valuta=due_date, extbeleg=extbeleg_val)

    rows = [credit]
    for line in line_configs:
        cfg = line['config']
        kostenstelle = _s(cfg.get('kostenstelle_debit')) or _s(cfg.get('kostenstelle_credit'))
        debit = _new_row()
        _set(debit,
             konto=_s(cfg.get('konto_debit')), soll_haben='s', buchdatum=invoice_date,
             belegart=belegart, belegdatum=invoice_date, belegnummer=_belegnummer(invoice_number),
             betrag=_money(line['net']), steuercode=_s(cfg.get('steuercode')),
             steuerbetrag=_money(line['vat']), gegenkonto=_s(cfg.get('gegenkonto_debit')),
             kostenstelle=kostenstelle, extbeleg=extbeleg_val, brutto_netto='N', valuta=due_date,
             text=_s(line.get('text')))
        rows.append(debit)
    return rows


def _config_incomplete(config):
    if not config:
        return True
    return any(not str(config.get(field) or '').strip() for field in _REQUIRED_CONFIG_FIELDS)


def _amounts_missing(invoice):
    return invoice.get('net_amount') is None or invoice.get('gross_amount') is None


def build_rows(invoices_with_configs, skipped=None) -> list:
    """Build the full MEDLINE row matrix for a batch of invoices, grouped/ordered by supplier.

    invoices_with_configs: iterable of (invoice: dict, config: dict) pairs.
    skipped: optional list; if given, any invoice whose supplier has no complete Table-2
        config or is missing net/gross amounts is appended to it (mutated in place) as
        {'invoice_number', 'supplier', 'reason'} and excluded from the output.

    Returns a list of 56-element rows: the label/header row, the required empty row, then
    two rows (credit/Haben, debit/Soll) per included invoice. Shared by build_csv/build_xlsx
    so both formats carry identical content.
    """
    if skipped is None:
        skipped = []

    pairs = sorted(
        invoices_with_configs,
        key=lambda pair: (str(pair[0].get('supplier') or ''), str(pair[0].get('invoice_number') or '')))

    rows = [list(HEADER), [''] * len(HEADER)]  # label row + required empty row after it

    for invoice, config in pairs:
        if _config_incomplete(config):
            skipped.append({'invoice_number': invoice.get('invoice_number'),
                             'supplier': invoice.get('supplier'), 'reason': 'incomplete_config'})
            continue
        if invoice.get('line_configs'):
            # Per-line invoice: 1 credit (base config) + one debit per line.
            per_line = build_medline_rows_per_line(invoice, config, invoice['line_configs'])
            if not per_line:
                skipped.append({'invoice_number': invoice.get('invoice_number'),
                                 'supplier': invoice.get('supplier'), 'reason': 'no_line_configs'})
                continue
            rows.extend(per_line)
            continue
        if _amounts_missing(invoice):
            skipped.append({'invoice_number': invoice.get('invoice_number'),
                             'supplier': invoice.get('supplier'), 'reason': 'missing_amounts'})
            continue
        rows.extend(build_medline_rows(invoice, config))

    return rows


def build_csv(invoices_with_configs, skipped=None) -> str:
    """Build the full MEDLINE CSV for a batch of invoices, grouped/ordered by supplier.

    See build_rows for the invoices_with_configs/skipped contract. Returns the CSV text:
    leading UTF-8 BOM + the 56-column header + two rows per included invoice, ';'-delimited
    (EuroFib/MEDLINE convention).
    """
    rows = build_rows(invoices_with_configs, skipped=skipped)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';', lineterminator='\r\n')
    for row in rows:
        writer.writerow(row)

    return '\ufeff' + buffer.getvalue()


def build_xlsx(invoices_with_configs, skipped=None) -> bytes:
    """Build the full MEDLINE export as a single-sheet .xlsx workbook.

    Same content and ordering as build_csv (see build_rows for the skipped contract). All
    cells are written as strings so account codes / belegnummer keep leading zeros in Excel.
    Returns the raw .xlsx bytes.
    """
    from openpyxl import Workbook

    rows = build_rows(invoices_with_configs, skipped=skipped)

    wb = Workbook()
    ws = wb.active
    ws.title = 'EuroFib'
    for row in rows:
        ws.append(row)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
