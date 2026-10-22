"""P4 Task 3 — accepting a FINAL_OFFER auto-generates the contract (with the
seller signature embedded) and emails the advisor, best-effort: a generation
or email failure must NEVER undo the accept→BOUGHT transition. DB-backed."""
import os
import secrets

import pytest

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.offer_repository import OfferRepository
from buyback.repositories.contract_template_repository import ContractTemplateRepository

pytestmark = pytest.mark.usefixtures('require_real_db')

_SIG = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC'
        'AAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


def _cid():
    return 970000 + secrets.randbelow(900000)


def _bid():
    return 10_000 + secrets.randbelow(900000)


def _vin():
    return ('WBA' + os.urandom(7).hex().upper())[:17]


@pytest.fixture(autouse=True)
def _stub_spaces(monkeypatch):
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct, acl='private': key,
    )


def _final_offer_record(cid, bid, with_template=True):
    """A record sitting in FINAL_OFFER with a pending 'final' offer, ready to accept."""
    rec = RecordRepository().create({
        'record_code': f'BB-ACC-{os.urandom(4).hex()}', 'company_id': cid, 'brand_id': bid,
        'vin': _vin(), 'brand': 'BMW', 'model': '320d', 'created_by': 1,
        'seller_name': 'Ion Popescu',
    })
    RecordRepository().set_status(rec['id'], 'FINAL_OFFER', 1)
    offer = OfferRepository().create(rec['id'], 'final', 12000, 'no_vat', None, None, 1)
    if with_template:
        ContractTemplateRepository().upsert(
            cid, bid, 'purchase', 'Contract', 'Vanzator {seller_name}, pret {price_eur}', 'GC', True, 1)
    return rec, offer


def _has_contract(record_id):
    from buyback.repositories.photo_repository import PhotoRepository
    return any(p.get('photo_type') == 'contract'
               for p in PhotoRepository().get_by_record(record_id))


def test_accept_final_offer_generates_contract(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec, offer = _final_offer_record(cid, bid)

    r = client.post(f"/api/buyback/records/{rec['id']}/offers/{offer['id']}/decision",
                    json={'decision': 'accepted', 'signature': _SIG})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['record']['status'] == 'BOUGHT'
    assert body.get('contract', {}).get('generated') is True
    assert _has_contract(rec['id'])


def test_accept_without_signature_still_generates(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec, offer = _final_offer_record(cid, bid)
    r = client.post(f"/api/buyback/records/{rec['id']}/offers/{offer['id']}/decision",
                    json={'decision': 'accepted'})
    assert r.status_code == 200
    assert r.get_json()['record']['status'] == 'BOUGHT'
    assert _has_contract(rec['id'])


def test_accept_still_bought_when_generation_raises(client, as_role, monkeypatch):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec, offer = _final_offer_record(cid, bid)
    monkeypatch.setattr('buyback.routes.offers.generate_contract',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('render boom')))
    r = client.post(f"/api/buyback/records/{rec['id']}/offers/{offer['id']}/decision",
                    json={'decision': 'accepted', 'signature': _SIG})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['record']['status'] == 'BOUGHT'   # transition preserved


def test_accept_still_bought_when_email_raises(client, as_role, monkeypatch):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec, offer = _final_offer_record(cid, bid)
    monkeypatch.setattr('buyback.routes.offers.send_contract_email',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('smtp boom')))
    r = client.post(f"/api/buyback/records/{rec['id']}/offers/{offer['id']}/decision",
                    json={'decision': 'accepted'})
    assert r.status_code == 200
    assert r.get_json()['record']['status'] == 'BOUGHT'


def test_accept_no_template_still_bought_no_contract(client, as_role):
    as_role('Admin', 1)
    cid, bid = _cid(), _bid()
    rec, offer = _final_offer_record(cid, bid, with_template=False)
    r = client.post(f"/api/buyback/records/{rec['id']}/offers/{offer['id']}/decision",
                    json={'decision': 'accepted'})
    assert r.status_code == 200
    assert r.get_json()['record']['status'] == 'BOUGHT'
    assert r.get_json().get('contract', {}).get('generated') is False
