"""Tests for buyback.services.contract_pdf.build_contract_context — the pure
record/company/offer/consignment -> token-dict builder consumed by the
contract PDF renderer (Task 4). No DB, no I/O.
"""
from decimal import Decimal

from buyback.services.contract_pdf import build_contract_context
from buyback.services.contract_template import PLACEHOLDERS


def test_maps_company_and_vehicle_tokens():
    ctx = build_contract_context(
        {'advisor_name': 'A', 'brand': 'Volvo', 'model': 'XC60', 'vin': 'YV1', 'mileage_km': 50000,
         'seller_name': 'Ion', 'seller_cnp': '1', 'seller_ci_serie': 'XZ', 'seller_ci_number': '12'},
        {'company': 'Autoworld', 'vat': 'RO1', 'reg_no': 'J40', 'street': 'Str. A', 'city': 'Cluj'},
        contract_number='BB-1', contract_date='2026-10-21')
    assert ctx['company_name'] == 'Autoworld'
    assert ctx['company_address'] == 'Str. A, Cluj'
    assert ctx['seller_ci'] == 'seria XZ nr. 12'
    assert ctx['brand'] == 'Volvo' and ctx['mileage'] == 50000


def test_company_seller_name_uses_company_name():
    # A company seller: the Vânzător on the contract is the firm, so the
    # company name takes the {seller_name} slot while {seller_company_name}
    # carries it explicitly for templates that want both.
    ctx = build_contract_context(
        {'client_type': 'company', 'seller_name': 'Ion Pop', 'seller_company_name': 'Auto SRL'}, {})
    assert ctx['seller_company_name'] == 'Auto SRL'
    assert ctx['seller_name'] == 'Auto SRL'


def test_person_seller_name_unchanged_by_company_name_field():
    ctx = build_contract_context(
        {'client_type': 'person', 'seller_name': 'Ion Pop', 'seller_company_name': ''}, {})
    assert ctx['seller_name'] == 'Ion Pop'
    assert ctx['seller_company_name'] == ''


def test_company_without_company_name_falls_back_to_seller_name():
    # Legacy company records (firm name typed into "Nume", no dedicated field)
    # must still render the firm as Vânzător.
    ctx = build_contract_context(
        {'client_type': 'company', 'seller_name': 'Legacy Firm SRL'}, {})
    assert ctx['seller_name'] == 'Legacy Firm SRL'


def test_price_from_accepted_offer():
    ctx = build_contract_context({}, {}, offer={'amount_eur': Decimal('12000')})
    assert '12' in ctx['price_eur'] and ctx['price_ron'] == ''


def test_missing_sources_render_empty_not_crash():
    ctx = build_contract_context({}, {})
    for t in PLACEHOLDERS:
        assert t in ctx                      # every token present
    assert ctx['engine_no'] == '' and ctx['seller_ci'] == ''


def test_consignment_terms_tokens():
    ctx = build_contract_context({}, {}, consignment={'consignment_terms': {'owner_price': '10000', 'commission': '4%'}})
    assert ctx['owner_price'] == '10000' and ctx['commission'] == '4%'


def test_company_address_falls_back_to_showroom_address():
    ctx = build_contract_context({}, {'showroom_address': 'Str. Fallback 1'})
    assert ctx['company_address'] == 'Str. Fallback 1'


def test_seller_ci_requires_both_serie_and_number():
    ctx = build_contract_context({'seller_ci_serie': 'XZ'}, {})
    assert ctx['seller_ci'] == ''
    ctx = build_contract_context({'seller_ci_number': '12'}, {})
    assert ctx['seller_ci'] == ''


def test_price_eur_empty_without_offer():
    ctx = build_contract_context({}, {})
    assert ctx['price_eur'] == ''


def test_vat_note_derived_from_vat_status():
    assert build_contract_context({'vat_status': 'with_vat'}, {})['vat_note'] == 'TVA inclus'
    assert build_contract_context({'vat_status': 'no_vat'}, {})['vat_note'] == 'neplatitor de TVA'
    assert build_contract_context({'vat_status': 'unknown'}, {})['vat_note'] == ''
    assert build_contract_context({}, {})['vat_note'] == ''


def test_consignment_min_price_from_floor_or_min_sale_price_key():
    ctx = build_contract_context({}, {}, consignment={'consignment_terms': {'floor': '9000'}})
    assert ctx['min_price'] == '9000'
    ctx = build_contract_context({}, {}, consignment={'consignment_terms': {'min_sale_price': '8500'}})
    assert ctx['min_price'] == '8500'


# P5 — the real consignment agreement is a carpark_vehicle_consignment ROW with
# TOP-LEVEL columns (owner_price/min_sale_price/commission_type/commission_value),
# not a nested consignment_terms dict. The builder must read that shape too, and
# compose {commission} from commission_type + commission_value.
def test_consignment_carpark_row_shape_percent_commission():
    row = {'owner_price': Decimal('10000.00'), 'min_sale_price': Decimal('8500.00'),
           'commission_type': 'percent', 'commission_value': Decimal('4.00')}
    ctx = build_contract_context({}, {}, consignment=row)
    assert ctx['owner_price'] == '10000'       # trailing zeros stripped
    assert ctx['min_price'] == '8500'
    assert ctx['commission'] == '4%'


def test_consignment_carpark_row_shape_fixed_commission():
    row = {'commission_type': 'fixed', 'commission_value': Decimal('500.00')}
    ctx = build_contract_context({}, {}, consignment=row)
    assert ctx['commission'] == '500 €'


def test_consignment_ready_commission_string_wins_over_type_value():
    # The offer-JSONB shape may carry a ready 'commission' — keep it verbatim.
    ctx = build_contract_context({}, {}, consignment={'consignment_terms': {
        'commission': '4%', 'commission_type': 'fixed', 'commission_value': '999'}})
    assert ctx['commission'] == '4%'


def test_engine_no_power_cp_civ_no_always_empty():
    ctx = build_contract_context(
        {'engine_no': 'should-not-be-used', 'power_cp': 999, 'civ_no': 'CIV-1'}, {})
    assert ctx['engine_no'] == '' and ctx['power_cp'] == '' and ctx['civ_no'] == ''
