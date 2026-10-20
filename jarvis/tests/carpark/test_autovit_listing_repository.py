"""Mock-based unit tests for AutovitListingRepository.upsert()'s SQL-building
logic — no real DB involved (unlike test_autovit_push.py's Part 1, which
exercises the same repo against localhost/defaultdb).

`upsert()` filters kwargs to the `_UPDATABLE` set before building the
INSERT ... ON CONFLICT DO UPDATE SET statement, so these tests patch
`core.base_repository.get_db/get_cursor/release_db` (where BaseRepository's
module-level `from database import ...` binds them — patching
`database.get_db` directly would NOT be observed here, unlike the late
per-call imports in tasks/carpark.py) with a `_FakeCursor` that records every
`execute(sql, params)` call, then asserts on the generated SQL/params.

Added for Task 1 of the CarPark publishing-panel plan: `last_published_at`
is a new column the Autovit push/verify jobs will write going forward
(freshness tracking) alongside the existing `status`/`external_*`/
`last_error` fields, while `last_sync`/`updated_at` keep bumping
unconditionally on every upsert.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime
from unittest.mock import MagicMock, patch

from carpark.repositories.autovit_listing_repository import AutovitListingRepository


class _FakeCursor:
    """Minimal cursor: every execute() is recorded; fetchone() returns a
    canned row so BaseRepository.execute(returning=True)'s dict_from_row()
    has something to convert."""

    def __init__(self, result=None):
        self._result = result if result is not None else {'id': 1}
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._result


def _run_upsert(**fields):
    cursor = _FakeCursor()
    with patch('core.base_repository.get_db', return_value=MagicMock()), \
         patch('core.base_repository.get_cursor', return_value=cursor), \
         patch('core.base_repository.release_db'):
        AutovitListingRepository().upsert(1, 2, **fields)
    return cursor.executed[0]  # (sql, params)


def test_upsert_persists_last_published_at():
    """last_published_at, when passed, must survive the _UPDATABLE filter
    and appear in both the INSERT column list and the ON CONFLICT DO UPDATE
    SET clause (mirroring every other updatable field) — not be silently
    dropped like an unknown kwarg would be."""
    now = datetime(2026, 10, 20, 12, 0, 0)

    sql, params = _run_upsert(status='active', last_published_at=now)

    insert_cols = sql.split('(', 2)[1].split(')')[0]  # "vehicle_id, account_id, ..."
    assert 'last_published_at' in insert_cols
    assert 'last_published_at=EXCLUDED.last_published_at' in sql
    assert now in params


def test_upsert_drops_last_published_at_when_omitted():
    """A partial upsert that doesn't pass last_published_at must not
    reference the column at all — status-only calls (e.g. unpublish) stay
    unaffected by the new field."""
    sql, params = _run_upsert(status='inactive')

    assert 'last_published_at' not in sql


def test_upsert_always_bumps_last_sync_and_updated_at():
    """last_sync/updated_at are server-managed and must always refresh to
    now(), regardless of which optional fields are passed."""
    sql, _ = _run_upsert(last_published_at=datetime(2026, 10, 20, 12, 0, 0))

    assert 'last_sync=now()' in sql
    assert 'updated_at=now()' in sql
