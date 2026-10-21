"""Task 6: `POST /records/<id>/generate-contract` — the manual "generate
contract" endpoint tying together build_contract_context (Task 3),
render_contract_pdf (Task 4) and PhotoRepository.store_contract_pdf (Task 5)
behind one route, plus the `ContractTemplateRepository.get_active_with_default`
fallback helper this route needs (no template fallback existed before this
task — `get_active`'s `brand_id = %s` predicate never matches a NULL row).

DB-backed (require_real_db/as_role, localhost/defaultdb). Records are seeded
directly via RecordRepository().create() (mirrors test_contract_document_store
.py's `_record()` helper) so brand_id/seller fields/status can be set freely
without going through the CREATE route's intake whitelist. Templates are
seeded via ContractTemplateRepository().upsert(). Every company_id/brand_id
used here is a fresh random int (mirrors test_contract_template_repository
.py) — buyback_records.company_id and buyback_contract_templates.company_id
carry no FK to the real `companies` table, so this never collides with (or
depends on) real seeded data; CompanyRepository().get() on a nonexistent id
just returns None, which build_contract_context handles as an all-empty
company.

spaces_service.upload is monkeypatched on the photo_repository module (same
spot store_contract_pdf calls it) so no real Spaces network call ever
happens, mirroring test_contract_document_store.py.
"""
import os
import secrets

import pytest

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.contract_template_repository import ContractTemplateRepository

pytestmark = pytest.mark.usefixtures('require_real_db')


def _cid():
    """Fresh random company_id per test — see module docstring."""
    return 970000 + secrets.randbelow(900000)


def _bid():
    """Fresh random brand_id per test."""
    return 10_000 + secrets.randbelow(900000)


def _vin():
    # Not checksum-valid (schema doesn't enforce VIN format), unique per call.
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _code():
    return f'BB-GENCONTRACT-{os.urandom(4).hex()}'


def _record(**overrides):
    data = {
        'record_code': _code(),
        'company_id': 1,
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'created_by': 1,
        'seller_name': 'Ion Popescu',
    }
    data.update(overrides)
    return RecordRepository().create(data)


@pytest.fixture(autouse=True)
def _stub_spaces(monkeypatch):
    """No real Spaces network call for the contract PDF upload inside
    store_contract_pdf — same stub spot as test_contract_document_store.py."""
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct, acl='private': key,
    )


# ═══════════════════════════════════════════════════════════════════════
# ContractTemplateRepository.get_active_with_default (repo helper, TDD'd
# in this task since it's the task that needs it — see brief's Repo note)
# ═══════════════════════════════════════════════════════════════════════

def test_get_active_with_default_falls_back_to_company_default():
    repo = ContractTemplateRepository()
    cid = _cid()
    # No brand-specific row for brand 999 at all; a company-default
    # (brand_id NULL) purchase row exists -> falls back to it.
    repo.upsert(cid, None, 'purchase', 'Default Contract', 'body {seller_name}', 'gc', True, 1)
    row = repo.get_active_with_default(cid, 999, 'purchase')
    assert row is not None and row['brand_id'] is None
    assert row['title'] == 'Default Contract'


def test_get_active_with_default_prefers_brand_specific_over_default():
    repo = ContractTemplateRepository()
    cid = _cid()
    bid = _bid()
    repo.upsert(cid, None, 'purchase', 'Default', 'body', 'gc', True, 1)
    repo.upsert(cid, bid, 'purchase', 'Brand Specific', 'body', 'gc', True, 1)
    row = repo.get_active_with_default(cid, bid, 'purchase')
    assert row['brand_id'] == bid
    assert row['title'] == 'Brand Specific'


def test_get_active_with_default_returns_none_when_neither_exists():
    repo = ContractTemplateRepository()
    cid = _cid()
    assert repo.get_active_with_default(cid, _bid(), 'purchase') is None


def test_get_active_with_default_ignores_inactive_default():
    repo = ContractTemplateRepository()
    cid = _cid()
    repo.upsert(cid, None, 'purchase', 'Inactive Default', 'body', 'gc', False, 1)
    assert repo.get_active_with_default(cid, _bid(), 'purchase') is None


# ═══════════════════════════════════════════════════════════════════════
# POST /api/buyback/records/<id>/generate-contract
# ═══════════════════════════════════════════════════════════════════════

def test_generate_creates_contract_document(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    record = _record(company_id=cid, brand_id=bid)
    ContractTemplateRepository().upsert(
        cid, bid, 'purchase', 'Contract Achizitie',
        'Vanzator {seller_name}, pret {price_eur}', 'GC', True, 1,
    )

    r = client.post(f"/api/buyback/records/{record['id']}/generate-contract", json={})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['photo']['photo_type'] == 'contract'
    assert 'warnings' in body


def test_generate_uses_company_default_template_when_no_brand_match(client, as_role):
    """Exercises the get_active_with_default fallback end-to-end through the
    route: a company-wide default (brand_id NULL) template is used when no
    brand-specific one exists for the record's brand."""
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    record = _record(company_id=cid, brand_id=bid)
    ContractTemplateRepository().upsert(
        cid, None, 'purchase', 'Default Contract', 'body', 'gc', True, 1,
    )

    r = client.post(f"/api/buyback/records/{record['id']}/generate-contract", json={})
    assert r.status_code == 200, r.get_json()


def test_generate_409_when_no_template(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    record = _record(company_id=cid, brand_id=bid)   # no template seeded at all

    r = client.post(f"/api/buyback/records/{record['id']}/generate-contract", json={})
    assert r.status_code == 409
    assert 'error' in r.get_json()


def test_generate_sparse_record_still_succeeds_with_warnings(client, as_role):
    """No accepted offer and no seller_name -> still 200, with warnings
    naming the gaps. Manual generate must never 500 on sparse data."""
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    record = _record(company_id=cid, brand_id=bid, seller_name=None)
    ContractTemplateRepository().upsert(
        cid, bid, 'purchase', 'Contract', 'Vanzator {seller_name}, pret {price_eur}', 'gc', True, 1,
    )

    r = client.post(f"/api/buyback/records/{record['id']}/generate-contract", json={})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert isinstance(body['warnings'], list)
    assert any('ofert' in w.lower() for w in body['warnings'])
    assert any('vânz' in w.lower() or 'vanz' in w.lower() for w in body['warnings'])


def test_generate_missing_record_404(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records/999999999/generate-contract', json={})
    assert r.status_code == 404


def test_generate_rejects_cross_company_record(client, as_role):
    as_role('Sales', 1)
    cid, bid = 1, _bid()
    record = _record(company_id=cid, brand_id=bid)
    ContractTemplateRepository().upsert(
        cid, bid, 'purchase', 'Contract', 'body', 'gc', True, 1,
    )

    as_role('Sales', 2)
    r = client.post(f"/api/buyback/records/{record['id']}/generate-contract", json={})
    assert r.status_code in (403, 404)


def test_generate_infers_consignment_document_type_from_status(client, as_role):
    """No explicit document_type in the body; record status CONSIGNAT ->
    the consignment template is picked (not the purchase one)."""
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    record = _record(company_id=cid, brand_id=bid, status='CONSIGNAT')
    ContractTemplateRepository().upsert(
        cid, bid, 'purchase', 'Purchase Contract', 'body', 'gc', True, 1,
    )
    ContractTemplateRepository().upsert(
        cid, bid, 'consignment', 'Consignment Contract', 'body', 'gc', True, 1,
    )

    r = client.post(f"/api/buyback/records/{record['id']}/generate-contract", json={})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['photo']['caption'] == 'Consignment Contract'


def test_generate_explicit_document_type_overrides_status_inference(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    record = _record(company_id=cid, brand_id=bid)  # default PENDING_EVALUATION status
    ContractTemplateRepository().upsert(
        cid, bid, 'purchase', 'Purchase Contract', 'body', 'gc', True, 1,
    )
    ContractTemplateRepository().upsert(
        cid, bid, 'consignment', 'Consignment Contract', 'body', 'gc', True, 1,
    )

    r = client.post(
        f"/api/buyback/records/{record['id']}/generate-contract",
        json={'document_type': 'consignment'},
    )
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['photo']['caption'] == 'Consignment Contract'
