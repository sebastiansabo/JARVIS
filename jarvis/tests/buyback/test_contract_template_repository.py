"""Tests for ContractTemplateRepository (per company×brand×type contract
templates). DB-backed (localhost/defaultdb via require_real_db)."""
import os

from buyback.repositories.contract_template_repository import ContractTemplateRepository


def test_upsert_is_unique_per_company_brand_type(require_real_db):
    repo = ContractTemplateRepository()
    cid = 963000 + int.from_bytes(os.urandom(2), 'big')
    repo.upsert(cid, 1, 'purchase', 'T1', 'body A', 'gc', True, 1)
    repo.upsert(cid, 1, 'purchase', 'T2', 'body B', 'gc2', True, 1)   # same key → update
    rows = [r for r in repo.list_for_company(cid) if r['brand_id'] == 1]
    assert len(rows) == 1
    assert rows[0]['title'] == 'T2' and rows[0]['body_template'] == 'body B'


def test_get_active_returns_only_active(require_real_db):
    repo = ContractTemplateRepository()
    cid = 964000 + int.from_bytes(os.urandom(2), 'big')
    repo.upsert(cid, 2, 'consignment', 'C', 'b', '', False, 1)
    assert repo.get_active(cid, 2, 'consignment') is None
    repo.upsert(cid, 2, 'consignment', 'C', 'b', '', True, 1)
    assert repo.get_active(cid, 2, 'consignment')['title'] == 'C'
