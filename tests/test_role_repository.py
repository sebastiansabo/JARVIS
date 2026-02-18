"""Unit tests for RoleRepository and PermissionRepository.

Tests for core.roles.repositories:
- RoleRepository: get_all, get, save, update, delete
- PermissionRepository: get_all, get_flat, get_role_permissions (cache),
  get_role_permissions_list (cache), set_role_permissions, check_permission_v2
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from core.roles.repositories.role_repository import RoleRepository
from core.roles.repositories.permission_repository import PermissionRepository, _perm_cache

_R = 'core.base_repository'  # RoleRepository inherits from BaseRepository
_P = 'core.roles.repositories.permission_repository'


def _mock_db():
    return MagicMock(), MagicMock()


# ==================== RoleRepository ====================

class TestRoleGetAll:

    @patch(f'{_R}.dict_from_row')
    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_returns_list(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'id': 1, 'name': 'Admin'}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        result = RoleRepository().get_all()

        assert len(result) == 1
        assert result[0]['name'] == 'Admin'
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_R}.dict_from_row')
    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_empty(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        result = RoleRepository().get_all()
        assert result == []


class TestRoleGet:

    @patch(f'{_R}.dict_from_row')
    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_found(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'id': 1, 'name': 'Admin'}
        mock_cursor.fetchone.return_value = row
        mock_dict.return_value = row

        result = RoleRepository().get(1)

        assert result['name'] == 'Admin'

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        result = RoleRepository().get(999)
        assert result is None


class TestRoleSave:

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 5}

        result = RoleRepository().save(name='Editor', can_view_invoices=True)

        assert result == 5
        mock_conn.commit.assert_called_once()

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_duplicate_raises_value_error(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('duplicate key')

        with pytest.raises(ValueError, match='already exists'):
            RoleRepository().save(name='Admin')

        mock_conn.rollback.assert_called_once()


class TestRoleUpdate:

    def test_no_fields_returns_false(self):
        result = RoleRepository().update(role_id=1)
        assert result is False

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        result = RoleRepository().update(role_id=1, name='Super Admin')

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert 'name = %s' in sql

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        result = RoleRepository().update(role_id=999, name='Ghost')
        assert result is False

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_duplicate_name_raises(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('unique constraint')

        with pytest.raises(ValueError, match='already exists'):
            RoleRepository().update(role_id=1, name='Taken')

        mock_conn.rollback.assert_called_once()


class TestRoleDelete:

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'count': 0}
        mock_cursor.rowcount = 1

        result = RoleRepository().delete(5)

        assert result is True
        mock_conn.commit.assert_called_once()

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_in_use_raises(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'count': 3}

        with pytest.raises(ValueError, match='assigned to users'):
            RoleRepository().delete(1)

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'count': 0}
        mock_cursor.rowcount = 0

        result = RoleRepository().delete(999)
        assert result is False


# ==================== PermissionRepository ====================

class TestPermGetAll:

    @patch(f'{_P}.dict_from_row')
    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_groups_by_module(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        rows = [
            {'id': 1, 'module_key': 'invoices', 'permission_key': 'view', 'label': 'View', 'description': '', 'icon': '', 'sort_order': 1, 'parent_id': None},
            {'id': 2, 'module_key': 'invoices', 'permission_key': 'add', 'label': 'Add', 'description': '', 'icon': '', 'sort_order': 2, 'parent_id': None},
            {'id': 3, 'module_key': 'hr', 'permission_key': 'access', 'label': 'Access', 'description': '', 'icon': '', 'sort_order': 1, 'parent_id': None},
        ]
        mock_cursor.fetchall.return_value = rows
        mock_dict.side_effect = lambda r: dict(r)

        result = PermissionRepository().get_all()

        assert len(result) == 2  # 2 modules
        module_keys = [m['key'] for m in result]
        assert 'invoices' in module_keys
        assert 'hr' in module_keys
        # Invoices module should have 2 permissions
        invoices_mod = next(m for m in result if m['key'] == 'invoices')
        assert len(invoices_mod['permissions']) == 2
        assert invoices_mod['label'] == 'Invoices'


class TestPermGetFlat:

    @patch(f'{_P}.dict_from_row')
    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_returns_flat_list(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        rows = [{'id': 1, 'module_key': 'invoices', 'permission_key': 'view'}]
        mock_cursor.fetchall.return_value = rows
        mock_dict.side_effect = lambda r: dict(r)

        result = PermissionRepository().get_flat()

        assert len(result) == 1
        assert result[0]['permission_key'] == 'view'


class TestPermGetRolePermissions:

    def setup_method(self):
        _perm_cache.clear()

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_returns_grouped_dict(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'module_key': 'invoices', 'permission_key': 'view', 'granted': True},
            {'module_key': 'invoices', 'permission_key': 'add', 'granted': True},
        ]

        result = PermissionRepository().get_role_permissions(1)

        assert result == {'invoices': {'view': True, 'add': True}}

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_uses_cache(self, mock_get_db, mock_get_cursor, mock_release):
        """Second call uses cache, no DB hit."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'module_key': 'invoices', 'permission_key': 'view', 'granted': True},
        ]

        repo = PermissionRepository()
        result1 = repo.get_role_permissions(1)
        result2 = repo.get_role_permissions(1)

        assert result1 == result2
        # get_db should only be called once (cached on second call)
        assert mock_get_db.call_count == 1


class TestPermGetRolePermissionsList:

    def setup_method(self):
        _perm_cache.clear()

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_returns_list_of_dicts(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'module_key': 'invoices', 'permission_key': 'view', 'label': 'View Invoices'},
        ]

        result = PermissionRepository().get_role_permissions_list(1)

        assert len(result) == 1
        assert result[0]['key'] == 'invoices.view'
        assert result[0]['label'] == 'View Invoices'


class TestPermSetRolePermissions:

    def setup_method(self):
        _perm_cache.clear()

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        result = PermissionRepository().set_role_permissions(1, [
            'invoices.view', 'invoices.add', 'system.settings'
        ])

        assert result is True
        mock_conn.commit.assert_called_once()
        # Cache should be cleared
        assert len(_perm_cache) == 0

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_skips_invalid_format(self, mock_get_db, mock_get_cursor, mock_release):
        """Permissions without dots are skipped."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        PermissionRepository().set_role_permissions(1, ['invalid', 'invoices.view'])

        # Should have: 1 delete + 1 valid insert (invalid skipped) + 1 sync = calls
        # The delete is always called, then only valid perms get inserts
        calls = mock_cursor.execute.call_args_list
        insert_calls = [c for c in calls if 'INSERT INTO role_permissions' in str(c)]
        assert len(insert_calls) == 1  # only 'invoices.view'


class TestPermCheckPermissionV2:

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_has_permission(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'scope': 'all', 'granted': True}

        result = PermissionRepository().check_permission_v2(1, 'invoices', 'records', 'view')

        assert result['has_permission'] is True
        assert result['scope'] == 'all'

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_no_permission(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        result = PermissionRepository().check_permission_v2(1, 'invoices', 'records', 'delete')

        assert result['has_permission'] is False
        assert result['scope'] == 'deny'

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_denied_permission(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'scope': 'deny', 'granted': False}

        result = PermissionRepository().check_permission_v2(1, 'hr', 'bonuses', 'edit')

        assert result['has_permission'] is False


class TestPermConnectionRelease:
    """Verify connections are released on exceptions."""

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_get_all_releases_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('DB error')

        with pytest.raises(Exception):
            PermissionRepository().get_all()

        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_R}.release_db')
    @patch(f'{_R}.get_cursor')
    @patch(f'{_R}.get_db')
    def test_role_delete_releases_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('DB error')

        with pytest.raises(Exception):
            RoleRepository().delete(1)

        mock_release.assert_called_once_with(mock_conn)
