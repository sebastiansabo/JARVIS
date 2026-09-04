import pytest

from core.suppliers.accounting_mapping import map_invoice_to_accounting_fields

# Reference example from the Phase 1.1 plan ("Mapping function" section).
_REFERENCE_CONFIG = {
    'klient': '140',
    'konto_credit': '40102793',
    'konto_debit': '628701',
    'gegenkonto_credit': '628701',
    'gegenkonto_debit': '',
    'kostenstelle_debit': '0393',
    'kostenstelle_credit': '',
    'extbeleg_credit': 'invoice_number',
    'extbeleg_debit': '',
}


def test_reference_example_from_plan():
    invoice = {'invoice_number': '17278'}
    result = map_invoice_to_accounting_fields(invoice, _REFERENCE_CONFIG)
    assert result == {
        'konto_debit': '628701',
        'konto_credit': '40102793',
        'klient': '140',
        'gegenkonto_debit': '',
        'gegenkonto_credit': '628701',
        'kostenstelle_debit': '0393',
        'kostenstelle_credit': '',
        'extbeleg_debit': '',
        'extbeleg_credit': '17278',
    }


def test_kostenstelle_leading_zero_preserved_as_string():
    result = map_invoice_to_accounting_fields({'invoice_number': '1'}, _REFERENCE_CONFIG)
    assert result['kostenstelle_debit'] == '0393'
    assert isinstance(result['kostenstelle_debit'], str)


def test_raises_when_config_missing():
    with pytest.raises(ValueError):
        map_invoice_to_accounting_fields({'invoice_number': '1', 'supplier_id': 9}, None)
    with pytest.raises(ValueError):
        map_invoice_to_accounting_fields({'invoice_number': '1'}, {})


def test_raises_when_config_supplier_mismatches_invoice_supplier():
    config = dict(_REFERENCE_CONFIG, supplier_id=5)
    invoice = {'invoice_number': '1', 'supplier_id': 6}
    with pytest.raises(ValueError):
        map_invoice_to_accounting_fields(invoice, config)


def test_no_mismatch_error_when_supplier_ids_match_or_absent():
    config = dict(_REFERENCE_CONFIG, supplier_id=5)
    invoice = {'invoice_number': '1', 'supplier_id': 5}
    result = map_invoice_to_accounting_fields(invoice, config)
    assert result['klient'] == '140'

    # config without supplier_id never conflicts, regardless of invoice.supplier_id
    result2 = map_invoice_to_accounting_fields({'invoice_number': '1', 'supplier_id': 999}, _REFERENCE_CONFIG)
    assert result2['klient'] == '140'


def test_none_config_fields_map_to_empty_string_not_invented():
    config = {
        'klient': None, 'konto_credit': None, 'konto_debit': None,
        'gegenkonto_credit': None, 'gegenkonto_debit': None,
        'kostenstelle_debit': None, 'kostenstelle_credit': None,
        'extbeleg_credit': None, 'extbeleg_debit': None,
    }
    result = map_invoice_to_accounting_fields({'invoice_number': '17278'}, config)
    assert result == {
        'konto_debit': '', 'konto_credit': '', 'klient': '',
        'gegenkonto_debit': '', 'gegenkonto_credit': '',
        'kostenstelle_debit': '', 'kostenstelle_credit': '',
        'extbeleg_debit': '', 'extbeleg_credit': '',
    }


def test_extbeleg_debit_directive_also_honored():
    config = dict(_REFERENCE_CONFIG, extbeleg_credit='', extbeleg_debit='invoice_number')
    result = map_invoice_to_accounting_fields({'invoice_number': '99887'}, config)
    assert result['extbeleg_debit'] == '99887'
    assert result['extbeleg_credit'] == ''
