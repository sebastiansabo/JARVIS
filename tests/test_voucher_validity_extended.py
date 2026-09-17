"""Validity range extended to include 36 and 48 months.

Vouchers previously capped validity at 24 months. Business now issues longer
vouchers (36 / 48 months), so both the create schema (VoucherCreate) and the
admin edit path (build_admin_voucher_edit) must accept the extended set while
still rejecting arbitrary values.
"""
import os
import sys

import pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.vouchers.schemas import VoucherCreate
from accounting.vouchers.edit_logic import build_admin_voucher_edit


def _create_payload(months):
    return dict(
        client_name='ACME SRL',
        contract_number='C-123',
        car_vin='WVWZZZ1JZXW000001',
        validity_months=months,
        voucher_type='value',
        value_lei=100,
    )


@pytest.mark.parametrize('months', [1, 3, 6, 12, 24, 36, 48])
def test_create_accepts_supported_validity(months):
    voucher = VoucherCreate(**_create_payload(months))
    assert voucher.validity_months == months


@pytest.mark.parametrize('months', [0, 5, 18, 60, 100])
def test_create_rejects_unsupported_validity(months):
    with pytest.raises(ValueError):
        VoucherCreate(**_create_payload(months))


@pytest.mark.parametrize('months', [1, 3, 6, 12, 24, 36, 48])
def test_admin_edit_accepts_supported_validity(months):
    updates, _diff = build_admin_voucher_edit({}, {'validity_months': months})
    assert updates['validity_months'] == months


@pytest.mark.parametrize('months', [0, 5, 18, 60])
def test_admin_edit_rejects_unsupported_validity(months):
    with pytest.raises(ValueError):
        build_admin_voucher_edit({}, {'validity_months': months})
