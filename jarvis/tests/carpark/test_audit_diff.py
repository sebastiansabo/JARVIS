"""value_changed() must ignore the type/format differences a full-form re-save
introduces (DB Decimal vs form int/float, DATE object vs ISO string) so the
vehicle audit trail only logs genuinely-changed fields — not ~90 spurious rows
on every save."""
import datetime
from decimal import Decimal

from carpark.audit_diff import value_changed


def test_both_none_is_not_a_change():
    assert value_changed(None, None) is False


def test_none_to_value_is_a_change():
    assert value_changed(None, 5) is True


def test_value_to_none_is_a_change():
    assert value_changed(5, None) is True


def test_decimal_equals_int_is_not_a_change():
    # DB returns Decimal('45000.00'); the form submits 45000.
    assert value_changed(Decimal('45000.00'), 45000) is False


def test_decimal_equals_float_is_not_a_change():
    assert value_changed(Decimal('45000.00'), 45000.0) is False


def test_numeric_string_equals_number_is_not_a_change():
    assert value_changed('45000', 45000) is False


def test_different_numbers_is_a_change():
    assert value_changed(45000, 45001) is True


def test_zero_decimal_equals_zero_is_not_a_change():
    assert value_changed(Decimal('0.00'), 0) is False


def test_date_object_equals_iso_string_is_not_a_change():
    # DATE columns come back as date objects; the form submits 'YYYY-MM-DD'.
    assert value_changed(datetime.date(2020, 1, 1), '2020-01-01') is False


def test_equal_strings_is_not_a_change():
    assert value_changed('Rulat', 'Rulat') is False


def test_different_strings_is_a_change():
    assert value_changed('petrol', 'diesel') is True


def test_equal_bools_is_not_a_change():
    assert value_changed(True, True) is False


def test_different_bools_is_a_change():
    assert value_changed(True, False) is True


def test_bool_is_not_coerced_to_number():
    # True must not compare equal to 1 (a bool flip is a real change).
    assert value_changed(True, 0) is True
