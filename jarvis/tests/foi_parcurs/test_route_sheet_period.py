"""Regression tests for route_sheet_service._period — the month-bucketing that
decides which sessions a monthly Foaie de Parcurs (PDF + Excel) includes.

Bug: `get_contracts` returns rows via `dict_from_row`, which serializes
`created_at` to an ISO *string*. `_period` used `isinstance(created_at, datetime)`
and so fell to None for string rows. Test-drive sessions have NULL year/month
(only the Excel/batch-import path sets them), so `_period` returned (None, None)
for every TD session → the aggregate found nothing → blank PDF *and* Excel, even
though the car showed in the list (the frontend parses created_at with `new Date`).
"""
from datetime import datetime

from foi_parcurs.services.route_sheet_service import _period


def test_period_parses_iso_string_created_at_when_year_month_null():
    # dict_from_row serializes created_at to an ISO string; TD sessions have NULL year/month.
    c = {'year': None, 'month': None, 'created_at': '2026-07-15T09:30:00'}
    assert _period(c) == (2026, 7)


def test_period_parses_iso_string_with_trailing_z():
    c = {'year': None, 'month': None, 'created_at': '2026-07-15T09:30:00Z'}
    assert _period(c) == (2026, 7)


def test_period_prefers_explicit_year_month_columns():
    # When the import path set year/month, they win over created_at.
    c = {'year': 2026, 'month': 3, 'created_at': '2026-07-15T09:30:00'}
    assert _period(c) == (2026, 3)


def test_period_handles_datetime_created_at():
    c = {'year': None, 'month': None, 'created_at': datetime(2026, 5, 2, 8, 0)}
    assert _period(c) == (2026, 5)


def test_period_none_when_no_date_and_no_columns():
    c = {'year': None, 'month': None, 'created_at': None}
    assert _period(c) == (None, None)
