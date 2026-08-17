import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
from unittest.mock import patch, MagicMock
import tasks.archive_comenzi as job


def _repo_with(active_anexas, active_contracts):
    repo = MagicMock()
    repo.list_active_anexas.return_value = active_anexas
    repo.list_active_contracts.return_value = active_contracts
    repo.archive_due_anexas.return_value = 0
    repo.archive_due_contracts.return_value = 0
    # arm/clear return rowcount ints so `armed`/`cancelled` accumulate cleanly
    repo.set_anexa_archive_after.return_value = 1
    repo.clear_anexa_archive_after.return_value = 1
    repo.set_contract_archive_after.return_value = 1
    repo.clear_contract_archive_after.return_value = 1
    return repo


def test_disabled_does_nothing():
    repo = _repo_with([{'id': 1, 'archive_after': None}], [])
    with patch.object(job, '_archive_settings', return_value=(False, 24)), \
         patch.object(job, 'InvoiceStorageRepository', return_value=repo):
        job.archive_pending_comenzi()
    repo.set_anexa_archive_after.assert_not_called()
    repo.archive_due_anexas.assert_not_called()


def test_arms_newly_complete_anexa():
    repo = _repo_with([{'id': 7, 'archive_after': None}], [])
    with patch.object(job, '_archive_settings', return_value=(True, 24)), \
         patch.object(job, 'InvoiceStorageRepository', return_value=repo), \
         patch.object(job, 'is_anexa_complete', return_value=True), \
         patch.object(job, 'is_contract_complete', return_value=False):
        job.archive_pending_comenzi()
    repo.set_anexa_archive_after.assert_called_once_with(7, 24)


def test_cancels_reopened_anexa():
    repo = _repo_with([{'id': 7, 'archive_after': 'sometime'}], [])
    with patch.object(job, '_archive_settings', return_value=(True, 24)), \
         patch.object(job, 'InvoiceStorageRepository', return_value=repo), \
         patch.object(job, 'is_anexa_complete', return_value=False), \
         patch.object(job, 'is_contract_complete', return_value=False):
        job.archive_pending_comenzi()
    repo.clear_anexa_archive_after.assert_called_once_with(7)
    repo.set_anexa_archive_after.assert_not_called()


def test_arms_contract_when_all_anexas_complete():
    repo = _repo_with([], [{'id': 3, 'archive_after': None}])
    with patch.object(job, '_archive_settings', return_value=(True, 12)), \
         patch.object(job, 'InvoiceStorageRepository', return_value=repo), \
         patch.object(job, 'is_contract_complete', return_value=True):
        job.archive_pending_comenzi()
    repo.set_contract_archive_after.assert_called_once_with(3, 12)


def test_one_bad_anexa_does_not_abort_sweep():
    repo = _repo_with([{'id': 1, 'archive_after': None}, {'id': 2, 'archive_after': None}], [])
    def flaky(r, aid):
        if aid == 1:
            raise RuntimeError("boom")
        return True
    with patch.object(job, '_archive_settings', return_value=(True, 24)), \
         patch.object(job, 'InvoiceStorageRepository', return_value=repo), \
         patch.object(job, 'is_anexa_complete', side_effect=flaky), \
         patch.object(job, 'is_contract_complete', return_value=False):
        job.archive_pending_comenzi()
    repo.set_anexa_archive_after.assert_called_once_with(2, 24)  # id=2 still armed
