"""Tests for reservation_rules — pure duration + overlap helpers.

These back the three reservation rules the Dispo reserve flow enforces:
multiple reservations allowed, no overlapping date ranges, max 3 days each.
No DB access; pure date math.
"""
from datetime import date, datetime

from carpark.services.reservation_rules import (
    MAX_RESERVATION_DAYS,
    exceeds_max_duration,
    ends_before_start,
    intervals_overlap,
    find_conflict,
)


# ── END-BEFORE-START ─────────────────────────────────────────────────────

def test_end_before_start_is_rejected():
    assert ends_before_start(date(2026, 9, 5), date(2026, 9, 1)) is True


def test_end_equal_or_after_start_is_ok():
    assert ends_before_start(date(2026, 9, 1), date(2026, 9, 1)) is False
    assert ends_before_start(date(2026, 9, 1), date(2026, 9, 3)) is False


# ── DURATION (3-day max) ─────────────────────────────────────────────────

def test_three_day_span_is_allowed():
    assert exceeds_max_duration(date(2026, 9, 1), date(2026, 9, 4)) is False


def test_four_day_span_exceeds_max():
    assert exceeds_max_duration(date(2026, 9, 1), date(2026, 9, 5)) is True


def test_same_day_start_end_is_allowed():
    assert exceeds_max_duration(date(2026, 9, 1), date(2026, 9, 1)) is False


def test_duration_accepts_iso_strings():
    assert exceeds_max_duration('2026-09-01', '2026-09-10') is True
    assert exceeds_max_duration('2026-09-01', '2026-09-03') is False


def test_duration_accepts_datetimes():
    # Calendar-day span (date-only UI): 4 full days exceeds the limit.
    assert exceeds_max_duration(
        datetime(2026, 9, 1, 9, 0), datetime(2026, 9, 5, 10, 0)) is True
    assert exceeds_max_duration(
        datetime(2026, 9, 1, 9, 0), datetime(2026, 9, 4, 8, 0)) is False


def test_max_days_constant_is_three():
    assert MAX_RESERVATION_DAYS == 3


# ── OVERLAP ──────────────────────────────────────────────────────────────

def test_overlapping_ranges_overlap():
    assert intervals_overlap(
        date(2026, 9, 1), date(2026, 9, 4),
        date(2026, 9, 3), date(2026, 9, 6)) is True


def test_touching_endpoints_do_not_overlap():
    # One ends exactly when the next starts — back-to-back is fine.
    assert intervals_overlap(
        date(2026, 9, 1), date(2026, 9, 4),
        date(2026, 9, 4), date(2026, 9, 6)) is False


def test_disjoint_ranges_do_not_overlap():
    assert intervals_overlap(
        date(2026, 9, 1), date(2026, 9, 2),
        date(2026, 9, 5), date(2026, 9, 6)) is False


def test_null_end_is_open_ended_and_overlaps_anything_after_start():
    # An existing reservation with no end date blocks everything from its start on.
    assert intervals_overlap(
        date(2026, 9, 10), date(2026, 9, 11),
        date(2026, 9, 1), None) is True


def test_fully_contained_range_overlaps():
    assert intervals_overlap(
        date(2026, 9, 2), date(2026, 9, 3),
        date(2026, 9, 1), date(2026, 9, 10)) is True


# ── find_conflict (against a list of existing reservations) ──────────────

def test_find_conflict_returns_overlapping_reservation():
    existing = [
        {'id': 1, 'reservation_start': date(2026, 9, 1), 'reservation_end': date(2026, 9, 2)},
        {'id': 2, 'reservation_start': date(2026, 9, 5), 'reservation_end': date(2026, 9, 8)},
    ]
    conflict = find_conflict(date(2026, 9, 6), date(2026, 9, 7), existing)
    assert conflict is not None
    assert conflict['id'] == 2


def test_find_conflict_returns_none_when_free():
    existing = [
        {'id': 1, 'reservation_start': date(2026, 9, 1), 'reservation_end': date(2026, 9, 2)},
    ]
    assert find_conflict(date(2026, 9, 5), date(2026, 9, 6), existing) is None


def test_find_conflict_ignores_reservations_without_start():
    # Defensive: a malformed row with no start can't be reasoned about; skip it.
    existing = [{'id': 9, 'reservation_start': None, 'reservation_end': None}]
    assert find_conflict(date(2026, 9, 5), date(2026, 9, 6), existing) is None
