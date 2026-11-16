"""Guard: get_today_punches stays sargable.

The query filtered with `event_datetime::date = %s`, which casts every row's
date and can't use an index on event_datetime — it scanned a user's whole punch
history and was a cause of the /mobile-checkin/api/status 504s. The fix uses a
half-open day range `[date, date+1day)` served by the
(biostar_user_id, event_datetime) composite index. This spy guards against a
regression back to the column cast (behavior-identical results + index usage
were verified directly against Postgres).
"""
from core.checkin.repository import CheckinRepository


def test_get_today_punches_uses_sargable_range_not_date_cast():
    repo = CheckinRepository()
    captured = {}
    repo.query_all = lambda sql, params: captured.update(sql=sql, params=params) or []

    repo.get_today_punches('b1', '2026-11-10')

    sql = captured['sql']
    assert 'event_datetime::date' not in sql, 'non-sargable date cast reintroduced'
    assert 'event_datetime >=' in sql
    assert "+ INTERVAL '1 day'" in sql
    # date_str is bound twice (range start + end); user id first.
    assert captured['params'] == ('b1', '2026-11-10', '2026-11-10')
