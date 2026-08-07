"""Real-DB tests for month-aware profile bonuses (mobile + web inherit).

A bonus whose days straddle a month boundary must appear under BOTH months with
that month's pro-rata amount; legacy rows without day rows still appear under
their stored month with the full amount.
"""
from datetime import date

from hr.events import database as db
from core.profile.repositories.profile_repository import ProfileRepository
from .conftest import make_bonus


def _by_id(rows):
    return {r['id']: r for r in rows}


def test_cross_month_bonus_shows_portion_in_each_month(hr_ctx):
    conn, cur, ctx = hr_ctx
    bonus_id = db.save_event_bonus(
        employee_id=ctx['user_id'], event_id=ctx['event_id'],
        year=2099, month=1, bonus_net=200,
        presence_days=[date(2099, 1, 31), date(2099, 2, 2)])
    repo = ProfileRepository()

    jan = _by_id(repo.get_user_event_bonuses(ctx['user_id'], year=2099, month=1))
    feb = _by_id(repo.get_user_event_bonuses(ctx['user_id'], year=2099, month=2))
    assert float(jan[bonus_id]['bonus_net']) == 100.0
    assert float(jan[bonus_id]['bonus_days']) == 1
    assert float(feb[bonus_id]['bonus_net']) == 100.0


def test_legacy_bonus_without_day_rows_still_appears(hr_ctx):
    conn, cur, ctx = hr_ctx
    legacy_id = make_bonus(cur, ctx, year=2099, month=1, bonus_net=50, bonus_days=1)
    conn.commit()  # no day rows for this one
    repo = ProfileRepository()

    jan = _by_id(repo.get_user_event_bonuses(ctx['user_id'], year=2099, month=1))
    feb = _by_id(repo.get_user_event_bonuses(ctx['user_id'], year=2099, month=2))
    assert legacy_id in jan
    assert float(jan[legacy_id]['bonus_net']) == 50.0   # full amount (fallback)
    assert legacy_id not in feb                          # not in the other month
