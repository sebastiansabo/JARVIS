"""Unit tests for the Tagging system.

Tests:
- TagRepository: groups, tags, entity tags CRUD
- AutoTagRepository: rules CRUD
- AutoTagService: rule evaluation
"""

import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

_B = 'core.base_repository'


def _mock_db():
    conn = MagicMock()
    cursor = MagicMock()
    return conn, cursor


# ═══════════════════════════════════════════════
# TagRepository — Tag Groups
# ═══════════════════════════════════════════════

class TestTagGroups:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_groups_active_only(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Status', 'color': '#28a745', 'sort_order': 0, 'is_active': True},
            {'id': 2, 'name': 'Priority', 'color': '#ffc107', 'sort_order': 1, 'is_active': True},
        ]

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        groups = repo.get_groups(active_only=True)
        assert len(groups) == 2
        assert groups[0]['name'] == 'Status'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_save_group(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 3}

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        result = repo.save_group(name='  Category  ', color='#ff0000')
        assert result == 3

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_group(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.update_group(1, name='Updated Status', color='#000') is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_group_no_valid_fields(self, mock_get_db, mock_get_cursor, mock_release):
        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.update_group(1, bogus='val') is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_group_soft(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.delete_group(1) is True


# ═══════════════════════════════════════════════
# TagRepository — Tags
# ═══════════════════════════════════════════════

class TestTags:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_tags_for_user(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Urgent', 'color': '#dc3545', 'is_global': True,
             'group_id': 2, 'group_name': 'Priority', 'group_color': '#ffc107'}
        ]

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        tags = repo.get_tags(user_id=5)
        assert len(tags) == 1
        assert tags[0]['group_name'] == 'Priority'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_tags_filtered_by_group(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        tags = repo.get_tags(user_id=5, group_id=99)
        assert tags == []

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_tag_by_id(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 1, 'name': 'Urgent', 'group_name': 'Priority'}

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        tag = repo.get_tag(1)
        assert tag['name'] == 'Urgent'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_tag_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.get_tag(999) is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_save_tag(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 10}

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        result = repo.save_tag(name='New Tag', is_global=True, created_by=1, group_id=2)
        assert result == 10

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_tag(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.update_tag(10, name='Renamed', color='#000') is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_tag_soft(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.delete_tag(10) is True


# ═══════════════════════════════════════════════
# TagRepository — Entity Tags
# ═══════════════════════════════════════════════

class TestEntityTags:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_entity_tags(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Urgent', 'color': '#dc3545', 'tagged_by': 5}
        ]

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        tags = repo.get_entity_tags('invoice', 42, user_id=5)
        assert len(tags) == 1

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_add_entity_tag(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 100}  # RETURNING id

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.add_entity_tag(tag_id=1, entity_type='invoice', entity_id=42, tagged_by=5) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_add_entity_tag_duplicate(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None  # ON CONFLICT DO NOTHING

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.add_entity_tag(tag_id=1, entity_type='invoice', entity_id=42, tagged_by=5) is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_remove_entity_tag(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.remove_entity_tag(tag_id=1, entity_type='invoice', entity_id=42) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_remove_entity_tag_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.remove_entity_tag(tag_id=999, entity_type='invoice', entity_id=42) is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_bulk_get_entities_tags_empty(self, mock_get_db, mock_get_cursor, mock_release):
        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        result = repo.get_entities_tags_bulk('invoice', [], user_id=5)
        assert result == {}

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_bulk_remove_entity_tags_empty(self, mock_get_db, mock_get_cursor, mock_release):
        from core.tags.repositories.tag_repository import TagRepository
        repo = TagRepository()
        assert repo.bulk_remove_entity_tags(tag_id=1, entity_type='invoice', entity_ids=[]) == 0


# ═══════════════════════════════════════════════
# AutoTagRepository Tests
# ═══════════════════════════════════════════════

class TestAutoTagRepository:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_rules_all(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Tag high invoices', 'entity_type': 'invoice',
             'tag_name': 'High Value', 'tag_color': '#dc3545'}
        ]

        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        rules = repo.get_rules()
        assert len(rules) == 1

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_rules_by_entity_type(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        rules = repo.get_rules(entity_type='invoice')
        assert rules == []

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create_rule(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 5}

        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        result = repo.create_rule(
            name='  High Value Invoices  ',
            entity_type='invoice',
            tag_id=1,
            conditions=[{'field': 'invoice_value', 'operator': 'gte', 'value': 10000}],
            created_by=1
        )
        assert result == 5

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_rule(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        assert repo.update_rule(5, name='Updated Rule', is_active=False) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_rule_no_valid_fields(self, mock_get_db, mock_get_cursor, mock_release):
        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        assert repo.update_rule(5, invalid='val') is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_rule(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        assert repo.delete_rule(5) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_rule_by_id(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 5, 'name': 'Rule', 'tag_name': 'High Value'}

        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        rule = repo.get_rule(5)
        assert rule['name'] == 'Rule'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_rule_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        assert repo.get_rule(999) is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_rule_conditions_serialized(self, mock_get_db, mock_get_cursor, mock_release):
        """Conditions should be JSON-serialized when updating."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from core.tags.repositories.auto_tag_repository import AutoTagRepository
        repo = AutoTagRepository()
        new_conditions = [{'field': 'amount', 'operator': 'gt', 'value': 5000}]
        result = repo.update_rule(5, conditions=new_conditions)
        assert result is True
        # Verify JSON was passed to DB
        call_args = mock_cursor.execute.call_args
        import json
        assert json.dumps(new_conditions) in call_args[0][1]
