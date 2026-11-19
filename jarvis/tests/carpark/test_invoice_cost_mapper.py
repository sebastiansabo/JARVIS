"""Unit tests for the invoice→cost field mapper (VAT split).

`map_parsed_invoice_to_cost` is pure (no DB/HTTP/LLM) — it converts the invoice
parser's output into cost fields by splitting the gross total into net + VAT.
Focus here: rounding and fallback defaults for missing fields.
"""

from carpark.services.invoice_cost_mapper import map_parsed_invoice_to_cost


def test_gross_splits_into_net_and_vat_at_19():
    out = map_parsed_invoice_to_cost({'invoice_value': 1190, 'currency': 'RON'})
    assert out['amount'] == 1000.0 and out['vat_amount'] == 190.0 and out['vat_rate'] == 19.0
    assert out['invoice_value'] == 1190.0


def test_missing_gross_yields_none_amount():
    out = map_parsed_invoice_to_cost({'supplier': 'AUTO SRL'})
    assert out['amount'] is None and out['vat_amount'] is None
    assert out['supplier_name'] == 'AUTO SRL'


def test_fields_are_mapped_through():
    out = map_parsed_invoice_to_cost({'invoice_value': 100, 'invoice_number': 'F123',
                                      'invoice_date': '2026-11-10', 'supplier': 'X', 'currency': 'EUR'})
    assert out['invoice_number'] == 'F123' and out['invoice_date'] == '2026-11-10'
    assert out['date'] == '2026-11-10' and out['currency'] == 'EUR'


def test_currency_defaults_to_ron_and_net_vat_sum_equals_gross():
    out = map_parsed_invoice_to_cost({'invoice_value': 1000})  # 1000/1.19
    assert out['currency'] == 'RON'
    assert round(out['amount'] + out['vat_amount'], 2) == 1000.0


def test_reduced_rate_split():
    out = map_parsed_invoice_to_cost({'invoice_value': 109}, default_vat_rate=9.0)
    assert out['amount'] == 100.0 and out['vat_amount'] == 9.0
