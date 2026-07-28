from datetime import datetime, timedelta, timezone
from foi_parcurs.session_lifecycle import GRACE_HOURS, derive_planned_substatus, TD_STATUS_SQL, NOW_LOCAL_SQL

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

def test_grace_is_eight_hours():
    assert GRACE_HOURS == 8

def test_future_departure_is_planned():
    assert derive_planned_substatus(NOW + timedelta(hours=1), NOW) == 'planned'

def test_just_past_departure_is_late():
    assert derive_planned_substatus(NOW - timedelta(minutes=1), NOW) == 'late'
    assert derive_planned_substatus(NOW - timedelta(hours=7, minutes=59), NOW) == 'late'

def test_at_or_past_grace_is_missed():
    assert derive_planned_substatus(NOW - timedelta(hours=8), NOW) == 'missed'
    assert derive_planned_substatus(NOW - timedelta(hours=9), NOW) == 'missed'

def test_none_departure_is_planned():
    assert derive_planned_substatus(None, NOW) == 'planned'

def test_sql_fragment_mentions_missed_and_late_and_interval():
    assert "'missed'" in TD_STATUS_SQL
    assert "'late'" in TD_STATUS_SQL
    assert "INTERVAL '8 hours'" in TD_STATUS_SQL
    assert 'AS td_status' in TD_STATUS_SQL


def test_sql_fragment_compares_against_bucharest_local_time_not_bare_now():
    # Regression guard: departure/return comparisons must go through the
    # Europe/Bucharest wall-clock expression, not bare NOW() — a bare NOW()
    # compares fine on a Bucharest-session localhost DB but fires ~2-3h late
    # against production's UTC DB session.
    assert "AT TIME ZONE 'Europe/Bucharest'" in TD_STATUS_SQL
    assert NOW_LOCAL_SQL is not None
    assert "AT TIME ZONE 'Europe/Bucharest'" in NOW_LOCAL_SQL
