"""Pure-logic tests for granular event-bonus presence days.

An event bonus is attended on a set of specific full days (not a contiguous
window). These helpers validate the days against the event range, derive the
stored bonus fields, and split the money pro-rata across the calendar months
the days fall in (so a bonus spanning a month boundary shows in both months).
"""
import datetime as dt

import pytest

from hr.events import presence

EVENT_START = dt.date(2026, 1, 30)
EVENT_END = dt.date(2026, 2, 3)


# ---- normalize_presence_days ----

def test_normalize_sorts_and_dedupes():
    days = ['2026-02-02', '2026-01-31', '2026-01-31']
    assert presence.normalize_presence_days(days, EVENT_START, EVENT_END) == [
        dt.date(2026, 1, 31), dt.date(2026, 2, 2)]


def test_normalize_accepts_date_and_datetime_objects():
    days = [dt.date(2026, 1, 31), dt.datetime(2026, 2, 2, 9, 0)]
    assert presence.normalize_presence_days(days, EVENT_START, EVENT_END) == [
        dt.date(2026, 1, 31), dt.date(2026, 2, 2)]


def test_normalize_rejects_day_before_event():
    with pytest.raises(ValueError):
        presence.normalize_presence_days(['2026-01-29'], EVENT_START, EVENT_END)


def test_normalize_rejects_day_after_event():
    with pytest.raises(ValueError):
        presence.normalize_presence_days(['2026-02-04'], EVENT_START, EVENT_END)


def test_normalize_rejects_empty():
    with pytest.raises(ValueError):
        presence.normalize_presence_days([], EVENT_START, EVENT_END)


# ---- derive_bonus_fields ----

def test_derive_primary_month_is_earliest_day():
    days = [dt.date(2026, 2, 2), dt.date(2026, 1, 31)]
    f = presence.derive_bonus_fields(days)
    assert f['bonus_days'] == 2
    assert f['participation_start'] == dt.date(2026, 1, 31)
    assert f['participation_end'] == dt.date(2026, 2, 2)
    assert f['year'] == 2026
    assert f['month'] == 1  # earliest day's month, not latest


# ---- months_touched ----

def test_months_touched_spanning_boundary():
    days = [dt.date(2026, 2, 2), dt.date(2026, 1, 31)]
    assert presence.months_touched(days) == [(2026, 1), (2026, 2)]


# ---- check_months_editable ----

def test_months_editable_when_none_locked():
    editable, locked = presence.check_months_editable(
        [(2026, 1), (2026, 2)], lambda y, m: False)
    assert editable is True
    assert locked == []


def test_months_blocked_when_any_locked():
    editable, locked = presence.check_months_editable(
        [(2026, 1), (2026, 2)], lambda y, m: m == 1)
    assert editable is False
    assert locked == [(2026, 1)]
