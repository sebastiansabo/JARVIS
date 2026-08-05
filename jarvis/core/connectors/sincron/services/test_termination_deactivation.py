"""Tests for SincronSyncService._deactivate_terminated_employees.

Runs under jarvis/conftest.py (psycopg2 mocked). We build the service with
__new__ to skip __init__/DB wiring and inject a fake repo, so these tests
exercise only the deactivation/close-guard logic.
"""
from core.connectors.sincron.services.sincron_sync_service import SincronSyncService


class FakeRepo:
    def __init__(self, affected_user_ids, active_map):
        self._affected = affected_user_ids
        self._active_map = active_map
        self.deactivated = None
        self.closed_user_ids = []

    def deactivate_employees(self, company_name, ids):
        self.deactivated = (company_name, set(ids))
        return list(self._affected)

    def has_active_contracts(self, user_id):
        return self._active_map.get(user_id, False)

    def execute(self, sql, params):
        # The only execute() call in the method closes a user by id
        self.closed_user_ids.append(params[0])
        return 1


def _service_with(fake):
    svc = SincronSyncService.__new__(SincronSyncService)  # skip __init__ (no DB)
    svc.repo = fake
    return svc


def test_deactivates_records_and_closes_user_without_other_contracts():
    fake = FakeRepo(affected_user_ids=[13], active_map={13: False})
    svc = _service_with(fake)

    n = svc._deactivate_terminated_employees('AUTOWORLD S.R.L.', {'220'})

    assert n == 1
    assert fake.deactivated == ('AUTOWORLD S.R.L.', {'220'})
    assert fake.closed_user_ids == [13]


def test_keeps_user_active_when_contract_exists_in_another_company():
    fake = FakeRepo(affected_user_ids=[13], active_map={13: True})
    svc = _service_with(fake)

    n = svc._deactivate_terminated_employees('AUTOWORLD S.R.L.', {'220'})

    assert n == 1
    assert fake.closed_user_ids == []  # still active elsewhere -> not closed


def test_empty_terminated_ids_is_a_noop():
    fake = FakeRepo(affected_user_ids=[], active_map={})
    svc = _service_with(fake)

    n = svc._deactivate_terminated_employees('AUTOWORLD S.R.L.', set())

    assert n == 0
    assert fake.deactivated is None
    assert fake.closed_user_ids == []
