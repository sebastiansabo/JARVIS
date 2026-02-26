"""User Repository - Data access layer for user operations.

This module handles all database operations related to users,
including authentication and online-user tracking.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from core.base_repository import BaseRepository
from database import dict_from_row


class UserRepository(BaseRepository):
    """Repository for user data access operations."""

    def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user by ID with role information."""
        return self.query_one('''
            SELECT u.*, r.name as role_name, r.description as role_description,
                   r.can_add_invoices, r.can_edit_invoices, r.can_delete_invoices, r.can_view_invoices,
                   r.can_access_accounting, r.can_access_settings, r.can_access_connectors,
                   r.can_access_templates, r.can_access_hr, r.is_hr_manager,
                   r.can_access_crm,
                   r.can_edit_crm, r.can_delete_crm, r.can_export_crm
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.id = %s
        ''', (user_id,))

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email address with role information."""
        return self.query_one('''
            SELECT u.*, r.name as role_name, r.description as role_description,
                   r.can_add_invoices, r.can_edit_invoices, r.can_delete_invoices, r.can_view_invoices,
                   r.can_access_accounting, r.can_access_settings, r.can_access_connectors,
                   r.can_access_templates, r.can_access_hr, r.is_hr_manager,
                   r.can_access_crm,
                   r.can_edit_crm, r.can_delete_crm, r.can_export_crm
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.email = %s
        ''', (email,))

    def update_password(self, user_id: int, password: str) -> bool:
        """Update the password for a user."""
        password_hash = generate_password_hash(password)
        return self.execute('''
            UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (password_hash, user_id)) > 0

    def update_last_login(self, user_id: int) -> bool:
        """Update the last login timestamp for a user."""
        return self.execute('''
            UPDATE users SET last_login = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (user_id,)) > 0

    def update_last_seen(self, user_id: int) -> bool:
        """Update the last seen timestamp for a user."""
        return self.execute('''
            UPDATE users SET last_seen = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (user_id,)) > 0

    def get_online_users(self, minutes: int = 5) -> List[Dict[str, Any]]:
        """Get users who have been active in the last N minutes."""
        rows = self.query_all('''
            SELECT id, name, email, last_seen
            FROM users
            WHERE last_seen IS NOT NULL
              AND last_seen > CURRENT_TIMESTAMP - INTERVAL '%s minutes'
            ORDER BY last_seen DESC
        ''', (minutes,))
        return [{'id': row['id'], 'name': row['name'], 'email': row['email']} for row in rows]

    # --- Authentication Methods ---

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user by email and password."""
        user = self.get_by_email(email)
        if not user or not user.get('is_active', False) or not user.get('password_hash'):
            return None
        if not check_password_hash(user['password_hash'], password):
            return None
        return user

    def get_online_count(self, minutes: int = 5) -> dict:
        """Get online users count with user list."""
        users = self.get_online_users(minutes)
        return {'count': len(users), 'users': users}

    # --- Password Reset Token Methods ---

    def create_reset_token(self, user_id: int, token: str, expires_at: datetime) -> bool:
        """Create a password reset token for a user.

        Invalidates any existing unused tokens for the same user.
        """
        def _work(cursor):
            cursor.execute('''
                UPDATE password_reset_tokens
                SET used_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND used_at IS NULL
            ''', (user_id,))
            cursor.execute('''
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (%s, %s, %s)
            ''', (user_id, token, expires_at))
            return True

        return self.execute_many(_work)

    def get_reset_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get a valid (not expired, not used) password reset token."""
        return self.query_one('''
            SELECT t.id, t.user_id, t.token, t.expires_at, t.created_at,
                   u.email, u.name
            FROM password_reset_tokens t
            JOIN users u ON t.user_id = u.id
            WHERE t.token = %s
              AND t.used_at IS NULL
              AND t.expires_at > CURRENT_TIMESTAMP
              AND u.is_active = TRUE
        ''', (token,))

    def mark_token_used(self, token: str) -> bool:
        """Mark a reset token as used."""
        return self.execute('''
            UPDATE password_reset_tokens
            SET used_at = CURRENT_TIMESTAMP
            WHERE token = %s AND used_at IS NULL
        ''', (token,)) > 0

    def delete_expired_tokens(self) -> int:
        """Delete expired and used tokens (cleanup)."""
        return self.execute('''
            DELETE FROM password_reset_tokens
            WHERE used_at IS NOT NULL
               OR expires_at < CURRENT_TIMESTAMP
        ''')

    # --- User CRUD Methods ---

    def get_all(self) -> list[dict]:
        """Get all users with their role information."""
        return self.query_all('''
            SELECT u.*, r.name as role_name, r.description as role_description
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            ORDER BY u.name
        ''')

    def save(self, name: str, email: str = None, phone: str = None,
             role_id: int = None, is_active: bool = True, company: str = None,
             brand: str = None, department: str = None, subdepartment: str = None,
             notify_on_allocation: bool = True) -> int:
        """Save a new user. Returns user ID."""
        try:
            result = self.execute('''
                INSERT INTO users (name, email, phone, role_id, is_active, company, brand, department, subdepartment, notify_on_allocation)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (name, email, phone, role_id, is_active, company, brand, department, subdepartment, notify_on_allocation),
                returning=True)
            return result['id']
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError(f"User with email '{email}' already exists")
            raise

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
        try:
            return self.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", params) > 0
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError("User with that email already exists")
            raise

    def delete(self, user_id: int) -> bool:
        """Delete a user."""
        return self.execute('DELETE FROM users WHERE id = %s', (user_id,)) > 0

    def delete_bulk(self, user_ids: list) -> int:
        """Delete multiple users. Returns count deleted."""
        if not user_ids:
            return 0
        placeholders = ','.join(['%s'] * len(user_ids))
        return self.execute(f'DELETE FROM users WHERE id IN ({placeholders})', tuple(user_ids))

    def bulk_update_role(self, user_ids: list, role_id: int) -> int:
        """Update role for multiple users. Returns count updated."""
        if not user_ids:
            return 0
        placeholders = ','.join(['%s'] * len(user_ids))
        return self.execute(
            f'UPDATE users SET role_id = %s WHERE id IN ({placeholders})',
            (role_id, *user_ids)
        )

    def get_managers_for_department(self, department: str, company: str = None) -> list[dict]:
        """Get users assigned as managers for a specific company + department.

        Looks up manager_ids in department_structure, falls back to manager name match.
        Only returns active users with notify_on_allocation enabled.
        """
        if not company or not department:
            return []

        def _work(cursor):
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

        return self.execute_many(_work)

    def set_default_passwords(self, default_password: str = 'changeme123') -> int:
        """Set default password for all users without a password. Returns count updated."""
        password_hash = generate_password_hash(default_password)
        return self.execute('''
            UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
            WHERE password_hash IS NULL OR password_hash = ''
        ''', (password_hash,))
