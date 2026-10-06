"""Unit tests for ChatService.open_direct — validation + delegation.
DB-free: a fake repo is injected by patching the module-global _repo."""
import pytest
import chat.services.chat_service as cs


class _FakeRepo:
    def __init__(self, active_user=None):
        self._active = active_user
        self.created = None

    def get_active_user(self, uid):
        return self._active

    def create_or_get_direct(self, me, other):
        self.created = (me, other)
        return {'id': 11, 'is_direct': True}


def _svc(monkeypatch, repo):
    monkeypatch.setattr(cs, '_repo', repo)
    return cs.ChatService()


def test_open_direct_rejects_self(monkeypatch):
    svc = _svc(monkeypatch, _FakeRepo())
    with pytest.raises(ValueError):
        svc.open_direct(5, 5)


def test_open_direct_rejects_unknown_target(monkeypatch):
    svc = _svc(monkeypatch, _FakeRepo(active_user=None))
    with pytest.raises(LookupError):
        svc.open_direct(5, 99)


def test_open_direct_creates_for_valid_target(monkeypatch):
    repo = _FakeRepo(active_user={'id': 99, 'name': 'Dana'})
    svc = _svc(monkeypatch, repo)
    out = svc.open_direct(5, 99)
    assert out == {'id': 11, 'is_direct': True}
    assert repo.created == (5, 99)
