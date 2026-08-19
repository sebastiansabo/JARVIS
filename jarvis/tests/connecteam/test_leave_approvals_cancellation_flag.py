"""FINDING 2: get_pending_leave_approvals must distinguish cancellation requests
from grant requests so the manager doesn't approve/reject them as if identical.

No live DB: monkeypatches database.get_db/get_cursor/release_db (imported
locally inside the method, so patching the `database` module attributes before
the call is picked up) and _get_current_step_approvers so the query never
actually runs against Postgres.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import database
import core.approvals.handlers._shared as shared
from core.connectors.connecteam.services.connecteam_service import ConnecteamService


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *a, **kw):
        pass

    def fetchall(self):
        return self._rows


def _row(request_id, submission_id, context_snapshot):
    return {
        'request_id': request_id,
        'submission_id': submission_id,
        'answers': {'f_bi_leave_date': '2026-08-01', 'f_bi_hours': 4},
        'requested_at': '2026-08-01T00:00:00',
        'requester_name': 'Alice',
        'context_snapshot': context_snapshot,
    }


def test_cancellation_request_flagged_is_cancellation_true(monkeypatch):
    rows = [_row(1, 10, {'cancellation': True, 'title': 'Anulare bilet de invoire #10'})]
    monkeypatch.setattr(database, 'get_db', lambda: object())
    monkeypatch.setattr(database, 'get_cursor', lambda conn: FakeCursor(rows))
    monkeypatch.setattr(database, 'release_db', lambda conn: None)
    monkeypatch.setattr(shared, '_get_current_step_approvers', lambda rid: [9])

    out = ConnecteamService().get_pending_leave_approvals(user_id=9)

    assert len(out) == 1
    assert out[0]['is_cancellation'] is True


def test_grant_request_flagged_is_cancellation_false(monkeypatch):
    rows = [_row(2, 11, {})]
    monkeypatch.setattr(database, 'get_db', lambda: object())
    monkeypatch.setattr(database, 'get_cursor', lambda conn: FakeCursor(rows))
    monkeypatch.setattr(database, 'release_db', lambda conn: None)
    monkeypatch.setattr(shared, '_get_current_step_approvers', lambda rid: [9])

    out = ConnecteamService().get_pending_leave_approvals(user_id=9)

    assert len(out) == 1
    assert out[0]['is_cancellation'] is False


def test_context_snapshot_as_json_string_is_parsed(monkeypatch):
    # Some drivers may hand back the JSONB column as a raw string; the
    # implementation must json.loads it rather than crash or silently
    # treat it as falsy.
    row = _row(3, 12, '{"cancellation": true}')
    monkeypatch.setattr(database, 'get_db', lambda: object())
    monkeypatch.setattr(database, 'get_cursor', lambda conn: FakeCursor([row]))
    monkeypatch.setattr(database, 'release_db', lambda conn: None)
    monkeypatch.setattr(shared, '_get_current_step_approvers', lambda rid: [9])

    out = ConnecteamService().get_pending_leave_approvals(user_id=9)

    assert out[0]['is_cancellation'] is True


def test_missing_context_snapshot_defaults_to_false(monkeypatch):
    row = _row(4, 13, None)
    monkeypatch.setattr(database, 'get_db', lambda: object())
    monkeypatch.setattr(database, 'get_cursor', lambda conn: FakeCursor([row]))
    monkeypatch.setattr(database, 'release_db', lambda conn: None)
    monkeypatch.setattr(shared, '_get_current_step_approvers', lambda rid: [9])

    out = ConnecteamService().get_pending_leave_approvals(user_id=9)

    assert out[0]['is_cancellation'] is False
