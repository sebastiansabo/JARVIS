"""Unit tests for ChatRepository DM helpers — create-or-get dedupe + target lookup.
DB-free: query_one/execute are mocked; we assert SQL shape and call sequencing."""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from chat.repositories.chat_repository import ChatRepository
from core.organization import ghost


def _repo():
    repo = ChatRepository()
    repo.execute = MagicMock()
    repo.query_one = MagicMock()
    return repo


class TestCreateOrGetDirect:
    def test_normalises_pair_key_regardless_of_order(self):
        repo = _repo()
        repo.execute.return_value = {'id': 5}
        repo.add_member = MagicMock()
        repo.create_or_get_direct(9, 2)
        insert = repo.execute.call_args_list[0]
        assert 'ON CONFLICT (dm_key) WHERE is_direct DO NOTHING' in insert.args[0]
        assert insert.args[1][0] == '2:9'  # sorted "min:max"

    def test_created_enrols_both_members(self):
        repo = _repo()
        repo.execute.return_value = {'id': 5}
        repo.add_member = MagicMock()
        out = repo.create_or_get_direct(2, 9)
        assert out == {'id': 5}
        repo.query_one.assert_not_called()
        assert repo.add_member.call_args_list[0].args == (5, 2, 'member')
        assert repo.add_member.call_args_list[1].args == (5, 9, 'member')

    def test_existing_pair_is_fetched_not_recreated(self):
        repo = _repo()
        repo.execute.return_value = None  # ON CONFLICT DO NOTHING -> no row
        repo.add_member = MagicMock()
        repo.query_one.return_value = {'id': 7}
        out = repo.create_or_get_direct(9, 2)
        assert out == {'id': 7}
        repo.add_member.assert_not_called()
        assert repo.query_one.call_args.args[1] == ('2:9',)


class TestGetActiveUser:
    def test_filters_active_and_passes_user_id(self, monkeypatch):
        repo = _repo()
        cap = {}
        repo.query_one = lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or None
        monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: set())
        monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
        monkeypatch.setattr(ghost, '_resolve_viewer', lambda: 1)
        ghost.invalidate_ghost_cache()
        repo.get_active_user(42)
        assert 'is_active = TRUE' in cap['sql']
        assert cap['args'][0] == 42


class TestGetChannelsCounterpart:
    def test_query_resolves_counterpart_and_gates_on_is_direct(self):
        repo = ChatRepository()
        cap = {}
        repo.query_all = lambda sql, args=None: cap.update(sql=sql, args=args) or []
        repo.get_channels(user_id=5)
        sql = cap['sql']
        assert 'counterpart_user_id' in sql
        assert 'counterpart_name' in sql
        assert 'ON c.is_direct' in sql           # counterpart LATERAL gated to DMs
        assert 'c.is_direct AND cpu.name ILIKE' in sql  # DM search by counterpart name
