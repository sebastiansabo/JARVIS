"""ConnectorRepository.update_sync_log — partial UPDATE builder.

Used to flip a 'running' carbackground_enhance log to its terminal state and
bump the live done-count. Unit-tested by capturing the SQL/params the method
hands to BaseRepository.execute (no DB needed): the behavior under test IS the
query it builds — which columns it sets, that it parameterizes, and that it
no-ops when given nothing.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import json
from core.connectors.repositories.connector_repository import ConnectorRepository


def _capturing_repo():
    repo = ConnectorRepository()
    cap = {}
    repo.execute = lambda sql, params: cap.update(sql=sql, params=params) or 1
    return repo, cap


def test_update_sync_log_sets_only_provided_fields():
    repo, cap = _capturing_repo()
    repo.update_sync_log(5, status='success', invoices_imported=3)
    assert 'UPDATE connector_sync_log SET' in cap['sql']
    assert 'status=%s' in cap['sql'] and 'invoices_imported=%s' in cap['sql']
    assert 'error_message' not in cap['sql'] and 'details' not in cap['sql']
    assert cap['sql'].rstrip().endswith('WHERE id=%s')
    assert cap['params'] == ('success', 3, 5)  # id parameterized last


def test_update_sync_log_json_encodes_details():
    repo, cap = _capturing_repo()
    repo.update_sync_log(9, details={'done': 2, 'errors': []})
    assert cap['params'] == (json.dumps({'done': 2, 'errors': []}), 9)


def test_update_sync_log_noop_without_fields():
    repo, cap = _capturing_repo()
    assert repo.update_sync_log(9) is None
    assert cap == {}  # execute never called


def test_get_latest_sync_log_scopes_by_connector_type_and_vehicle():
    """Bounded, vehicle-scoped lookup (details->>'vehicle_id') — not a fixed
    window of recent connector-wide rows — so a busy fleet can't hide a job."""
    repo = ConnectorRepository()
    cap = {}
    repo.query_one = lambda sql, params: cap.update(sql=sql, params=params) or {'id': 1}
    repo.get_latest_sync_log(7, 'carbackground_enhance', 9)
    sql = ' '.join(cap['sql'].split())  # normalize whitespace
    assert 'FROM connector_sync_log' in sql
    assert "details->>'vehicle_id' = %s" in sql
    assert 'ORDER BY created_at DESC' in sql and 'LIMIT 1' in sql
    # vehicle_id bound as TEXT to match the ->> extraction
    assert cap['params'] == (7, 'carbackground_enhance', '9')
