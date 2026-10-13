"""Tests for VoucherCreate validation rules.

Covers two hardening changes:
  * the 'accessory_percentage' type is no longer accepted for new issuance
    (soft-removed — legacy rows keep working, but you cannot create one);
  * ``value_lei`` must be a positive amount within a sane cap (no negative,
    zero, or absurd values).
"""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from accounting.vouchers.schemas import VoucherCreate, VALUE_LEI_MAX


def _base(**overrides):
    data = {
        'client_name': 'Client',
        'contract_number': '100',
        'car_vin': 'LSJWS4394SZ328671',
        'validity_months': 12,
        'voucher_type': 'value',
        'value_lei': Decimal('500.00'),
    }
    data.update(overrides)
    return data


def test_value_voucher_valid():
    v = VoucherCreate(**_base())
    assert v.voucher_type == 'value'
    assert v.value_lei == Decimal('500.00')


def test_percentage_type_rejected_for_new_issuance():
    with pytest.raises(ValidationError):
        VoucherCreate(**_base(voucher_type='accessory_percentage',
                              value_lei=None, discount_percentage=Decimal('10')))


def test_discount_code_type_still_valid():
    v = VoucherCreate(**_base(voucher_type='accessory_discount_code',
                              value_lei=None, discount_code='SAVE10'))
    assert v.voucher_type == 'accessory_discount_code'


def test_service_items_type_still_valid():
    v = VoucherCreate(**_base(voucher_type='service_items',
                              value_lei=None, service_items=['Oil change']))
    assert v.service_items == ['Oil change']


def test_value_lei_zero_rejected():
    with pytest.raises(ValidationError):
        VoucherCreate(**_base(value_lei=Decimal('0')))


def test_value_lei_negative_rejected():
    with pytest.raises(ValidationError):
        VoucherCreate(**_base(value_lei=Decimal('-100')))


def test_value_lei_above_cap_rejected():
    with pytest.raises(ValidationError):
        VoucherCreate(**_base(value_lei=Decimal(VALUE_LEI_MAX) + 1))


def test_value_lei_at_cap_allowed():
    v = VoucherCreate(**_base(value_lei=Decimal(VALUE_LEI_MAX)))
    assert v.value_lei == Decimal(VALUE_LEI_MAX)
