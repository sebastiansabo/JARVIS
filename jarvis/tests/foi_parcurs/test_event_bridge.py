"""Tests for the HR-event -> marketing-project bridge helper used by
POST /api/foi-parcurs/test-drive.

`_ensure_event_project(event_id, company_id, user_id)` is idempotent: reuse an
already-bridged marketing 'event' project for the HR event if one exists,
otherwise create one (via ProjectEventRepository.create_event_project) and
link it (via ProjectEventRepository.link), returning the project id either
way. Tested directly against a fake bridge repo monkeypatched onto
`td_mod._event_bridge_repo` (mirrors test_td_company_gate.py's monkeypatch
style) -- no Flask app/route involved here, since the helper is pure.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import foi_parcurs.routes.test_drive as td_mod


class FakeBridge:
    def __init__(self, existing=None, event_info=None, created_id=500):
        self.existing = existing
        self.event_info = event_info
        self.created_id = created_id
        self.created = 0
        self.create_calls = []
        self.linked = []

    def get_project_for_event(self, event_id):
        return self.existing

    def get_event_info(self, event_id):
        return self.event_info

    def create_event_project(self, name, company_id, user_id, event_id):
        self.created += 1
        self.create_calls.append((name, company_id, user_id, event_id))
        return self.created_id

    def link(self, project_id, event_id, linked_by, notes=None):
        self.linked.append((project_id, event_id, linked_by))


def test_reuses_existing_bridged_project(monkeypatch):
    fake = FakeBridge(existing={'id': 42})
    monkeypatch.setattr(td_mod, '_event_bridge_repo', fake)
    assert td_mod._ensure_event_project(7, 11, 1) == 42
    assert fake.created == 0
    assert fake.linked == []


def test_creates_and_links_when_missing(monkeypatch):
    fake = FakeBridge(existing=None,
                       event_info={'name': 'Audi Q6 Launch', 'company': 'AW'},
                       created_id=500)
    monkeypatch.setattr(td_mod, '_event_bridge_repo', fake)
    assert td_mod._ensure_event_project(7, 11, 1) == 500
    assert fake.created == 1
    assert fake.linked == [(500, 7, 1)]


def test_returns_none_when_event_not_found(monkeypatch):
    fake = FakeBridge(existing=None, event_info=None)
    monkeypatch.setattr(td_mod, '_event_bridge_repo', fake)
    assert td_mod._ensure_event_project(7, 11, 1) is None
    assert fake.created == 0
    assert fake.linked == []
