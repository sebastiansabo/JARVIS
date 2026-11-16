"""Regression: POST /sincron/api/sync/timesheets/now 500 on past-month syncs.

`sync_timesheets` builds per-company result dicts that carry an internal
`_synced_ids` Python *set*. `_terminated_ids` is always popped before return
("so it never leaks into the jsonify'd result"), but `_synced_ids` was popped
ONLY on current-month, after-day-5, success syncs. Any past-month sync (the
normal case for timesheet corrections) left the raw set in the result, so the
route's `jsonify(result)` raised `TypeError: Object of type set is not JSON
serializable` -> generic HTTP 500 on every such run.

This drives the orchestration with mocked collaborators (no DB/HTTP) and asserts
the returned structure is JSON-serializable for a PAST month.
"""
import json
from unittest.mock import MagicMock

from core.connectors.sincron.services.sincron_sync_service import SincronSyncService


def _service_with_mocks():
    """A service whose heavy collaborators are stubbed; _sync_company_timesheets
    returns a result still carrying the internal `_synced_ids`/`_terminated_ids`
    sets, exactly as the real per-company sync does."""
    svc = SincronSyncService.__new__(SincronSyncService)  # skip __init__ (real repos)
    svc.sync_repo = MagicMock()
    svc.sync_repo.create_run.return_value = {'run_id': 1}
    svc.connector_repo = MagicMock()
    svc.connector_repo.get_by_type.return_value = None  # skip last_sync update branch
    svc.repo = MagicMock()
    svc.repo.recalculate_base_contracts.return_value = 0
    svc.user_repo = MagicMock()
    svc._get_company_tokens = MagicMock(return_value={'CompA': 'tok'})
    svc._get_company_id_map = MagicMock(return_value={})
    svc._sync_company_timesheets = MagicMock(return_value={
        'success': True, 'employees': 1, 'records': 2,
        '_synced_ids': {10, 11}, '_terminated_ids': {20},
    })
    svc._deactivate_missing_employees = MagicMock(return_value=0)
    svc._deactivate_terminated_employees = MagicMock(return_value=0)
    svc._reactivate_returned_employees = MagicMock(return_value=0)
    svc._sync_biostar_schedules = MagicMock(return_value=0)
    return svc


def test_past_month_sync_result_is_json_serializable():
    svc = _service_with_mocks()
    # A past month => is_current_month False => the _synced_ids pop branch is skipped.
    result = svc.sync_timesheets(year=2020, month=1)
    # The route does jsonify(result); a leaked set makes that raise TypeError/500.
    json.dumps(result)
    assert '_synced_ids' not in result['companies']['CompA']
    assert '_terminated_ids' not in result['companies']['CompA']
