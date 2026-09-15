"""Unit tests for voucher issue/expiry date computation.

Regression: pending/rejected/reissued vouchers used to show no Issue/Expiry
date because those columns were only populated on approval (activate_voucher).
Dates are now anchored at creation via compute_voucher_dates(), so they appear
everywhere (list, detail, PDF, CSV, email) from the moment a voucher exists.
"""
import os
import sys
from datetime import date

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.vouchers.repositories.voucher_repository import compute_voucher_dates


def test_explicit_start_date_anchors_issue_and_expiry():
    issued, expires = compute_voucher_dates(date(2026, 9, 1), 6)
    assert issued == date(2026, 9, 1)
    assert expires == date(2027, 3, 1)


def test_none_start_date_falls_back_to_today():
    today = date.today()
    issued, expires = compute_voucher_dates(None, 12)
    assert issued == today
    assert expires == date(today.year + 1, today.month, today.day)


def test_string_start_date_is_parsed():
    issued, expires = compute_voucher_dates('2026-06-23', 6)
    assert issued == date(2026, 6, 23)
    assert expires == date(2026, 12, 23)


def test_validity_months_as_string_is_coerced():
    issued, expires = compute_voucher_dates(date(2026, 1, 15), '3')
    assert issued == date(2026, 1, 15)
    assert expires == date(2026, 4, 15)
