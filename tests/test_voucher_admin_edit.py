"""Tests for the admin full-edit pure helper (accounting.vouchers.edit_logic).

The helper computes the column updates + audit diff for an admin editing a
voucher. It is free of Flask/DB so we can exercise every branch directly.
"""
from datetime import date
from decimal import Decimal

import pytest

from accounting.vouchers.edit_logic import build_admin_voucher_edit


def _voucher(**overrides):
    """A baseline active 'value' voucher row as get_by_id would return it."""
    base = {
        'id': 1,
        'company_id': 16,
        'voucher_code': 'VCH-202609-ABC123',
        'client_name': 'Old Client',
        'contract_number': '100',
        'car_vin': 'LSJWS4394SZ328671',
        'validity_months': 12,
        'voucher_type': 'value',
        'value_lei': Decimal('500.00'),
        'discount_code': None,
        'discount_percentage': None,
        'service_items': None,
        'status': 'active',
        'start_date': date(2026, 1, 1),
        'issued_at': date(2026, 1, 1),
        'expires_at': date(2027, 1, 1),
        'client_email': None,
        'client_cif': None,
        'notes': None,
        'redemption_notes': None,
    }
    base.update(overrides)
    return base


def test_text_field_change_is_updated_and_audited():
    updates, changes = build_admin_voucher_edit(_voucher(), {'client_name': 'New Client'})
    assert updates['client_name'] == 'New Client'
    assert changes['client_name'] == {'old': 'Old Client', 'new': 'New Client'}


def test_status_active_fills_dates_when_missing():
    existing = _voucher(status='pending_approval', issued_at=None, expires_at=None,
                        start_date=date(2026, 3, 1), validity_months=6)
    updates, _ = build_admin_voucher_edit(existing, {'status': 'active'})
    assert updates['status'] == 'active'
    assert updates['issued_at'] == date(2026, 3, 1)
    assert updates['expires_at'] == date(2026, 9, 1)


def test_status_active_does_not_overwrite_existing_dates():
    existing = _voucher(status='pending_approval')  # issued/expires already set
    updates, _ = build_admin_voucher_edit(existing, {'status': 'active'})
    assert updates['status'] == 'active'
    assert 'issued_at' not in updates
    assert 'expires_at' not in updates


def test_type_change_nulls_other_benefit_fields():
    existing = _voucher()  # value / value_lei = 500
    updates, changes = build_admin_voucher_edit(
        existing, {'voucher_type': 'accessory_percentage', 'discount_percentage': 10}
    )
    assert updates['voucher_type'] == 'accessory_percentage'
    assert updates['discount_percentage'] == Decimal('10')
    assert updates['value_lei'] is None
    assert changes['value_lei'] == {'old': '500.00', 'new': None}


def test_benefit_edit_without_type_change_updates_value_only():
    updates, _ = build_admin_voucher_edit(_voucher(), {'value_lei': 750})
    assert updates['value_lei'] == Decimal('750')
    assert 'discount_code' not in updates  # other benefit fields left untouched


def test_invalid_status_raises():
    with pytest.raises(ValueError):
        build_admin_voucher_edit(_voucher(), {'status': 'bogus'})


def test_invalid_vin_raises():
    with pytest.raises(ValueError):
        build_admin_voucher_edit(_voucher(), {'car_vin': 'TOOSHORT'})


def test_invalid_validity_raises():
    with pytest.raises(ValueError):
        build_admin_voucher_edit(_voucher(), {'validity_months': 7})


def test_no_effective_change_yields_empty_changes():
    # Re-sending the current type + value should not be flagged as a change,
    # even though Decimal('500') vs Decimal('500.00') differ textually.
    updates, changes = build_admin_voucher_edit(
        _voucher(), {'voucher_type': 'value', 'value_lei': 500, 'client_name': 'Old Client'}
    )
    assert changes == {}


def test_date_field_accepts_iso_string():
    updates, _ = build_admin_voucher_edit(_voucher(), {'expires_at': '2028-05-15'})
    assert updates['expires_at'] == date(2028, 5, 15)


def test_empty_string_email_normalized_to_none():
    updates, _ = build_admin_voucher_edit(_voucher(client_email='x@y.z'), {'client_email': ''})
    assert updates['client_email'] is None
