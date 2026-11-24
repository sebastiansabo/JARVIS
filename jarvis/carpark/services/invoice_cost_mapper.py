"""Invoice parser output → cost / revenue field mappers (VAT split).

Pure functions (no DB, no network, no LLM) that convert the invoice parser's
output into cost or revenue fields, splitting the gross total into net + VAT
using the standard 19% rate (or a custom rate). Mirrors the pure parser
`document_ocr.py` in structure and testing style.

A purchase / service / internal invoice becomes a COST (the invoice's supplier
-> supplier_name); a sale invoice becomes a REVENUE (the invoice's customer ->
client_name). Same OCR, two mappings — the parse-invoice route returns both and
the user picks the destination.
"""


def _split_net_vat(gross, rate):
    """(net, vat_amount, gross) from a gross total at `rate`%.

    Returns (None, None, None) when gross is missing or non-numeric (e.g. 'N/A'
    from the parser's JSON-decode-failure path) — a non-numeric value must never
    leak into the numeric DB columns. `net + vat_amount == gross` to the cent.
    """
    if gross is None:
        return None, None, None
    try:
        gross = float(gross)
    except (ValueError, TypeError):
        return None, None, None
    net = round(gross / (1 + rate / 100), 2)
    return net, round(gross - net, 2), gross


def map_parsed_invoice_to_cost(parsed: dict, default_cost_type: str = 'other', default_vat_rate: float = 19.0) -> dict:
    """Convert a parsed invoice into COST fields with VAT split.

    Returns keys: cost_type, amount (net | None), vat_amount (| None), vat_rate,
    currency (parsed or 'RON'), invoice_number, invoice_date, invoice_value
    (gross | None), supplier_name, description, date (defaults to invoice_date).
    """
    net, vat_amount, gross = _split_net_vat(parsed.get('invoice_value'), default_vat_rate)
    return {
        'cost_type': default_cost_type,
        'amount': net,
        'vat_amount': vat_amount,
        'vat_rate': default_vat_rate,
        # `or 'RON'` (not a dict default) so an explicit None from the parser's
        # failure path still falls back — else NULL persists to the currency col.
        'currency': parsed.get('currency') or 'RON',
        'invoice_number': parsed.get('invoice_number'),
        'invoice_date': parsed.get('invoice_date'),
        'invoice_value': gross,
        'supplier_name': parsed.get('supplier'),
        'description': parsed.get('description'),
        'date': parsed.get('invoice_date'),
    }


def map_parsed_invoice_to_revenue(parsed: dict, default_revenue_type: str = 'sale', default_vat_rate: float = 19.0) -> dict:
    """Convert a parsed invoice into REVENUE (Venituri) fields with VAT split.

    Mirrors the cost mapper, but the money side flips: the invoice's *customer*
    (the buyer) becomes the revenue's client, and the default type is 'sale'.
    `vat_rate`, `invoice_date` and `invoice_value` are UI helpers only — the
    carpark_vehicle_revenues table has no such columns, so RevenueRepository
    filters them out; the invoice date drives the revenue `date` field.
    """
    net, vat_amount, gross = _split_net_vat(parsed.get('invoice_value'), default_vat_rate)
    return {
        'revenue_type': default_revenue_type,
        'amount': net,
        'vat_amount': vat_amount,
        'vat_rate': default_vat_rate,
        'currency': parsed.get('currency') or 'RON',
        'invoice_number': parsed.get('invoice_number'),
        'invoice_date': parsed.get('invoice_date'),
        'invoice_value': gross,
        'client_name': parsed.get('customer'),
        'description': parsed.get('description'),
        'date': parsed.get('invoice_date'),
    }
