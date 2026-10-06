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


class _NotifyRepo:
    def __init__(self, channel, members):
        self._channel = channel
        self._members = members

    def get_channel(self, cid):
        return self._channel

    def get_channel_members(self, cid):
        return self._members

    def get_post(self, pid):
        return None


def _capture_push(monkeypatch):
    calls = []
    monkeypatch.setattr('core.notifications.notify.notify_with_push',
                        lambda *a, **k: calls.append(a))
    return calls


def test_notify_dm_uses_sender_name_as_title(monkeypatch):
    repo = _NotifyRepo(
        channel={'id': 11, 'is_direct': True, 'name': '', 'type': 'general', 'notify_mode': 'all'},
        members=[{'user_id': 5}, {'user_id': 9}])
    svc = _svc(monkeypatch, repo)
    calls = _capture_push(monkeypatch)
    svc._notify_post({'id': 100, 'parent_id': None}, 11, 5, 'hi', 'post', 'Alex', None)
    assert len(calls) == 1
    targets, title = calls[0][0], calls[0][1]
    assert targets == [9]
    assert title == 'Alex'


def test_notify_group_keeps_hash_title(monkeypatch):
    repo = _NotifyRepo(
        channel={'id': 3, 'is_direct': False, 'name': 'Suport', 'type': 'general', 'notify_mode': 'all'},
        members=[{'user_id': 5}, {'user_id': 9}])
    svc = _svc(monkeypatch, repo)
    calls = _capture_push(monkeypatch)
    svc._notify_post({'id': 101, 'parent_id': None}, 3, 5, 'hi', 'post', 'Alex', None)
    assert calls[0][1] == '#Suport'


class _ChannelRepo:
    def __init__(self, channel):
        self._channel = channel

    def get_channel(self, cid):
        return self._channel


def test_is_direct_true_for_dm(monkeypatch):
    svc = _svc(monkeypatch, _ChannelRepo({'id': 11, 'is_direct': True}))
    assert svc.is_direct(11) is True


def test_is_direct_false_for_group(monkeypatch):
    svc = _svc(monkeypatch, _ChannelRepo({'id': 3, 'is_direct': False}))
    assert svc.is_direct(3) is False


def test_is_direct_false_when_missing(monkeypatch):
    svc = _svc(monkeypatch, _ChannelRepo(None))
    assert svc.is_direct(999) is False
