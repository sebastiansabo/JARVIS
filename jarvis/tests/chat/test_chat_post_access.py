"""Unit tests for ChatService post/poll access guards.

A non-member of a PRIVATE channel (including a DM) must not read/react/vote on
its posts via the post-id / poll-id scoped routes. DB-free: a fake repo is
injected by patching the module-global _repo; the guards delegate to the
existing can_access_channel (public → anyone, private → members only)."""
import chat.services.chat_service as cs


class _FakeRepo:
    """Minimal repo: one post, one poll→channel mapping, and the channel's
    privacy + membership used by can_access_channel."""
    def __init__(self, post=None, poll_channel=None, private=True, members=()):
        self._post = post
        self._poll_channel = poll_channel
        self._private = private
        self._members = set(members)

    def get_post(self, post_id):
        return self._post

    def channel_id_for_poll(self, poll_id):
        return self._poll_channel

    # used by ChatService.can_access_channel
    def get_channel(self, channel_id):
        return {'id': channel_id, 'is_private': self._private}

    def is_member(self, channel_id, user_id):
        return user_id in self._members


def _svc(monkeypatch, repo):
    monkeypatch.setattr(cs, '_repo', repo)
    return cs.ChatService()


class TestCanAccessPost:
    def test_false_when_post_missing(self, monkeypatch):
        svc = _svc(monkeypatch, _FakeRepo(post=None))
        assert svc.can_access_post(123, 5) is False

    def test_private_requires_membership(self, monkeypatch):
        repo = _FakeRepo(post={'id': 1, 'channel_id': 9}, private=True, members={5})
        svc = _svc(monkeypatch, repo)
        assert svc.can_access_post(1, 5) is True    # member
        assert svc.can_access_post(1, 6) is False   # non-member blocked

    def test_public_open_to_all(self, monkeypatch):
        repo = _FakeRepo(post={'id': 1, 'channel_id': 9}, private=False)
        svc = _svc(monkeypatch, repo)
        assert svc.can_access_post(1, 999) is True


class TestCanAccessPoll:
    def test_false_when_poll_missing(self, monkeypatch):
        svc = _svc(monkeypatch, _FakeRepo(poll_channel=None))
        assert svc.can_access_poll(77, 5) is False

    def test_private_requires_membership(self, monkeypatch):
        repo = _FakeRepo(poll_channel=9, private=True, members={5})
        svc = _svc(monkeypatch, repo)
        assert svc.can_access_poll(77, 5) is True
        assert svc.can_access_poll(77, 6) is False
