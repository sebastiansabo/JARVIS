"""User Repository - Data access layer for user operations.

This module handles all database operations related to users.
Business logic should NOT be here - only CRUD operations.
"""
from typing import Optional, Dict, Any, List
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
