"""Tests for the presence-day route helpers in hr/events/routes/_shared.py."""
import datetime as dt

import pytest

from hr.events.routes import _shared


def test_resolve_presence_days_valid(hr_ctx):
    conn, cur, ctx = hr_ctx
    data = {'event_id': ctx['event_id'], 'presence_days': ['2099-02-02', '2099-01-31']}
    assert _shared.resolve_presence_days(data) == [dt.date(2099, 1, 31), dt.date(2099, 2, 2)]


def test_resolve_presence_days_out_of_range_raises(hr_ctx):
    conn, cur, ctx = hr_ctx
    # event ends 2099-02-03; a March day is outside the range
    data = {'event_id': ctx['event_id'], 'presence_days': ['2099-03-01']}
    with pytest.raises(ValueError):
        _shared.resolve_presence_days(data)


def test_resolve_presence_days_absent_returns_none(hr_ctx):
    conn, cur, ctx = hr_ctx
    assert _shared.resolve_presence_days({'event_id': ctx['event_id']}) is None


def test_check_presence_months_editable_blocks_locked_month(monkeypatch):
    monkeypatch.setattr(
        _shared, 'can_edit_bonus',
        lambda y, m, role: (False, 'month locked') if m == 1 else (True, ''))
    ok, reason = _shared.check_presence_months_editable(
        [dt.date(2099, 1, 31), dt.date(2099, 2, 2)], 'User')
    assert ok is False
    assert reason == 'month locked'


def test_check_presence_months_editable_allows_when_unlocked(monkeypatch):
    monkeypatch.setattr(_shared, 'can_edit_bonus', lambda y, m, role: (True, ''))
    ok, reason = _shared.check_presence_months_editable([dt.date(2099, 2, 2)], 'User')
    assert ok is True
