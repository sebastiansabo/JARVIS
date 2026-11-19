"""Invoice parser output → cost field mapper (VAT split).

Pure function (no DB, no network, no LLM) that converts the invoice parser's
output into cost fields by splitting the gross total into net + VAT using the
standard 19% rate (or a custom rate). Mirrors the pure parser `document_ocr.py`
in structure and testing style.
"""


def map_parsed_invoice_to_cost(parsed: dict, default_cost_type: str = 'other', default_vat_rate: float = 19.0) -> dict:
    """Convert parsed invoice dict into cost fields with VAT split.

    Args:
        parsed: Invoice parser output dict with keys like invoice_value, currency,
                invoice_number, invoice_date, supplier, description.
        default_cost_type: Cost type fallback (default: 'other').
        default_vat_rate: VAT rate as percentage (default: 19.0).

    Returns:
        Dict with keys:
        - cost_type: str (default_cost_type)
        - amount: float | None (net, None if invoice_value missing)
        - vat_amount: float | None (VAT, None if invoice_value missing)
        - vat_rate: float (the rate used)
        - currency: str (from parsed or 'RON')
        - invoice_number: str | None
        - invoice_date: str | None
        - invoice_value: float | None (gross, None if missing)
        - supplier_name: str | None
        - description: str | None
        - date: str | None (defaults to invoice_date)
    """
    gross = parsed.get('invoice_value')
    currency = parsed.get('currency', 'RON')
    invoice_date = parsed.get('invoice_date')
    supplier_name = parsed.get('supplier')
    description = parsed.get('description')
    invoice_number = parsed.get('invoice_number')

    # Split gross into net + VAT when available
    if gross is not None:
        try:
            gross = float(gross)
            # net = round(gross / (1 + rate/100), 2)
            # vat_amount = round(gross - net, 2)
            net = round(gross / (1 + default_vat_rate / 100), 2)
            vat_amount = round(gross - net, 2)
        except (ValueError, TypeError):
            net = None
            vat_amount = None
    else:
        net = None
        vat_amount = None
        gross = None

    return {
        'cost_type': default_cost_type,
        'amount': net,
        'vat_amount': vat_amount,
        'vat_rate': default_vat_rate,
        'currency': currency,
        'invoice_number': invoice_number,
        'invoice_date': invoice_date,
        'invoice_value': gross,
        'supplier_name': supplier_name,
        'description': description,
        'date': invoice_date,
    }
