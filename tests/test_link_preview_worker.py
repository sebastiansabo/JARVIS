"""Unit tests for the background link-preview resolution worker
(_resolve_and_store, _cache_is_fresh, schedule_preview) and its wiring into
chat_service.create_post / update_post.

_resolve_and_store is exercised directly and synchronously (never through
the thread pool): its collaborators — ChatRepository, resolve_preview,
rehost_image, is_social_url — are monkeypatched on the `link_preview`
module, and the network is never touched.
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from datetime import datetime, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from chat.services import link_preview
from chat.services.link_preview import _resolve_and_store, _cache_is_fresh


def _mock_repo(monkeypatch, cached_row=None):
    """Patch link_preview.ChatRepository with a MagicMock class and return
    the single instance it always hands back (`mock_cls.return_value`),
    pre-wired so get_cached_preview() yields `cached_row`."""
    instance = MagicMock()
    instance.get_cached_preview.return_value = cached_row
    mock_cls = MagicMock(return_value=instance)
    monkeypatch.setattr(link_preview, 'ChatRepository', mock_cls)
    return instance


def _forbid(monkeypatch, name):
    """Patch a link_preview collaborator so calling it fails the test."""
    monkeypatch.setattr(
        link_preview, name,
        MagicMock(side_effect=AssertionError(f'{name} should not have been called'))
    )


# --- no URL --------------------------------------------------------------

def test_no_url_clears_preview(monkeypatch):
    repo = _mock_repo(monkeypatch)
    _forbid(monkeypatch, 'resolve_preview')

    _resolve_and_store(5, 'just some text, no link here', '/tmp/uploads')

    repo.set_post_link_preview.assert_called_once_with(5, None)
    repo.get_cached_preview.assert_not_called()
    repo.upsert_cached_preview.assert_not_called()


# --- normal (non-social) URL ---------------------------------------------

def test_normal_url_stores_scraped(monkeypatch):
    repo = _mock_repo(monkeypatch, cached_row=None)
    scraped = {'url': 'https://nytimes.com/a', 'title': 'T', 'description': 'D',
               'image': 'https://cdn/i.jpg', 'site_name': 'nytimes.com', 'source': 'scrape'}
    monkeypatch.setattr(link_preview, 'resolve_preview', MagicMock(return_value=scraped))
    monkeypatch.setattr(link_preview, 'is_social_url', MagicMock(return_value=False))
    _forbid(monkeypatch, 'rehost_image')

    _resolve_and_store(5, 'check this out https://nytimes.com/a', '/tmp/uploads')

    link_preview.resolve_preview.assert_called_once_with('https://nytimes.com/a')
    repo.upsert_cached_preview.assert_called_once_with('https://nytimes.com/a', scraped)
    repo.set_post_link_preview.assert_called_once_with(5, scraped)
    assert scraped['image'] == 'https://cdn/i.jpg'  # untouched — not rehosted


# --- social URL: image gets rehosted before storing -----------------------

def test_social_url_rehosts_then_stores(monkeypatch):
    repo = _mock_repo(monkeypatch, cached_row=None)
    scraped = {'url': 'https://facebook.com/reel/1', 'title': 'T', 'description': None,
               'image': 'https://fbcdn/x', 'site_name': None, 'source': 'microlink'}
    monkeypatch.setattr(link_preview, 'resolve_preview', MagicMock(return_value=scraped))
    monkeypatch.setattr(link_preview, 'is_social_url', MagicMock(return_value=True))
    monkeypatch.setattr(link_preview, 'rehost_image',
                         MagicMock(return_value='/static/uploads/digest/abc.jpg'))

    _resolve_and_store(9, 'https://facebook.com/reel/1', '/srv/static/uploads/digest')

    link_preview.rehost_image.assert_called_once_with('https://fbcdn/x', '/srv/static/uploads/digest')
    assert scraped['image'] == '/static/uploads/digest/abc.jpg'
    repo.upsert_cached_preview.assert_called_once_with('https://facebook.com/reel/1', scraped)
    stored_data = repo.set_post_link_preview.call_args.args[1]
    assert stored_data['image'] == '/static/uploads/digest/abc.jpg'


def test_social_url_rehost_failure_sets_image_none(monkeypatch):
    """rehost_image returning None (download/SSRF/ext failure) must not
    leave the original (soon-to-expire) signed CDN URL in the stored data."""
    repo = _mock_repo(monkeypatch, cached_row=None)
    scraped = {'url': 'https://facebook.com/reel/2', 'title': 'T', 'description': None,
               'image': 'https://fbcdn/y', 'site_name': None, 'source': 'microlink'}
    monkeypatch.setattr(link_preview, 'resolve_preview', MagicMock(return_value=scraped))
    monkeypatch.setattr(link_preview, 'is_social_url', MagicMock(return_value=True))
    monkeypatch.setattr(link_preview, 'rehost_image', MagicMock(return_value=None))

    _resolve_and_store(9, 'https://facebook.com/reel/2', '/srv/static/uploads/digest')

    assert scraped['image'] is None
    repo.set_post_link_preview.assert_called_once_with(9, scraped)


# --- cache hit (fresh) skips resolve_preview -------------------------------

def test_cache_hit_skips_resolve_success_row(monkeypatch):
    fresh_data = {'url': 'https://nytimes.com/a', 'title': 'cached', 'source': 'scrape'}
    row = {'data': fresh_data, 'fetched_at': datetime.now() - timedelta(days=1)}
    repo = _mock_repo(monkeypatch, cached_row=row)
    _forbid(monkeypatch, 'resolve_preview')
    _forbid(monkeypatch, 'rehost_image')

    _resolve_and_store(5, 'see https://nytimes.com/a', '/tmp/uploads')

    repo.get_cached_preview.assert_called_once_with('https://nytimes.com/a')
    repo.upsert_cached_preview.assert_not_called()
    repo.set_post_link_preview.assert_called_once_with(5, fresh_data)


def test_cache_hit_skips_resolve_negative_row(monkeypatch):
    row = {'data': None, 'fetched_at': datetime.now() - timedelta(minutes=10)}
    repo = _mock_repo(monkeypatch, cached_row=row)
    _forbid(monkeypatch, 'resolve_preview')

    _resolve_and_store(5, 'see https://unfurlable.example/a', '/tmp/uploads')

    repo.upsert_cached_preview.assert_not_called()
    repo.set_post_link_preview.assert_called_once_with(5, None)


def test_cache_hit_with_isoformat_string_fetched_at(monkeypatch):
    """Production shape: query_one -> dict_from_row serializes fetched_at
    to an ISO string (see database.dict_from_row), so a real cache hit
    must work with a string timestamp, not just a raw datetime."""
    fresh_data = {'url': 'https://nytimes.com/a', 'title': 'cached', 'source': 'scrape'}
    row = {'data': fresh_data, 'fetched_at': (datetime.now() - timedelta(hours=1)).isoformat()}
    repo = _mock_repo(monkeypatch, cached_row=row)
    _forbid(monkeypatch, 'resolve_preview')

    _resolve_and_store(5, 'see https://nytimes.com/a', '/tmp/uploads')

    repo.upsert_cached_preview.assert_not_called()
    repo.set_post_link_preview.assert_called_once_with(5, fresh_data)


def test_stale_success_row_past_seven_days_refetches(monkeypatch):
    row = {'data': {'title': 'old'}, 'fetched_at': datetime.now() - timedelta(days=8)}
    repo = _mock_repo(monkeypatch, cached_row=row)
    fresh = {'title': 'new', 'image': None}
    monkeypatch.setattr(link_preview, 'resolve_preview', MagicMock(return_value=fresh))
    monkeypatch.setattr(link_preview, 'is_social_url', MagicMock(return_value=False))

    _resolve_and_store(5, 'https://nytimes.com/a', '/tmp/uploads')

    link_preview.resolve_preview.assert_called_once()
    repo.upsert_cached_preview.assert_called_once_with('https://nytimes.com/a', fresh)


def test_stale_negative_row_past_thirty_minutes_refetches(monkeypatch):
    row = {'data': None, 'fetched_at': datetime.now() - timedelta(minutes=31)}
    repo = _mock_repo(monkeypatch, cached_row=row)
    monkeypatch.setattr(link_preview, 'resolve_preview', MagicMock(return_value=None))
    monkeypatch.setattr(link_preview, 'is_social_url', MagicMock(return_value=False))

    _resolve_and_store(5, 'https://unfurlable.example/a', '/tmp/uploads')

    link_preview.resolve_preview.assert_called_once()


# --- failure writes a negative cache entry --------------------------------

def test_failure_writes_negative_cache(monkeypatch):
    repo = _mock_repo(monkeypatch, cached_row=None)
    monkeypatch.setattr(link_preview, 'resolve_preview', MagicMock(return_value=None))
    _forbid(monkeypatch, 'rehost_image')

    _resolve_and_store(5, 'https://broken.example/a', '/tmp/uploads')

    repo.upsert_cached_preview.assert_called_once_with('https://broken.example/a', None)
    repo.set_post_link_preview.assert_called_once_with(5, None)


# --- exceptions never propagate -------------------------------------------

def test_unexpected_exception_is_caught_and_logged(monkeypatch):
    mock_cls = MagicMock(side_effect=RuntimeError('db is down'))
    monkeypatch.setattr(link_preview, 'ChatRepository', mock_cls)

    # Must not raise.
    _resolve_and_store(5, 'https://nytimes.com/a', '/tmp/uploads')


# --- _cache_is_fresh -------------------------------------------------------

class TestCacheIsFresh:
    def test_none_row_is_stale(self):
        assert _cache_is_fresh(None) is False

    def test_missing_fetched_at_is_stale(self):
        assert _cache_is_fresh({'data': {'a': 1}, 'fetched_at': None}) is False

    def test_success_row_exactly_at_boundary_is_fresh(self):
        row = {'data': {'a': 1}, 'fetched_at': datetime.now() - timedelta(days=7, seconds=-5)}
        assert _cache_is_fresh(row) is True

    def test_success_row_past_seven_days_is_stale(self):
        row = {'data': {'a': 1}, 'fetched_at': datetime.now() - timedelta(days=7, seconds=5)}
        assert _cache_is_fresh(row) is False

    def test_negative_row_within_thirty_minutes_is_fresh(self):
        row = {'data': None, 'fetched_at': datetime.now() - timedelta(minutes=29)}
        assert _cache_is_fresh(row) is True

    def test_negative_row_past_thirty_minutes_is_stale(self):
        row = {'data': None, 'fetched_at': datetime.now() - timedelta(minutes=31)}
        assert _cache_is_fresh(row) is False

    def test_isoformat_string_fetched_at_is_handled(self):
        """get_cached_preview is built on BaseRepository.query_one, which
        runs rows through database.dict_from_row — that serializes any
        datetime-like value to an ISO string before the row ever reaches
        this code. fetched_at must be usable as a string, not just a raw
        datetime, or every real cache hit in production would silently
        be judged stale."""
        fresh_row = {'data': {'a': 1},
                     'fetched_at': (datetime.now() - timedelta(days=1)).isoformat()}
        assert _cache_is_fresh(fresh_row) is True

        stale_row = {'data': {'a': 1},
                     'fetched_at': (datetime.now() - timedelta(days=8)).isoformat()}
        assert _cache_is_fresh(stale_row) is False

    def test_unparseable_fetched_at_string_is_stale(self):
        assert _cache_is_fresh({'data': {'a': 1}, 'fetched_at': 'not-a-date'}) is False


# --- schedule_preview submits to the module-level executor ----------------

def test_schedule_preview_submits_to_executor(monkeypatch):
    mock_executor = MagicMock()
    monkeypatch.setattr(link_preview, '_EXECUTOR', mock_executor)

    link_preview.schedule_preview(5, 'https://nytimes.com/a', '/tmp/uploads')

    mock_executor.submit.assert_called_once_with(
        link_preview._resolve_and_store, 5, 'https://nytimes.com/a', '/tmp/uploads'
    )


# --- wiring: create_post / update_post schedule the worker ----------------

class TestChatServiceWiring:
    def _service(self, monkeypatch):
        from chat.services import chat_service as svc_module
        monkeypatch.setattr(svc_module, 'current_app',
                             MagicMock(static_folder='/srv/static'))
        monkeypatch.setattr(svc_module, 'link_preview', MagicMock())
        mock_repo = MagicMock()
        # Short-circuits _notify_post (no channel -> immediate return) so
        # create_post's notification branch never calls the real
        # core.notifications.notify.notify_with_push.
        mock_repo.get_channel.return_value = None
        monkeypatch.setattr(svc_module, '_repo', mock_repo)
        return svc_module

    def test_create_post_schedules_preview_when_url_present(self, monkeypatch):
        svc_module = self._service(monkeypatch)
        svc_module._repo.create_post.return_value = {'id': 42, 'parent_id': None}
        service = svc_module.ChatService()

        service.create_post(1, 7, 'see https://nytimes.com/a', author_name='Ana')

        svc_module.link_preview.schedule_preview.assert_called_once_with(
            42, 'see https://nytimes.com/a',
            os.path.join('/srv/static', 'uploads', 'digest')
        )

    def test_create_post_does_not_schedule_when_no_url(self, monkeypatch):
        svc_module = self._service(monkeypatch)
        svc_module._repo.create_post.return_value = {'id': 43, 'parent_id': None}
        service = svc_module.ChatService()

        service.create_post(1, 7, 'no link in here', author_name='Ana')

        svc_module.link_preview.schedule_preview.assert_not_called()

    def test_update_post_schedules_preview_unconditionally(self, monkeypatch):
        svc_module = self._service(monkeypatch)
        svc_module._repo.get_post.return_value = {'id': 10, 'user_id': 7}
        svc_module._repo.update_post.return_value = {'id': 10, 'content': 'no link anymore'}
        service = svc_module.ChatService()

        service.update_post(10, 'no link anymore', 7)

        svc_module.link_preview.schedule_preview.assert_called_once_with(
            10, 'no link anymore', os.path.join('/srv/static', 'uploads', 'digest')
        )

    def test_update_post_does_not_schedule_when_update_fails(self, monkeypatch):
        svc_module = self._service(monkeypatch)
        svc_module._repo.get_post.return_value = {'id': 10, 'user_id': 7}
        svc_module._repo.update_post.return_value = None
        service = svc_module.ChatService()

        service.update_post(10, 'edited', 7)

        svc_module.link_preview.schedule_preview.assert_not_called()
