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
    """YYYY-MM-DD. Accepts date/datetime objects or already-formatted strings. None -> ''."""
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()[:10]
    return str(value)[:10]


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
              gross_amount}
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
    text = _resolve_text(config.get('text_template'), invoice)

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


def _config_incomplete(config):
    if not config:
        return True
    return any(not str(config.get(field) or '').strip() for field in _REQUIRED_CONFIG_FIELDS)


def _amounts_missing(invoice):
    return invoice.get('net_amount') is None or invoice.get('gross_amount') is None


def build_csv(invoices_with_configs, skipped=None) -> str:
    """Build the full MEDLINE CSV for a batch of invoices, grouped/ordered by supplier.

    invoices_with_configs: iterable of (invoice: dict, config: dict) pairs.
    skipped: optional list; if given, any invoice whose supplier has no complete Table-2
        config or is missing net/gross amounts is appended to it (mutated in place) as
        {'invoice_number', 'supplier', 'reason'} and excluded from the CSV.

    Returns the CSV text: leading UTF-8 BOM + the 56-column header + two rows per included
    invoice, ';'-delimited (EuroFib/MEDLINE convention).
    """
    if skipped is None:
        skipped = []

    pairs = sorted(
        invoices_with_configs,
        key=lambda pair: (str(pair[0].get('supplier') or ''), str(pair[0].get('invoice_number') or '')))

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';', lineterminator='\r\n')
    writer.writerow(HEADER)

    for invoice, config in pairs:
        if _config_incomplete(config):
            skipped.append({'invoice_number': invoice.get('invoice_number'),
                             'supplier': invoice.get('supplier'), 'reason': 'incomplete_config'})
            continue
        if _amounts_missing(invoice):
            skipped.append({'invoice_number': invoice.get('invoice_number'),
                             'supplier': invoice.get('supplier'), 'reason': 'missing_amounts'})
            continue
        for row in build_medline_rows(invoice, config):
            writer.writerow(row)

    return '\ufeff' + buffer.getvalue()
