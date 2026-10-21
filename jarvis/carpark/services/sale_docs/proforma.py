"""Per-car proforma-invoice PDF — Task 5 of the CarPark "Documente vanzare"
plan. Pure module (no DB, no I/O of its own): it maps the Task 2 context
dict (`context.py::build_sale_context`) onto the existing, CLAUDE.md-
protected `ProformaPdfRenderer` / `OrderLine` types from the `facturare`
module and calls them — it never reimplements any PDF-drawing logic.

Buyer identity (design D4, same convention as contract.py/warranty.py): the
proforma's customer is `context['cumparator']` — the invoiced party (the
buyer in a cash sale, the leasing company in a leasing sale) — NOT
`utilizator`.
"""
from accounting.facturare.generators.proforma_pdf import ProformaPdfRenderer
from accounting.facturare.models import OrderLine


def _s(value) -> str:
    """Stringify + strip; None/blank becomes ''. Mirrors context.py's `_s`."""
    if value is None:
        return ''
    return str(value).strip()


def _model_string(brand, model, variant) -> str:
    """`f"{brand} {model} {variant}".strip()`, built from the non-empty
    parts so a missing brand/model/variant never injects the literal
    string "None"."""
    return ' '.join(part for part in (_s(brand), _s(model), _s(variant)) if part)


def _address_lines(block: dict) -> list:
    """Compose the renderer's `address_lines` from a seller/party dict's
    `address`/`city`/`county` fields, dropping empties."""
    block = block or {}
    city_county = ', '.join(part for part in (_s(block.get('city')), _s(block.get('county'))) if part)
    return [line for line in (_s(block.get('address')), city_county) if line]


def _supplier_dict(seller: dict) -> dict:
    seller = seller or {}
    return {
        'name': _s(seller.get('name')),
        'address_lines': _address_lines(seller),
        'reg_no': _s(seller.get('reg_no')),
        'vat': _s(seller.get('cui')),
        'iban': _s(seller.get('iban')),
        'bank': _s(seller.get('bank')),
        'swift': _s(seller.get('swift')),
    }


def _customer_dict(party: dict) -> dict:
    party = party or {}
    return {
        'name': _s(party.get('name')),
        'address_lines': _address_lines(party),
        'vat': _s(party.get('cui')),
    }


def render_proforma_pdf(context: dict, proforma_number: int) -> bytes:
    """Build one `OrderLine` from `context`'s vehicle tokens and render it
    to proforma-invoice PDF bytes via `ProformaPdfRenderer`."""
    context = context or {}
    price = float(context.get('price'))

    line = OrderLine(
        comanda=1,
        model=_model_string(context.get('brand'), context.get('model'), context.get('variant')),
        culoare=context.get('color'),
        list_price=price,
        selling_price=price,
        advance=price,
        rest=0.0,
        vin=context.get('vin'),
        invoice_date=context.get('proforma_date'),
    )

    supplier = _supplier_dict(context.get('seller'))
    customer = _customer_dict(context.get('cumparator'))

    renderer = ProformaPdfRenderer(
        supplier,
        customer,
        invoice_date=context.get('proforma_date'),
        total_amount_ron=None,
    )
    return renderer.render_single_doc_to_bytes([line], proforma_number)


def validate_proforma_context(context: dict) -> list:
    """Return a list of Romanian missing-mandatory-field messages; an empty
    list means `context` has everything required to render a proforma.

    Mirrors `contract.py::validate_contract_context` (spec A4 — never emit a
    document with required data silently missing). Mandatory: the invoiced
    party's name (`context['cumparator']` — see module docstring: the
    proforma's customer is the buyer in a cash sale, the leasing company in
    a leasing sale) and the price.
    """
    context = context or {}
    errors = []

    cumparator = context.get('cumparator') or {}
    if not cumparator.get('name'):
        errors.append('Datele cumpărătorului (nume) sunt obligatorii.')

    if not context.get('price'):
        errors.append('Prețul este obligatoriu.')

    return errors
