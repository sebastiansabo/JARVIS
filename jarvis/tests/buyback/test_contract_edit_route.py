"""P3c Task 3 — GET /records/<id>/contract (editable draft) + unified
POST /records/<id>/contract (generate-from-data | save manual edit |
regenerate-from-data). DB-backed (require_real_db/as_role, localhost/
defaultdb); spaces upload stubbed so no network. Seeding mirrors
test_generate_contract_route.py (fresh random company/brand ids, no FK)."""
import os
import secrets

import pytest

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.contract_template_repository import ContractTemplateRepository

pytestmark = pytest.mark.usefixtures('require_real_db')


def _cid():
    return 970000 + secrets.randbelow(900000)


def _bid():
    return 10_000 + secrets.randbelow(900000)


def _vin():
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _record(**overrides):
    data = {
        'record_code': f'BB-EDIT-{os.urandom(4).hex()}', 'company_id': 1,
        'vin': _vin(), 'brand': 'BMW', 'model': '320d', 'created_by': 1,
        'seller_name': 'Ion Popescu',
    }
    data.update(overrides)
    return RecordRepository().create(data)


@pytest.fixture(autouse=True)
def _stub_spaces(monkeypatch):
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct, acl='private': key,
    )


def _seed_template(cid, bid, body='Vanzator {seller_name}, pret {price_eur}'):
    ContractTemplateRepository().upsert(cid, bid, 'purchase', 'Contract Achizitie', body, 'GC', True, 1)


def test_post_generate_from_data_creates_body_and_photo(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed_template(cid, bid)

    r = client.post(f"/api/buyback/records/{rec['id']}/contract", json={'from_data': True})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['photo']['photo_type'] == 'contract'
    assert body['draft']['has_contract'] is True
    assert 'Ion Popescu' in body['draft']['body']       # token substituted from data


def test_get_draft_preview_when_no_stored_contract(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed_template(cid, bid)

    r = client.get(f"/api/buyback/records/{rec['id']}/contract")
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d['has_template'] is True
    assert d['has_contract'] is False
    assert 'Ion Popescu' in d['body']                   # fresh substitution preview
    assert d['download_url'] is None


def test_post_edit_stores_exact_body_no_resubstitution(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed_template(cid, bid)
    client.post(f"/api/buyback/records/{rec['id']}/contract", json={'from_data': True})

    edited = 'TEXT EDITAT MANUAL {not_a_real_token}'
    r = client.post(f"/api/buyback/records/{rec['id']}/contract", json={'body': edited})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['draft']['body'] == edited       # stored verbatim, not substituted

    d = client.get(f"/api/buyback/records/{rec['id']}/contract").get_json()
    assert d['body'] == edited and d['has_contract'] is True


def test_regenerate_from_data_overwrites_manual_edit(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed_template(cid, bid)
    client.post(f"/api/buyback/records/{rec['id']}/contract", json={'from_data': True})
    client.post(f"/api/buyback/records/{rec['id']}/contract", json={'body': 'TEXT EDITAT'})

    r = client.post(f"/api/buyback/records/{rec['id']}/contract", json={'from_data': True})
    assert r.status_code == 200
    body = r.get_json()['draft']['body']
    assert 'TEXT EDITAT' not in body and 'Ion Popescu' in body   # rebuilt from template


def test_post_no_template_no_body_returns_409(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)          # no template seeded

    r = client.post(f"/api/buyback/records/{rec['id']}/contract", json={'from_data': True})
    assert r.status_code == 409
    assert 'error' in r.get_json()


def test_generate_contract_alias_still_works(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed_template(cid, bid)

    r = client.post(f"/api/buyback/records/{rec['id']}/generate-contract", json={})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['photo']['photo_type'] == 'contract'


def test_long_title_is_clamped_not_500(client, as_role):
    # contract_title is VARCHAR(300); an over-long title must be clamped, not 500.
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed_template(cid, bid)
    r = client.post(f"/api/buyback/records/{rec['id']}/contract",
                    json={'title': 'X' * 500, 'body': 'corp'})
    assert r.status_code == 200, r.get_json()
    assert len(r.get_json()['draft']['title']) <= 300


def test_post_rejects_cross_company(client, as_role):
    as_role('Sales', 1)
    cid, bid = 1, _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed_template(cid, bid)

    as_role('Sales', 2)
    r = client.post(f"/api/buyback/records/{rec['id']}/contract", json={'from_data': True})
    assert r.status_code in (403, 404)
