"""Unit tests for UserRepository.

Tests for core.auth.repositories.user_repository:
- authenticate (valid, not found, inactive, no password hash, wrong password)
- get_online_count (with users, empty)
- update (no args, with args)
- delete_bulk (empty list, non-empty list)
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from core.auth.repositories.user_repository import UserRepository


class TestAuthenticate:
    """Tests for UserRepository.authenticate()."""

    @patch('core.auth.repositories.user_repository.check_password_hash')
    @patch.object(UserRepository, 'get_by_email')
    def test_valid_credentials(self, mock_get_by_email, mock_check_pw):
        """Valid email + password returns user dict."""
        user = {
            'id': 1,
            'email': 'admin@autoworld.ro',
            'name': 'Admin',
            'is_active': True,
            'password_hash': 'pbkdf2:sha256:hashed_value',
        }
        mock_get_by_email.return_value = user
        mock_check_pw.return_value = True

        repo = UserRepository()
        result = repo.authenticate('admin@autoworld.ro', 'secret123')

        assert result is not None
        assert result['id'] == 1
        assert result['email'] == 'admin@autoworld.ro'
        mock_get_by_email.assert_called_once_with('admin@autoworld.ro')
        mock_check_pw.assert_called_once_with('pbkdf2:sha256:hashed_value', 'secret123')

    @patch.object(UserRepository, 'get_by_email')
    def test_user_not_found(self, mock_get_by_email):
        """Non-existent email returns None."""
        mock_get_by_email.return_value = None

        repo = UserRepository()
        result = repo.authenticate('nobody@example.com', 'password')

        assert result is None
        mock_get_by_email.assert_called_once_with('nobody@example.com')

    @patch.object(UserRepository, 'get_by_email')
    def test_inactive_user(self, mock_get_by_email):
        """Inactive user returns None even with correct password."""
        user = {
            'id': 2,
            'email': 'inactive@autoworld.ro',
            'name': 'Inactive User',
            'is_active': False,
            'password_hash': 'pbkdf2:sha256:hashed_value',
        }
        mock_get_by_email.return_value = user

        repo = UserRepository()
        result = repo.authenticate('inactive@autoworld.ro', 'secret123')

        assert result is None

    @patch.object(UserRepository, 'get_by_email')
    def test_no_password_hash_empty_string(self, mock_get_by_email):
        """User with empty password_hash returns None."""
        user = {
            'id': 3,
            'email': 'nopw@autoworld.ro',
            'name': 'No Password',
            'is_active': True,
            'password_hash': '',
        }
        mock_get_by_email.return_value = user

        repo = UserRepository()
        result = repo.authenticate('nopw@autoworld.ro', 'anything')

        assert result is None

    @patch.object(UserRepository, 'get_by_email')
    def test_no_password_hash_none(self, mock_get_by_email):
        """User with None password_hash returns None."""
        user = {
            'id': 4,
            'email': 'nullpw@autoworld.ro',
            'name': 'Null Password',
            'is_active': True,
            'password_hash': None,
        }
        mock_get_by_email.return_value = user

        repo = UserRepository()
        result = repo.authenticate('nullpw@autoworld.ro', 'anything')

        assert result is None

    @patch('core.auth.repositories.user_repository.check_password_hash')
    @patch.object(UserRepository, 'get_by_email')
    def test_wrong_password(self, mock_get_by_email, mock_check_pw):
        """Wrong password returns None."""
        user = {
            'id': 5,
            'email': 'user@autoworld.ro',
            'name': 'User',
            'is_active': True,
            'password_hash': 'pbkdf2:sha256:hashed_value',
        }
        mock_get_by_email.return_value = user
        mock_check_pw.return_value = False

        repo = UserRepository()
        result = repo.authenticate('user@autoworld.ro', 'wrong_password')

        assert result is None
        mock_check_pw.assert_called_once_with('pbkdf2:sha256:hashed_value', 'wrong_password')

    @patch.object(UserRepository, 'get_by_email')
    def test_user_missing_is_active_key(self, mock_get_by_email):
        """User dict without is_active key defaults to False, returns None."""
        user = {
            'id': 6,
            'email': 'nokey@autoworld.ro',
            'name': 'No Key',
            'password_hash': 'pbkdf2:sha256:hashed_value',
        }
        mock_get_by_email.return_value = user

        repo = UserRepository()
        result = repo.authenticate('nokey@autoworld.ro', 'anything')

        assert result is None


class TestGetOnlineCount:
    """Tests for UserRepository.get_online_count()."""

    @patch.object(UserRepository, 'get_online_users')
    def test_with_online_users(self, mock_get_online):
        """Returns count and user list when users are online."""
        online = [
            {'id': 1, 'name': 'Alice', 'email': 'alice@autoworld.ro'},
            {'id': 2, 'name': 'Bob', 'email': 'bob@autoworld.ro'},
        ]
        mock_get_online.return_value = online

        repo = UserRepository()
        result = repo.get_online_count(minutes=5)

        assert result['count'] == 2
        assert len(result['users']) == 2
        assert result['users'][0]['name'] == 'Alice'
        mock_get_online.assert_called_once_with(5)

    @patch.object(UserRepository, 'get_online_users')
    def test_no_online_users(self, mock_get_online):
        """Returns count 0 and empty list when no users are online."""
        mock_get_online.return_value = []

        repo = UserRepository()
        result = repo.get_online_count(minutes=5)

        assert result['count'] == 0
        assert result['users'] == []

    @patch.object(UserRepository, 'get_online_users')
    def test_default_minutes(self, mock_get_online):
        """Default minutes parameter is 5."""
        mock_get_online.return_value = []

        repo = UserRepository()
        repo.get_online_count()

        mock_get_online.assert_called_once_with(5)

    @patch.object(UserRepository, 'get_online_users')
    def test_custom_minutes(self, mock_get_online):
        """Custom minutes parameter is passed through."""
        mock_get_online.return_value = [
            {'id': 1, 'name': 'Alice', 'email': 'alice@autoworld.ro'},
        ]

        repo = UserRepository()
        result = repo.get_online_count(minutes=15)

        assert result['count'] == 1
        mock_get_online.assert_called_once_with(15)


class TestUpdate:
    """Tests for UserRepository.update()."""

    def test_no_arguments_returns_false(self):
        """Calling update with no kwargs returns False without touching DB."""
        repo = UserRepository()
        result = repo.update(user_id=1)

        assert result is False

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_update_name_only(self, mock_get_db, mock_release):
        """Update with name builds correct SQL and returns True."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = UserRepository()
        result = repo.update(user_id=42, name='New Name')

        assert result is True
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'name = %s' in sql
        assert 'updated_at = CURRENT_TIMESTAMP' in sql
        assert params[0] == 'New Name'
        assert params[-1] == 42
        mock_conn.commit.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_update_multiple_fields(self, mock_get_db, mock_release):
        """Update with multiple fields includes all in SQL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = UserRepository()
        result = repo.update(user_id=10, name='Updated', email='new@test.com', is_active=False)

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'name = %s' in sql
        assert 'email = %s' in sql
        assert 'is_active = %s' in sql
        assert params[0] == 'Updated'
        assert params[1] == 'new@test.com'
        assert params[2] is False
        assert params[-1] == 10

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_update_no_rows_affected(self, mock_get_db, mock_release):
        """Update returns False when no rows are affected (user not found)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = UserRepository()
        result = repo.update(user_id=999, name='Ghost')

        assert result is False
        mock_conn.commit.assert_called_once()

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_update_duplicate_email_raises_value_error(self, mock_get_db, mock_release):
        """Update raises ValueError when email conflicts with unique constraint."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('duplicate key value violates unique constraint')

        repo = UserRepository()
        with pytest.raises(ValueError, match='User with that email already exists'):
            repo.update(user_id=1, email='taken@test.com')

        mock_conn.rollback.assert_called_once()


class TestDeleteBulk:
    """Tests for UserRepository.delete_bulk()."""

    def test_empty_list_returns_zero(self):
        """Empty user_ids list returns 0 without touching DB."""
        repo = UserRepository()
        result = repo.delete_bulk([])

        assert result == 0

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_delete_multiple_users(self, mock_get_db, mock_release):
        """Deletes multiple users and returns count."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 3

        repo = UserRepository()
        result = repo.delete_bulk([1, 2, 3])

        assert result == 3
        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'DELETE FROM users' in sql
        assert 'IN' in sql
        assert params == (1, 2, 3)
        mock_conn.commit.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_delete_single_user(self, mock_get_db, mock_release):
        """Deletes single user in list and returns 1."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = UserRepository()
        result = repo.delete_bulk([42])

        assert result == 1

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_delete_bulk_partial(self, mock_get_db, mock_release):
        """Returns actual count when some IDs don't exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 2  # only 2 of 4 existed

        repo = UserRepository()
        result = repo.delete_bulk([1, 2, 999, 1000])

        assert result == 2


class TestGetOnlineUsers:
    """Tests for UserRepository.get_online_users() — direct DB method."""

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_returns_formatted_list(self, mock_get_db, mock_release):
        """Returns list of dicts with id, name, email keys."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Alice', 'email': 'alice@test.com', 'last_seen': '2025-01-01 10:00:00'},
            {'id': 2, 'name': 'Bob', 'email': 'bob@test.com', 'last_seen': '2025-01-01 09:55:00'},
        ]

        repo = UserRepository()
        result = repo.get_online_users(minutes=5)

        assert len(result) == 2
        assert result[0] == {'id': 1, 'name': 'Alice', 'email': 'alice@test.com'}
        assert result[1] == {'id': 2, 'name': 'Bob', 'email': 'bob@test.com'}
        mock_release.assert_called_once_with(mock_conn)

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_empty_result(self, mock_get_db, mock_release):
        """Returns empty list when no users are online."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        repo = UserRepository()
        result = repo.get_online_users()

        assert result == []


class TestGetByEmail:
    """Tests for UserRepository.get_by_email() — direct DB method."""

    @patch('core.base_repository.dict_from_row')
    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_found(self, mock_get_db, mock_release, mock_dict_from_row):
        """Returns user dict when email exists."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        row = {'id': 1, 'email': 'admin@autoworld.ro', 'name': 'Admin'}
        mock_cursor.fetchone.return_value = row
        mock_dict_from_row.return_value = row

        repo = UserRepository()
        result = repo.get_by_email('admin@autoworld.ro')

        assert result is not None
        assert result['email'] == 'admin@autoworld.ro'
        mock_release.assert_called_once_with(mock_conn)

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_not_found(self, mock_get_db, mock_release):
        """Returns None when email does not exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        repo = UserRepository()
        result = repo.get_by_email('nobody@example.com')

        assert result is None


class TestGetById:
    """Tests for UserRepository.get_by_id() — direct DB method."""

    @patch('core.base_repository.dict_from_row')
    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_found(self, mock_get_db, mock_release, mock_dict_from_row):
        """Returns user dict when ID exists."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        row = {'id': 1, 'email': 'admin@autoworld.ro', 'name': 'Admin', 'role_name': 'Super Admin'}
        mock_cursor.fetchone.return_value = row
        mock_dict_from_row.return_value = row

        repo = UserRepository()
        result = repo.get_by_id(1)

        assert result is not None
        assert result['id'] == 1
        assert result['role_name'] == 'Super Admin'

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_db')
    def test_not_found(self, mock_get_db, mock_release):
        """Returns None when ID does not exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        repo = UserRepository()
        result = repo.get_by_id(999)

        assert result is None
