"""Repo-level tests for the reschedule stamp that drives the "Replanificat" tag.

reschedule_session must (1) revive the row to PLANNED and (2) stamp
rescheduled_at = NOW() so the badge can render; and the lean list column set
(_LIST_COLUMNS, used by the Hub Driving Sessions list) must carry the column —
otherwise the badge never reaches the list payload (the list runs lean=True).
Only the DB boundary (execute) is mocked; the method logic is the real thing.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from foi_parcurs.repositories.foi_parcurs_repository import (
    FoiParcursRepository, _LIST_COLUMNS,
)


def test_lean_list_columns_include_rescheduled_at():
    assert 'rescheduled_at' in _LIST_COLUMNS


def test_reschedule_session_stamps_rescheduled_at_and_revives_to_planned():
    repo = FoiParcursRepository()
    captured = {}

    def fake_execute(sql, params, returning=False):
        captured['sql'] = sql
        captured['params'] = params
        return {'id': 5}

    repo.execute = fake_execute
    repo.get_contract_by_id = lambda cid: {'id': cid, 'status': 'PLANNED'}

    out = repo.reschedule_session(5, '2999-01-01T10:00', '2999-01-01T11:00')

    assert 'rescheduled_at = NOW()' in captured['sql']
    assert "status = 'PLANNED'" in captured['sql']
    assert out['status'] == 'PLANNED'
