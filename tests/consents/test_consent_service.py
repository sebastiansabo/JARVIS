import pytest
from core.consents.services.consent_service import ConsentService

class FakeRepo:
    def __init__(self):
        self.docs = [
            {'id': 1, 'doc_key': 'data_usage', 'title': 'A', 'body': 'x',
             'version': 1, 'requires_signature': True, 'is_active': True, 'is_mandatory': True},
            {'id': 2, 'doc_key': 'gdpr', 'title': 'B', 'body': 'y',
             'version': 1, 'requires_signature': True, 'is_active': True, 'is_mandatory': True},
        ]
        self.signed = set()
        self.inserted = []
    def list_active_mandatory(self): return [d for d in self.docs if d['is_active'] and d['is_mandatory']]
    def get_by_id(self, i): return next((d for d in self.docs if d['id'] == i), None)
    def get_user_signed_ids(self, u): return list(self.signed)
    def count_active_mandatory(self): return len(self.list_active_mandatory())
    def count_user_accepted_mandatory(self, u): return len(self.signed)
    def insert_signature(self, u, d, v, img, h, ip, ua): self.inserted.append((u, d, h)); self.signed.add(d)

PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=='

def test_pending_lists_unsigned_in_order():
    svc = ConsentService(FakeRepo())
    res = svc.get_pending_for_user(7)
    assert res['complete'] is False
    assert [d['id'] for d in res['pending']] == [1, 2]

def test_sign_advances_and_completes():
    repo = FakeRepo(); svc = ConsentService(repo)
    r1 = svc.sign(7, 1, PNG, '1.2.3.4', 'UA')
    assert r1['complete'] is False and r1['pending_count'] == 1
    r2 = svc.sign(7, 2, PNG, '1.2.3.4', 'UA')
    assert r2['complete'] is True and r2['pending_count'] == 0
    assert len(repo.inserted) == 2

def test_sign_rejects_missing_signature():
    svc = ConsentService(FakeRepo())
    with pytest.raises(ValueError):
        svc.sign(7, 1, '', '1.2.3.4', 'UA')

def test_sign_rejects_invalid_document():
    svc = ConsentService(FakeRepo())
    with pytest.raises(ValueError):
        svc.sign(7, 999, PNG, '1.2.3.4', 'UA')

def test_hash_is_stable():
    assert ConsentService.compute_hash('abc') == ConsentService.compute_hash('abc')
    assert ConsentService.compute_hash('abc') != ConsentService.compute_hash('abd')
