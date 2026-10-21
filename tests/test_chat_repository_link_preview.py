"""Unit tests for ChatRepository link-preview methods — the cache table
(digest_link_previews) and the per-post snapshot column
(digest_posts.link_preview).

Note on Json assertions: tests/conftest.py globally replaces the
`psycopg2.extras` module with a MagicMock (so the suite never needs a real
psycopg2 driver). Under that stub, calling the mocked `Json(x)` always
returns the SAME fixed child mock regardless of `x` — so we can't recover
the wrapped value by inspecting the mock's return value. Instead we patch
the `Json` name as imported into chat_repository and assert it was *called*
with the expected value (with a passthrough side_effect so the param tuple
still carries something we can compare).
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from chat.repositories import chat_repository as repo_module
from chat.repositories.chat_repository import ChatRepository


def _repo():
    repo = ChatRepository()
    repo.query_one = MagicMock(return_value=None)
    repo.execute = MagicMock()
    return repo


class TestGetCachedPreview:
    def test_get_cached_preview_queries_by_url(self):
        repo = _repo()
        repo.query_one = MagicMock(return_value={'data': {'title': 'T'}})
        repo.get_cached_preview('https://a.com')
        sql = repo.query_one.call_args.args[0]
        assert sql.strip().upper().startswith('SELECT')
        assert 'digest_link_previews' in sql
        assert 'WHERE url = %s' in sql
        assert repo.query_one.call_args.args[1] == ('https://a.com',)

    def test_get_cached_preview_returns_row(self):
        repo = _repo()
        repo.query_one = MagicMock(return_value={'data': {'title': 'T'}, 'fetched_at': 'now'})
        result = repo.get_cached_preview('https://a.com')
        assert result == {'data': {'title': 'T'}, 'fetched_at': 'now'}

    def test_get_cached_preview_returns_none_when_absent(self):
        repo = _repo()
        repo.query_one = MagicMock(return_value=None)
        result = repo.get_cached_preview('https://nope.com')
        assert result is None


class TestUpsertCachedPreview:
    def test_upsert_uses_on_conflict_and_json(self):
        repo = _repo()
        repo.execute = MagicMock()
        repo.upsert_cached_preview('https://a.com', {'title': 'T'})
        sql = repo.execute.call_args.args[0]
        assert 'INSERT INTO digest_link_previews' in sql
        assert 'ON CONFLICT (url)' in sql
        assert 'DO UPDATE SET' in sql

    def test_upsert_params_are_url_then_json_wrapped_data(self):
        repo = _repo()
        repo.execute = MagicMock()
        data = {'title': 'T'}
        with patch.object(repo_module, 'Json', side_effect=lambda v: v) as mock_json:
            repo.upsert_cached_preview('https://a.com', data)
        mock_json.assert_called_once_with(data)
        params = repo.execute.call_args.args[1]
        assert params == ('https://a.com', data)

    def test_upsert_negative_cache_wraps_none_in_json(self):
        repo = _repo()
        repo.execute = MagicMock()
        with patch.object(repo_module, 'Json', side_effect=lambda v: v) as mock_json:
            repo.upsert_cached_preview('https://nope.com', None)
        mock_json.assert_called_once_with(None)
        params = repo.execute.call_args.args[1]
        assert params == ('https://nope.com', None)


class TestSetPostLinkPreview:
    def test_set_post_link_preview_updates_column(self):
        repo = _repo()
        repo.execute = MagicMock()
        repo.set_post_link_preview(5, {'title': 'T'})
        sql, params = repo.execute.call_args.args[0], repo.execute.call_args.args[1]
        assert 'UPDATE digest_posts SET link_preview' in sql
        assert 'WHERE id = %s' in sql
        assert params[1] == 5

    def test_set_post_link_preview_wraps_data_in_json(self):
        repo = _repo()
        repo.execute = MagicMock()
        data = {'title': 'T'}
        with patch.object(repo_module, 'Json', side_effect=lambda v: v) as mock_json:
            repo.set_post_link_preview(5, data)
        mock_json.assert_called_once_with(data)
        params = repo.execute.call_args.args[1]
        assert params == (data, 5)

    def test_set_post_link_preview_wraps_none_in_json(self):
        repo = _repo()
        repo.execute = MagicMock()
        with patch.object(repo_module, 'Json', side_effect=lambda v: v) as mock_json:
            repo.set_post_link_preview(7, None)
        mock_json.assert_called_once_with(None)
        params = repo.execute.call_args.args[1]
        assert params == (None, 7)
