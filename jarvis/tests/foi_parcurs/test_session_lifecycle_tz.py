"""Integration test proving the Europe/Bucharest tz-comparison fix in
foi_parcurs.session_lifecycle / foi_parcurs_repository.

Background: departure_datetime/return_datetime on foi_de_parcurs are naive
Bucharest wall-clock values stored in timestamptz columns. Production's DB
session runs in UTC, so comparing them against bare NOW() (a UTC instant
there) fires the late/missed detection ~2-3h late. The fix compares against
NOW_LOCAL_SQL = (NOW() AT TIME ZONE 'Europe/Bucharest')::timestamptz instead,
mirroring the compensation record_return already applies.

This test simulates production by forcing the DB session to UTC and proving a
session that departed 10 minutes ago (Bucharest wall-clock) is detected as
late by get_sessions_pending_late_notify(). Under the pre-fix bare-NOW()
comparison this would silently miss the row for ~2-3h in a UTC session — this
is the exact regression the fix guards against.

Requires a real, reachable Postgres (localhost/defaultdb by default) with the
foi_de_parcurs schema. Skipped when a genuine DB connection isn't available —
notably, jarvis/conftest.py replaces psycopg2 with a MagicMock for the rest of
the suite (so unit tests don't need a live DB), which makes a real UTC-session
timing test impossible to run there; this test detects that (a mocked cursor
returns {} instead of a real row) and skips rather than asserting on it.

To actually exercise this test against a real DB, bypass the ancestor
conftest.py's mock via --confcutdir, e.g.:

    DATABASE_URL=postgresql://localhost/defaultdb \\
      venv/bin/python -m pytest tests/foi_parcurs/test_session_lifecycle_tz.py \\
      --confcutdir=tests/foi_parcurs -v
"""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest


def _real_repo_or_skip():
    """Return a FoiParcursRepository backed by a genuine DB connection, or
    skip the test. A mocked psycopg2 (this suite's normal conftest.py setup)
    makes query_one('SELECT 1 AS one') come back as {} rather than
    {'one': 1} — dict_from_row() on a MagicMock row silently degrades to an
    empty dict instead of raising, so we must check the *value*, not just
    catch exceptions."""
    try:
        from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
        repo = FoiParcursRepository()
        row = repo.query_one('SELECT 1 AS one')
    except Exception as e:
        pytest.skip(f'DB unavailable: {e}')
        return None
    if not row or row.get('one') != 1:
        pytest.skip(
            'DB unavailable for this test (psycopg2 appears mocked in this '
            'pytest session) — run with --confcutdir to bypass the '
            'top-level conftest.py mock and hit a real Postgres'
        )
    return repo


def _force_utc_on_all_pooled_connections():
    """SET SESSION TIME ZONE 'UTC' on every physical connection the pool can
    hand out, so whichever one a later repo call happens to draw already has
    it applied — simulates production's UTC DB session without depending on
    the connection pool's internal reuse order."""
    from database import get_db, get_cursor, release_db, POOL_MAX_CONN
    conns = [get_db() for _ in range(POOL_MAX_CONN)]
    try:
        for conn in conns:
            cur = get_cursor(conn)
            cur.execute("SET SESSION TIME ZONE 'UTC'")
            conn.commit()
    finally:
        for conn in conns:
            release_db(conn)


def test_late_session_detected_under_utc_db_session():
    repo = _real_repo_or_skip()
    _force_utc_on_all_pooled_connections()

    vin = f"TZTEST{uuid.uuid4().hex[:10].upper()}"
    contract_id = f"TD-TZTEST-{uuid.uuid4().hex[:8]}"
    # Naive Bucharest wall-clock, 10 minutes in the past — exactly the kind of
    # value the app writes into departure_datetime.
    dep = (
        datetime.now(ZoneInfo('Europe/Bucharest')).replace(second=0, microsecond=0, tzinfo=None)
        - timedelta(minutes=10)
    ).isoformat()

    row = repo.execute(
        """INSERT INTO foi_de_parcurs (
            contract_id, vin, company_id, route_type, status, advisor_name,
            departure_datetime, km_start, km_end, distance_km,
            fuel_tank_capacity_liters, fuel_gauge_start_level,
            fuel_gauge_end_level, fuel_start_liters, fuel_end_liters,
            fuel_consumed_liters
        ) VALUES (
            %s, %s, 999999, 'TD', 'PLANNED', 'TZ Fix Test',
            %s, 0, 0, 0,
            50, 'F',
            'F', 0, 0,
            0
        ) RETURNING id""",
        (contract_id, vin, dep),
        returning=True,
    )
    new_id = row['id']

    try:
        pending = repo.get_sessions_pending_late_notify()
        ids = [r['id'] for r in pending]
        assert new_id in ids, (
            'Session departed 10 min ago (Bucharest wall-clock) should be '
            'detected as late under a UTC DB session; the bare-NOW() '
            'regression silently misses this for ~2-3h in production'
        )
    finally:
        repo.execute('DELETE FROM foi_de_parcurs WHERE id = %s', (new_id,))
