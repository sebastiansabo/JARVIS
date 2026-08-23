"""Unit tests for ChatRepository.toggle_reaction — one-reaction-per-user
(interchange) semantics: a new emoji replaces the caller's previous reaction,
and tapping the current emoji clears it.
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from chat.repositories.chat_repository import ChatRepository


def _repo(existing_emoji=None):
    """A ChatRepository with its DB accessors stubbed. `existing_emoji` is what
    the caller currently has on the post (None = no reaction yet)."""
    repo = ChatRepository()
    repo.query_one = MagicMock(return_value=({'emoji': existing_emoji} if existing_emoji else None))
    repo.execute = MagicMock()
    return repo


def _sql_calls(repo):
    return [c.args[0].strip().split()[0].upper() for c in repo.execute.call_args_list]


class TestToggleReactionInterchange:
    def test_first_reaction_is_added(self):
        repo = _repo(existing_emoji=None)
        assert repo.toggle_reaction(1, 2, '👍') == 'added'
        # clears (no-op) then inserts the new reaction
        assert _sql_calls(repo) == ['DELETE', 'INSERT']

    def test_tapping_current_emoji_toggles_off(self):
        repo = _repo(existing_emoji='👍')
        assert repo.toggle_reaction(1, 2, '👍') == 'removed'
        # only the clear runs — no re-insert
        assert _sql_calls(repo) == ['DELETE']

    def test_new_emoji_replaces_previous(self):
        repo = _repo(existing_emoji='👀')
        assert repo.toggle_reaction(1, 2, '👍') == 'added'
        # old reaction cleared, new one inserted — never two at once
        assert _sql_calls(repo) == ['DELETE', 'INSERT']

    def test_clear_is_scoped_to_post_and_user(self):
        repo = _repo(existing_emoji='👀')
        repo.toggle_reaction(7, 3, '🎉')
        delete_call = repo.execute.call_args_list[0]
        assert delete_call.args[1] == (7, 3)  # (post_id, user_id)
