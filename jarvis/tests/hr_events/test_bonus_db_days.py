"""Real-DB tests for the LIVE bonus path in hr/events/database.py.

Covers: presence-day writes (atomic + derived fields) on save/update, and the
month-split reads (a bonus whose days straddle a month boundary is reported in
both months with pro-rata amounts). localhost/defaultdb only; else skipped.
"""
from datetime import date

from hr.events import database as db


def _read_days(cur, bonus_id):
    cur.execute("SELECT day FROM hr.event_bonus_days WHERE bonus_id=%s ORDER BY day",
                (bonus_id,))
    return [r['day'].isoformat() for r in cur.fetchall()]


def test_save_writes_days_and_derives_fields(hr_ctx):
    conn, cur, ctx = hr_ctx
    # deliberately-wrong year/month/bonus_days to prove they are derived from days
    bonus_id = db.save_event_bonus(
        employee_id=ctx['user_id'], event_id=ctx['event_id'],
        year=1900, month=12, bonus_days=99, bonus_net=200,
        presence_days=[date(2099, 1, 31), date(2099, 2, 2)])
    cur.execute("""SELECT year, month, bonus_days, participation_start, participation_end
                   FROM hr.event_bonuses WHERE id=%s""", (bonus_id,))
    row = cur.fetchone()
    assert row['year'] == 2099
    assert row['month'] == 1                      # earliest day's month
    assert float(row['bonus_days']) == 2
    assert row['participation_start'].isoformat() == '2099-01-31'
    assert row['participation_end'].isoformat() == '2099-02-02'
    assert _read_days(cur, bonus_id) == ['2099-01-31', '2099-02-02']


def test_update_replaces_days_and_rederives(hr_ctx):
    conn, cur, ctx = hr_ctx
    bonus_id = db.save_event_bonus(
        employee_id=ctx['user_id'], event_id=ctx['event_id'],
        year=2099, month=1, bonus_net=100,
        presence_days=[date(2099, 1, 30), date(2099, 1, 31)])
    db.update_event_bonus(
        bonus_id, employee_id=ctx['user_id'], event_id=ctx['event_id'],
        year=2099, month=1, bonus_net=100, presence_days=[date(2099, 2, 1)])
    assert _read_days(cur, bonus_id) == ['2099-02-01']
    cur.execute("SELECT month, bonus_days FROM hr.event_bonuses WHERE id=%s", (bonus_id,))
    row = cur.fetchone()
    assert row['month'] == 2
    assert float(row['bonus_days']) == 1


def test_get_bonuses_by_month_splits_cross_month(hr_ctx):
    conn, cur, ctx = hr_ctx
    db.save_event_bonus(
        employee_id=ctx['user_id'], event_id=ctx['event_id'],
        year=2099, month=1, bonus_net=200,
        presence_days=[date(2099, 1, 31), date(2099, 2, 2)])
    rows = {r['month']: r for r in db.get_bonuses_by_month(2099)}
    assert float(rows[1]['total']) == 100.0
    assert float(rows[2]['total']) == 100.0


def test_get_all_month_filter_shows_bonus_in_both_months(hr_ctx):
    conn, cur, ctx = hr_ctx
    db.save_event_bonus(
        employee_id=ctx['user_id'], event_id=ctx['event_id'],
        year=2099, month=1, bonus_net=200,
        presence_days=[date(2099, 1, 31), date(2099, 2, 2)])
    jan = db.get_all_event_bonuses(year=2099, month=1, event_id=ctx['event_id'])
    feb = db.get_all_event_bonuses(year=2099, month=2, event_id=ctx['event_id'])
    assert len(jan) == 1 and len(feb) == 1
    assert float(jan[0]['period_bonus_net']) == 100.0
    assert float(feb[0]['period_bonus_net']) == 100.0
    assert int(jan[0]['period_bonus_days']) == 1


def test_get_bonuses_by_event_splits_cross_month(hr_ctx):
    conn, cur, ctx = hr_ctx
    db.save_event_bonus(
        employee_id=ctx['user_id'], event_id=ctx['event_id'],
        year=2099, month=1, bonus_net=200,
        presence_days=[date(2099, 1, 31), date(2099, 2, 2)])
    rows = {(r['year'], r['month']): r for r in db.get_bonuses_by_event(year=2099)}
    assert float(rows[(2099, 1)]['total_bonus']) == 100.0
    assert float(rows[(2099, 2)]['total_bonus']) == 100.0


def test_get_bonuses_by_employee_splits_by_month(hr_ctx):
    conn, cur, ctx = hr_ctx
    db.save_event_bonus(
        employee_id=ctx['user_id'], event_id=ctx['event_id'],
        year=2099, month=1, bonus_net=200,
        presence_days=[date(2099, 1, 31), date(2099, 2, 2)])
    jan = {r['id']: r for r in db.get_bonuses_by_employee(year=2099, month=1)}
    assert float(jan[ctx['user_id']]['total_bonus']) == 100.0
    assert int(jan[ctx['user_id']]['total_days']) == 1
