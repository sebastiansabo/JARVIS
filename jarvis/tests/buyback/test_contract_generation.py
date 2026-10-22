"""P4 Task 1 — the extracted generate_contract() service core (shared by the
manual route and the accept-time auto-generate), signature-aware. DB-backed."""
import os
import io
import secrets

import pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from buyback.repositories.record_repository import RecordRepository  # noqa: E402
from buyback.repositories.contract_template_repository import ContractTemplateRepository  # noqa: E402
from buyback.services.contract_generation import generate_contract, NoTemplateError  # noqa: E402
from PyPDF2 import PdfReader  # noqa: E402

pytestmark = pytest.mark.usefixtures('require_real_db')

# 1x1 transparent PNG data-URL.
_SIG = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC'
        'AAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


def _cid():
    return 970000 + secrets.randbelow(900000)


def _bid():
    return 10_000 + secrets.randbelow(900000)


def _vin():
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _record(**ov):
    data = {
        'record_code': f'BB-GEN-{os.urandom(4).hex()}', 'company_id': 1, 'vin': _vin(),
        'brand': 'BMW', 'model': '320d', 'created_by': 1, 'seller_name': 'Ion Popescu',
    }
    data.update(ov)
    return RecordRepository().create(data)


@pytest.fixture(autouse=True)
def _stub_spaces(monkeypatch):
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct, acl='private': key,
    )


def _seed(cid, bid, body='Vanzator {seller_name}'):
    ContractTemplateRepository().upsert(cid, bid, 'purchase', 'Contract', body, 'GC', True, 1)


def test_from_data_creates_contract_photo_and_substitutes():
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed(cid, bid)
    res = generate_contract(rec, from_data=True)
    assert res['photo']['photo_type'] == 'contract'
    assert 'Ion Popescu' in res['parts']['body']
    assert res['pdf_bytes'][:5] == b'%PDF-'


def test_stored_body_rendered_not_resubstituted():
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed(cid, bid)
    generate_contract(rec, from_data=True)                   # stamps contract_body
    rec2 = RecordRepository().get_by_id(rec['id'])
    res = generate_contract(rec2)                            # no from_data -> use stored body
    assert 'Ion Popescu' in res['parts']['body']             # the stored (already-substituted) text


def test_signature_is_embedded():
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)
    _seed(cid, bid)
    no_sig = generate_contract(rec, from_data=True)['pdf_bytes']
    rec2 = RecordRepository().get_by_id(rec['id'])
    with_sig = generate_contract(rec2, signature=_SIG)['pdf_bytes']
    assert len(with_sig) > len(no_sig)                       # embedded signature image adds bytes


def test_no_template_raises_NoTemplateError():
    cid, bid = _cid(), _bid()
    rec = _record(company_id=cid, brand_id=bid)              # no template seeded
    with pytest.raises(NoTemplateError):
        generate_contract(rec, from_data=True)
