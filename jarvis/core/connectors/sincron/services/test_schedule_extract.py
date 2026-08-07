"""Tests for employee-schedule extraction from Sincron timesheet activities.

Loads schedule_extract.py directly by path so the suite has zero app/DB deps.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'sincron_schedule_extract', Path(__file__).with_name('schedule_extract.py'))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
extract_employee_schedule = _mod.extract_employee_schedule


def test_prefers_oz_program_over_leave():
    # OZ is the worked schedule and must win even if a leave day is seen first.
    days = {
        '2026-07-01': [{'short_code': 'CM', 'program': {'in': '09:00', 'out': '12:00', 'pauza_masa': 0}}],
        '2026-07-02': [{'short_code': 'OZ', 'program': {'in': '08:00', 'out': '16:00', 'pauza_masa': 30}}],
    }
    assert extract_employee_schedule(days) == ('08:00', '16:00', 30)


def test_falls_back_to_leave_program_when_no_oz():
    # Ivascu case: whole month is CM/CMS, no OZ — Sincron still carries the
    # contracted program on the leave rows, so we must use it.
    days = {
        '2026-07-01': [
            {'short_code': 'CMS', 'program': {'in': '08:00', 'out': '17:00', 'pauza_masa': 60}},
            {'short_code': 'CM', 'program': {'in': '08:00', 'out': '17:00', 'pauza_masa': 60}},
        ],
    }
    assert extract_employee_schedule(days) == ('08:00', '17:00', 60)


def test_none_when_no_activity_has_a_program():
    days = {
        '2026-07-01': [{'short_code': 'X'}, {'short_code': 'OZ', 'program': {}}],
    }
    assert extract_employee_schedule(days) == (None, None, None)


def test_empty_days_returns_none():
    assert extract_employee_schedule({}) == (None, None, None)
    assert extract_employee_schedule(None) == (None, None, None)
