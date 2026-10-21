"""Tests for carpark.services.sale_docs.proforma.

Task 5 of the CarPark "Documente vanzare" plan: builds one proforma-invoice
PDF for a car by reusing the existing, CLAUDE.md-protected
`ProformaPdfRenderer` (accounting/facturare/generators/proforma_pdf.py) and
`OrderLine` (accounting/facturare/models.py) — this module itself does no
DB/I/O, it only maps the Task 2 context dict onto those two existing types.

Both tests patch `ProformaPdfRenderer` where it is USED
(`carpark.services.sale_docs.proforma.ProformaPdfRenderer`), capturing the
ctor args and the `lines` passed to `render_single_doc_to_bytes`, so no
reportlab rendering actually happens here — that's already covered by the
facturare module's own tests.
"""
from unittest.mock import patch

from carpark.services.sale_docs import proforma
from carpark.services.sale_docs.proforma import render_proforma_pdf, validate_proforma_context


def _party(**overrides):
    base = {
        'name': 'Ion Popescu',
        'cui': 'RO99887766',
        'address': 'Str. Lalelelor 1',
        'city': 'Cluj-Napoca',
        'county': 'Cluj',
        'phone': '0722111222',
        'email': 'ion@example.com',
    }
    base.update(overrides)
    return base


def _seller(**overrides):
    base = {
        'name': 'Autoworld Premium SRL',
        'cui': '50188939',
        'reg_no': 'J2024002670120',
        'address': 'Calea Floresti 145',
        'city': 'Cluj-Napoca',
        'county': 'Cluj',
        'iban': 'RO24BACX0000002700266000',
        'bank': 'Unicredit',
        'swift': 'BACXROBU',
        'administrator': 'Mezei Ioan',
        'showroom_address': 'Calea Turzii 249',
        'phone': '0264-502600',
    }
    base.update(overrides)
    return base


def _context(**overrides):
    base = {
        'seller': _seller(),
        'cumparator': _party(),
        'utilizator': _party(),
        'is_leasing': False,
        'brand': 'Audi',
        'model': 'A4',
        'variant': '2.0 TDI S-Line',
        'vin': 'WAUZZZ8K9DA012345',
        'registration_number': None,
        'mileage_km': 45000,
        'year': 2021,
        'color': 'Negru',
        'price': 24990,
        'currency': 'EUR',
        'fuel': 'Diesel',
        'consultant_name': None,
        'contract_number': None,
        'contract_date': None,
        'proforma_number': 7,
        'proforma_date': '2026-10-21',
        'delivery_term_days': None,
        'delivery_place': None,
        'delivery_date': None,
        'autonomy': None,
    }
    base.update(overrides)
    return base


def test_proforma_builds_orderline_from_vehicle():
    context = _context()
    captured = {}

    class FakeRenderer:
        def __init__(self, *args, **kwargs):
            captured['ctor_args'] = args
            captured['ctor_kwargs'] = kwargs

        def render_single_doc_to_bytes(self, lines, inv_no):
            captured['lines'] = lines
            captured['inv_no'] = inv_no
            return b'%PDF-stub'

    with patch.object(proforma, 'ProformaPdfRenderer', FakeRenderer):
        result = render_proforma_pdf(context, proforma_number=7)

    assert result == b'%PDF-stub'
    assert captured['inv_no'] == 7

    lines = captured['lines']
    assert len(lines) == 1
    line = lines[0]
    assert line.model == 'Audi A4 2.0 TDI S-Line'
    assert line.vin == 'WAUZZZ8K9DA012345'
    assert line.culoare == 'Negru'
    assert line.advance == 24990.0
    assert line.list_price == 24990.0
    assert line.selling_price == 24990.0
    assert line.rest == 0.0
    assert line.invoice_date == '2026-10-21'
    assert line.comanda == 1


def test_proforma_supplier_customer_from_context():
    context = _context()
    captured = {}

    class FakeRenderer:
        def __init__(self, *args, **kwargs):
            captured['ctor_args'] = args
            captured['ctor_kwargs'] = kwargs

        def render_single_doc_to_bytes(self, lines, inv_no):
            return b'%PDF-stub'

    with patch.object(proforma, 'ProformaPdfRenderer', FakeRenderer):
        render_proforma_pdf(context, proforma_number=7)

    supplier = captured['ctor_kwargs'].get('supplier') or captured['ctor_args'][0]
    customer = captured['ctor_kwargs'].get('customer') or captured['ctor_args'][1]

    assert supplier['name'] == 'Autoworld Premium SRL'
    assert supplier['reg_no'] == 'J2024002670120'
    assert supplier['vat'] == '50188939'
    assert supplier['iban'] == 'RO24BACX0000002700266000'
    assert supplier['bank'] == 'Unicredit'
    assert supplier['swift'] == 'BACXROBU'
    assert any('Calea Floresti 145' in line for line in supplier['address_lines'])

    assert customer['name'] == 'Ion Popescu'
    assert customer['vat'] == 'RO99887766'
    assert any('Str. Lalelelor 1' in line for line in customer['address_lines'])


def test_validate_proforma_flags_missing_customer_name():
    # Important #3 (spec A4): never emit a proforma with no invoiced-party
    # name or no price silently missing.
    context = _context(cumparator=_party(name=None))
    errors = validate_proforma_context(context)
    assert any('cump' in e.lower() for e in errors)

    context_no_price = _context(price=None)
    errors_no_price = validate_proforma_context(context_no_price)
    assert any('pre' in e.lower() for e in errors_no_price)

    # A complete context has no errors.
    assert validate_proforma_context(_context()) == []
