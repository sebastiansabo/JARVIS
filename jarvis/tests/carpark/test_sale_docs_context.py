"""Pure unit tests for carpark.services.sale_docs.context — no DB, no mocks.

Every input is a plain dict shaped exactly like the row a repository would
return (companies / crm_clients / carpark_leasing_companies / carpark_vehicles),
per the Task 2 brief. The module under test does no I/O, so these tests
construct dicts by hand and assert on the returned context dict.

Added for Task 2 of the CarPark "Documente vanzare" plan: assembles the
seller/buyer/leasing-company "party" blocks + vehicle/form tokens into the
single context dict that Tasks 3-5 (contract/warranty/proforma renderers)
will consume.
"""
import pytest

from carpark.services.sale_docs.context import (
    LEASING_SALE_TYPES,
    build_seller,
    build_party_from_client,
    build_sale_context,
)


def _company(**overrides):
    base = {
        'company': 'Autoworld Premium SRL',
        'vat': 'RO12345678',
        'reg_no': 'J12/345/2020',
        'iban': 'RO49AAAA1B31007593840000',
        'bank': 'Unicredit',
        'swift': 'BACXROBU',
        'street': 'Calea Florești 145',
        'city': 'Cluj-Napoca',
        'county': 'Cluj',
        'showroom_address': 'Calea Clujului 4B',
        'administrator': 'Ioan Mezei',
    }
    base.update(overrides)
    return base


def _client(**overrides):
    base = {
        'display_name': 'Ion Popescu',
        'cui': 'RO99887766',
        'street': 'Str. Lalelelor 1',
        'city': 'Cluj-Napoca',
        'region': 'Cluj',
        'company_name': 'Popescu SRL',
        'phone': '0722111222',
        'email': 'ion@example.com',
    }
    base.update(overrides)
    return base


def _leasing_company(**overrides):
    base = {
        'name': 'BRD Leasing IFN SA',
        'cui': 'RO11223344',
        'reg_no': 'J40/1/2001',
        'address': 'Bd. Ion Mihalache 1-7',
        'city': 'Bucuresti',
        'county': 'Sector 1',
        'legal_rep': 'Maria Ionescu',
        'legal_rep_role': 'Director',
        'phone': '0211234567',
        'email': 'office@brdleasing.ro',
        'iban': 'RO11BRDE1234567890',
    }
    base.update(overrides)
    return base


def _vehicle(**overrides):
    base = {
        'brand': 'Audi',
        'model': 'A4',
        'variant': '2.0 TDI S-Line',
        'vin': 'WAUZZZ8K9DA012345',
        'mileage_km': 45000,
        'year_of_manufacture': 2021,
        'color_exterior': 'Negru',
        'fuel_type': 'Diesel',
        'sale_price': 25000,
        'current_price': 27000,
        'price_currency': 'EUR',
        'sale_type': 'CASH',
        'buyer_client_id': 1,
        'buyer_name': None,
        'company_id': 1,
    }
    base.update(overrides)
    return base


def _form(**overrides):
    base = {
        'contract_number': '123',
        'contract_date': '2026-10-21',
        'proforma_number': 'PF-001',
        'proforma_date': '2026-10-21',
        'delivery_term_days': 5,
        'delivery_place': 'Showroom Cluj',
        'delivery_date': '2026-10-26',
        'autonomy': None,
    }
    base.update(overrides)
    return base


def test_build_seller_maps_company_strips_ro_vat():
    seller = build_seller(_company(vat='RO12345678'))

    assert seller['name'] == 'Autoworld Premium SRL'
    assert seller['cui'] == '12345678'  # leading 'RO' stripped
    assert seller['reg_no'] == 'J12/345/2020'
    assert seller['address'] == 'Calea Florești 145'  # from street
    assert seller['city'] == 'Cluj-Napoca'
    assert seller['county'] == 'Cluj'
    assert seller['iban'] == 'RO49AAAA1B31007593840000'
    assert seller['bank'] == 'Unicredit'
    assert seller['swift'] == 'BACXROBU'
    assert seller['administrator'] == 'Ioan Mezei'
    assert seller['showroom_address'] == 'Calea Clujului 4B'
    # `companies` has no `phone` column; must not crash, must come back blank.
    assert seller['phone'] == ''


def test_build_seller_without_ro_prefix_keeps_vat_as_is():
    seller = build_seller(_company(vat='12345678'))
    assert seller['cui'] == '12345678'


def test_build_seller_exposes_vat_and_email():
    seller = build_seller(_company(vat='RO50188939', alert_email='aap@autoworld.ro'))

    # Raw registered VAT, incl. the 'RO' prefix — distinct from `cui` above,
    # which is used for the contract's TVA field (Critical #1 / spec G2/A2).
    assert seller['vat'] == 'RO50188939'
    # `companies` has no dedicated email column — `alert_email` is the only
    # one available.
    assert seller['email'] == 'aap@autoworld.ro'

    # Blank when absent, never raises.
    blank_seller = build_seller(_company(alert_email=None))
    assert blank_seller['email'] == ''


def test_build_party_uses_display_name_then_fallback():
    with_client = build_party_from_client(_client(display_name='Ion Popescu'), fallback_name='Should Not Be Used')
    assert with_client['name'] == 'Ion Popescu'
    assert with_client['cui'] == 'RO99887766'
    assert with_client['address'] == 'Str. Lalelelor 1'
    assert with_client['city'] == 'Cluj-Napoca'
    assert with_client['county'] == 'Cluj'  # from `region`
    assert with_client['phone'] == '0722111222'
    assert with_client['email'] == 'ion@example.com'

    without_client = build_party_from_client(None, fallback_name='Walk-in Buyer')
    assert without_client['name'] == 'Walk-in Buyer'
    assert without_client['cui'] == ''
    assert without_client['address'] == ''


def test_context_leasing_sets_cumparator_to_leasing_company():
    vehicle = _vehicle(sale_type='BRD')
    context = build_sale_context(
        vehicle=vehicle,
        company=_company(),
        buyer_client=_client(),
        leasing_company=_leasing_company(),
        form=_form(),
    )

    assert context['is_leasing'] is True
    assert context['cumparator']['name'] == 'BRD Leasing IFN SA'
    assert context['cumparator']['cui'] == 'RO11223344'
    assert context['utilizator']['name'] == 'Ion Popescu'
    # cumparator must NOT collapse into the buyer in a leasing sale
    assert context['cumparator'] != context['utilizator']


@pytest.mark.parametrize('sale_type', sorted(LEASING_SALE_TYPES))
def test_every_leasing_sale_type_is_detected(sale_type):
    vehicle = _vehicle(sale_type=sale_type)
    context = build_sale_context(
        vehicle=vehicle,
        company=_company(),
        buyer_client=_client(),
        leasing_company=_leasing_company(),
        form=_form(),
    )
    assert context['is_leasing'] is True


def test_context_cash_collapses_cumparator_to_buyer():
    vehicle = _vehicle(sale_type='CASH')
    context = build_sale_context(
        vehicle=vehicle,
        company=_company(),
        buyer_client=_client(),
        leasing_company=None,
        form=_form(),
    )

    assert context['is_leasing'] is False
    assert context['cumparator'] == context['utilizator']
    assert context['cumparator']['name'] == 'Ion Popescu'


def test_context_includes_vehicle_and_form_tokens():
    vehicle = _vehicle(sale_type='CASH', sale_price=25000)
    context = build_sale_context(
        vehicle=vehicle,
        company=_company(),
        buyer_client=_client(),
        leasing_company=None,
        form=_form(contract_number='999'),
    )

    assert context['brand'] == 'Audi'
    assert context['model'] == 'A4'
    assert context['variant'] == '2.0 TDI S-Line'
    assert context['vin'] == 'WAUZZZ8K9DA012345'
    assert context['mileage_km'] == 45000
    assert context['year'] == 2021  # from year_of_manufacture
    assert context['color'] == 'Negru'  # from color_exterior
    assert context['price'] == 25000  # sale_price takes priority
    assert context['currency'] == 'EUR'
    assert context['fuel'] == 'Diesel'
    assert context['contract_number'] == '999'
    assert context['proforma_number'] == 'PF-001'
    assert context['delivery_term_days'] == 5
    assert context['delivery_place'] == 'Showroom Cluj'
    assert context['delivery_date'] == '2026-10-26'
    assert context['autonomy'] is None


def test_context_price_falls_back_to_current_price():
    vehicle = _vehicle(sale_price=None, current_price=27000)
    context = build_sale_context(
        vehicle=vehicle,
        company=_company(),
        buyer_client=_client(),
        leasing_company=None,
        form=_form(),
    )
    assert context['price'] == 27000


def test_context_requires_price():
    vehicle = _vehicle(sale_price=None, current_price=None)
    with pytest.raises(ValueError):
        build_sale_context(
            vehicle=vehicle,
            company=_company(),
            buyer_client=_client(),
            leasing_company=None,
            form=_form(),
        )


def test_context_prefers_form_price():
    vehicle = _vehicle(sale_price=100, current_price=50, price_currency='RON')
    context = build_sale_context(
        vehicle=vehicle,
        company=_company(),
        buyer_client=_client(),
        leasing_company=None,
        form=_form(price=99999, currency='EUR'),
    )
    assert context['price'] == 99999
    assert context['currency'] == 'EUR'


def test_context_falls_back_to_vehicle_price_when_form_absent():
    vehicle = _vehicle(sale_price=100, current_price=50, price_currency='RON')
    context = build_sale_context(
        vehicle=vehicle,
        company=_company(),
        buyer_client=_client(),
        leasing_company=None,
        form=_form(),
    )
    assert context['price'] == 100
    assert context['currency'] == 'RON'
