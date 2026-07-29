"""Regression test: negative (storno/credit-note) invoices must budget on NET, not gross.

Bug: `net_value > 0` disabled net-based budgeting for negative invoices, so their
allocations were computed on the gross (with-VAT) value instead of the net value.
"""
from decimal import Decimal

from core.connectors.efactura.services.invoice_allocation_service import net_vat_fields


def test_positive_invoice_enables_net_budgeting():
    subtract_vat, vat_rate = net_vat_fields(Decimal('2041.32'), Decimal('1687.04'))
    assert subtract_vat is True
    assert abs(float(vat_rate) - 21.0) < 0.05


def test_negative_invoice_enables_net_budgeting():
    # Before the fix this returned (False, None) → allocations fell back to gross.
    subtract_vat, vat_rate = net_vat_fields(Decimal('-2041.32'), Decimal('-1687.04'))
    assert subtract_vat is True
    assert abs(float(vat_rate) - 21.0) < 0.05


def test_negative_matches_positive_of_same_magnitude():
    pos = net_vat_fields(Decimal('2041.32'), Decimal('1687.04'))
    neg = net_vat_fields(Decimal('-2041.32'), Decimal('-1687.04'))
    assert neg == pos


def test_zero_net_keeps_gross_budgeting():
    assert net_vat_fields(Decimal('100'), Decimal('0')) == (False, None)


def test_missing_net_keeps_gross_budgeting():
    assert net_vat_fields(Decimal('100'), None) == (False, None)


def test_works_with_plain_floats():
    subtract_vat, vat_rate = net_vat_fields(-2041.32, -1687.04)
    assert subtract_vat is True
    assert abs(vat_rate - 21.0) < 0.05
