"""Tests for Sincron trailing-X termination detection.

Loads termination.py directly by path so the suite has zero app/DB deps.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'sincron_termination', Path(__file__).with_name('termination.py'))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
detect_termination = _mod.detect_termination


def _days(spec):
    """Build a Sincron-shaped days dict: {day: [{'short_code': c}, ...]}.

    spec: dict of {day_str: 'CODE' or ['CODE', ...]}.
    """
    out = {}
    for day, codes in spec.items():
        if isinstance(codes, str):
            codes = [codes]
        out[day] = [{'short_code': c, 'short_code_en': c, 'unit': 'day', 'value': '1.00'}
                    for c in codes]
    return out


def _range(start_day, end_day, code):
    return {f'2026-07-{d:02d}': code for d in range(start_day, end_day + 1)}


def test_trailing_x_after_last_oz_is_termination():
    # Pop Maria: worked through Jul 6, then X to month end
    days = _days({**_range(1, 6, 'OZ'), **_range(7, 31, 'X')})
    result = detect_termination(days)
    assert result['terminated'] is True
    assert result['last_worked_day'] == '2026-07-06'
    assert result['termination_from'] == '2026-07-07'


def test_leading_x_before_first_oz_is_new_hire_not_termination():
    # Szigeti: pre-hire X Jul 1-13, then works from Jul 14
    days = _days({**_range(1, 13, 'X'), **_range(14, 31, 'OZ')})
    assert detect_termination(days)['terminated'] is False


def test_full_month_medical_leave_is_not_termination():
    # Ivascu: CM/CMS every working day, no X at all
    days = _days({f'2026-07-{d:02d}': ['CM', 'CMS'] for d in range(1, 24)})
    assert detect_termination(days)['terminated'] is False


def test_full_month_worked_is_not_termination():
    days = _days(_range(1, 31, 'OZ'))
    assert detect_termination(days)['terminated'] is False


def test_empty_days_is_not_termination():
    assert detect_termination({})['terminated'] is False


def test_trailing_x_after_leave_code_is_termination():
    # Worked, then vacation (CO), then terminated -> X trails the last real activity
    days = _days({**_range(1, 3, 'OZ'), **_range(4, 10, 'CO'), **_range(11, 31, 'X')})
    result = detect_termination(days)
    assert result['terminated'] is True
    assert result['last_worked_day'] == '2026-07-10'
    assert result['termination_from'] == '2026-07-11'


def test_day_with_both_x_and_work_counts_as_active():
    # A day carrying OZ + X is a real activity day, not an out-of-contract day
    days = _days({**_range(1, 30, 'OZ'), '2026-07-31': ['OZ', 'X']})
    assert detect_termination(days)['terminated'] is False
