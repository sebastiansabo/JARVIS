"""Tests for ConfigRepository (buyback_company_config upsert/get)."""
from buyback.repositories.config_repository import ConfigRepository


def test_upsert_inserts_then_updates(require_real_db):
    repo = ConfigRepository()
    cid = 987654  # a company_id no other test uses
    repo.execute('DELETE FROM buyback_company_config WHERE company_id = %s', (cid,))
    row = repo.upsert(cid, {'enabled': False, 'acquisition_emails': 'a@b.ro'}, updated_by=1)
    assert row['enabled'] is False and row['acquisition_emails'] == 'a@b.ro'
    row2 = repo.upsert(cid, {'enabled': True}, updated_by=1)
    assert row2['enabled'] is True
    assert row2['acquisition_emails'] == 'a@b.ro'  # untouched field preserved
    assert repo.get(cid)['company_id'] == cid


def test_upsert_drops_unknown_keys(require_real_db):
    repo = ConfigRepository()
    cid = 987655
    repo.execute('DELETE FROM buyback_company_config WHERE company_id = %s', (cid,))
    row = repo.upsert(cid, {'enabled': True, 'evil_col': 'x'}, updated_by=1)
    assert 'evil_col' not in row
