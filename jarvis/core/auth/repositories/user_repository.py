"""User Repository - Data access layer for user operations.

This module handles all database operations related to users,
including authentication and online-user tracking.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
from database import get_db, get_cursor, release_db, dict_from_row


class UserRepository:
    """Repository for user data access operations."""

    def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user by ID with role information.

        Args:
            user_id: The user ID

        Returns:
            User dict with role permissions, or None if not found
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                SELECT u.*, r.name as role_name, r.description as role_description,
                       r.can_add_invoices, r.can_edit_invoices, r.can_delete_invoices, r.can_view_invoices,
                       r.can_access_accounting, r.can_access_settings, r.can_access_connectors,
                       r.can_access_templates, r.can_access_hr, r.is_hr_manager
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.id
                WHERE u.id = %s
            ''', (user_id,))
            user = cursor.fetchone()
            return dict_from_row(user) if user else None
        finally:
            release_db(conn)

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email address with role information.

        Args:
            email: The user's email address

        Returns:
            User dict with role permissions, or None if not found
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                SELECT u.*, r.name as role_name, r.description as role_description,
                       r.can_add_invoices, r.can_edit_invoices, r.can_delete_invoices, r.can_view_invoices,
                       r.can_access_accounting, r.can_access_settings, r.can_access_connectors,
                       r.can_access_templates, r.can_access_hr, r.is_hr_manager
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
            ''', (email,))
            user = cursor.fetchone()
            return dict_from_row(user) if user else None
        finally:
            release_db(conn)

    def update_password(self, user_id: int, password: str) -> bool:
        """Update the password for a user.

        Args:
            user_id: The user ID
            password: The new plain-text password (will be hashed)

        Returns:
            True if updated, False otherwise
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            password_hash = generate_password_hash(password)

            cursor.execute('''
                UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (password_hash, user_id))

            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            release_db(conn)

    def update_last_login(self, user_id: int) -> bool:
        """Update the last login timestamp for a user.

        Args:
            user_id: The user ID

        Returns:
            True if updated, False otherwise
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                UPDATE users SET last_login = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (user_id,))

            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            release_db(conn)

    def update_last_seen(self, user_id: int) -> bool:
        """Update the last seen timestamp for a user.

        Args:
            user_id: The user ID

        Returns:
            True if updated, False otherwise
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                UPDATE users SET last_seen = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (user_id,))

            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            release_db(conn)

    def get_online_users(self, minutes: int = 5) -> List[Dict[str, Any]]:
        """Get users who have been active in the last N minutes.

        Args:
            minutes: Number of minutes to consider a user "online"

        Returns:
            List of online user dicts with id, name, email
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                SELECT id, name, email, last_seen
                FROM users
                WHERE last_seen IS NOT NULL
                  AND last_seen > CURRENT_TIMESTAMP - INTERVAL '%s minutes'
                ORDER BY last_seen DESC
            ''', (minutes,))

            rows = cursor.fetchall()
            return [{'id': row['id'], 'name': row['name'], 'email': row['email']} for row in rows]
        finally:
            release_db(conn)

    # --- Authentication Methods ---

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user by email and password.

        Args:
            email: User's email address
            password: Plain-text password to check

        Returns:
            User dict if credentials are valid, None otherwise
        """
        user = self.get_by_email(email)
        if not user or not user.get('is_active', False) or not user.get('password_hash'):
            return None
        if not check_password_hash(user['password_hash'], password):
            return None
        return user

    def get_online_count(self, minutes: int = 5) -> dict:
        """Get online users count with user list.

        Args:
            minutes: Number of minutes to consider a user "online"

        Returns:
            Dict with 'count' and 'users' list
        """
        users = self.get_online_users(minutes)
        return {'count': len(users), 'users': users}

    # --- Password Reset Token Methods ---

    def create_reset_token(self, user_id: int, token: str, expires_at: datetime) -> bool:
        """Create a password reset token for a user.

        Invalidates any existing unused tokens for the same user.

        Args:
            user_id: The user ID
            token: The reset token string
            expires_at: When the token expires

        Returns:
            True if created successfully
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            # Invalidate existing unused tokens for this user
            cursor.execute('''
                UPDATE password_reset_tokens
                SET used_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND used_at IS NULL
            ''', (user_id,))

            # Create new token
            cursor.execute('''
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (%s, %s, %s)
            ''', (user_id, token, expires_at))

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            release_db(conn)

    def get_reset_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get a valid (not expired, not used) password reset token.

        Args:
            token: The reset token string

        Returns:
            Token dict with user_id, or None if invalid/expired/used
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                SELECT t.id, t.user_id, t.token, t.expires_at, t.created_at,
                       u.email, u.name
                FROM password_reset_tokens t
                JOIN users u ON t.user_id = u.id
                WHERE t.token = %s
                  AND t.used_at IS NULL
                  AND t.expires_at > CURRENT_TIMESTAMP
                  AND u.is_active = TRUE
            ''', (token,))

            row = cursor.fetchone()
            return dict_from_row(row) if row else None
        finally:
            release_db(conn)

    def mark_token_used(self, token: str) -> bool:
        """Mark a reset token as used.

        Args:
            token: The reset token string

        Returns:
            True if updated
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                UPDATE password_reset_tokens
                SET used_at = CURRENT_TIMESTAMP
                WHERE token = %s AND used_at IS NULL
            ''', (token,))

            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            release_db(conn)

    def delete_expired_tokens(self) -> int:
        """Delete expired and used tokens (cleanup).

        Returns:
            Number of tokens deleted
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                DELETE FROM password_reset_tokens
                WHERE used_at IS NOT NULL
                   OR expires_at < CURRENT_TIMESTAMP
            ''')

            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            release_db(conn)

    # --- User CRUD Methods ---

    def get_all(self) -> list[dict]:
        """Get all users with their role information."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT u.*, r.name as role_name, r.description as role_description
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.id
                ORDER BY u.name
            ''')
            return [dict_from_row(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def save(self, name: str, email: str = None, phone: str = None,
             role_id: int = None, is_active: bool = True, company: str = None,
             brand: str = None, department: str = None, subdepartment: str = None,
             notify_on_allocation: bool = True) -> int:
        """Save a new user. Returns user ID."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO users (name, email, phone, role_id, is_active, company, brand, department, subdepartment, notify_on_allocation)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (name, email, phone, role_id, is_active, company, brand, department, subdepartment, notify_on_allocation))
            user_id = cursor.fetchone()['id']
            conn.commit()
            return user_id
        except Exception as e:
            conn.rollback()
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError(f"User with email '{email}' already exists")
            raise
        finally:
            release_db(conn)

    def update(self, user_id: int, name: str = None, email: str = None,
               phone: str = None, role_id: int = None, is_active: bool = None,
               company: str = None, brand: str = None, department: str = None,
               subdepartment: str = None, notify_on_allocation: bool = None) -> bool:
        """Update a user. Returns True if updated."""
        updates = []
        params = []
        if name is not None:
            updates.append('name = %s')
            params.append(name)
        if email is not None:
            updates.append('email = %s')
            params.append(email)
        if phone is not None:
            updates.append('phone = %s')
            params.append(phone)
        if role_id is not None:
            updates.append('role_id = %s')
            params.append(role_id)
        if is_active is not None:
            updates.append('is_active = %s')
            params.append(is_active)
        if company is not None:
            updates.append('company = %s')
            params.append(company)
        if brand is not None:
            updates.append('brand = %s')
            params.append(brand)
        if department is not None:
            updates.append('department = %s')
            params.append(department)
        if subdepartment is not None:
            updates.append('subdepartment = %s')
            params.append(subdepartment)
        if notify_on_allocation is not None:
            updates.append('notify_on_allocation = %s')
            params.append(notify_on_allocation)
        if not updates:
            return False
        updates.append('updated_at = CURRENT_TIMESTAMP')
        params.append(user_id)
        # Guard: updates are code-controlled literals, never user input
        assert all(isinstance(u, str) and ('= %s' in u or u == 'updated_at = CURRENT_TIMESTAMP') for u in updates), \
            "SQL SET clauses must be parameterized strings"
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", params)
            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        except Exception as e:
            conn.rollback()
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError("User with that email already exists")
            raise
        finally:
            release_db(conn)

    def delete(self, user_id: int) -> bool:
        """Delete a user."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            release_db(conn)

    def delete_bulk(self, user_ids: list) -> int:
        """Delete multiple users. Returns count deleted."""
        if not user_ids:
            return 0
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            placeholders = ','.join(['%s'] * len(user_ids))
            cursor.execute(f'DELETE FROM users WHERE id IN ({placeholders})', tuple(user_ids))
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count
        finally:
            release_db(conn)

    def get_managers_for_department(self, department: str, company: str = None) -> list[dict]:
        """Get users assigned as managers for a specific company + department.

        Looks up manager_ids in department_structure, falls back to manager name match.
        Only returns active users with notify_on_allocation enabled.
        """
        if not company or not department:
            return []
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT manager_ids, manager
                FROM department_structure
                WHERE company = %s AND department = %s
                LIMIT 1
            ''', (company, department))
            row = cursor.fetchone()
            if not row:
                return []
            manager_ids = row['manager_ids']
            manager_name = row['manager']
            if manager_ids:
                cursor.execute('''
                    SELECT id, name, email, phone, department, subdepartment,
                           company, brand, notify_on_allocation, is_active
                    FROM users
                    WHERE id = ANY(%s)
                          AND is_active = TRUE AND notify_on_allocation = TRUE
                ''', (manager_ids,))
            elif manager_name:
                cursor.execute('''
                    SELECT id, name, email, phone, department, subdepartment,
                           company, brand, notify_on_allocation, is_active
                    FROM users
                    WHERE LOWER(name) = LOWER(%s)
                          AND is_active = TRUE AND notify_on_allocation = TRUE
                ''', (manager_name,))
            else:
                return []
            return [dict_from_row(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def set_default_passwords(self, default_password: str = 'changeme123') -> int:
        """Set default password for all users without a password. Returns count updated."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            password_hash = generate_password_hash(default_password)
            cursor.execute('''
                UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
                WHERE password_hash IS NULL OR password_hash = ''
            ''', (password_hash,))
            updated_count = cursor.rowcount
            conn.commit()
            return updated_count
        finally:
            release_db(conn)
