"""User Repository - Data access layer for user operations.

This module handles all database operations related to users.
Business logic should NOT be here - only CRUD operations.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from werkzeug.security import generate_password_hash

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
