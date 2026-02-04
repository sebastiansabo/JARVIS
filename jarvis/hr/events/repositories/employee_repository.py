"""Employee Repository - Data access for HR employees.

Handles all database operations for the users table (formerly responsables).
"""
from typing import Optional, List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from database import get_db, get_cursor, release_db, dict_from_row


class EmployeeRepository:
    """Repository for employee data access operations."""

    def get_all(
        self,
        active_only: bool = True,
        scope: str = 'all',
        user_context: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Get all HR employees from users table with scope-based filtering.

        Args:
            active_only: If True, only return active employees
            scope: Permission scope ('own', 'department', 'all')
            user_context: Dict with user_id, company, department for scope filtering

        Returns:
            List of employee dictionaries
        """
        conn = get_db()
        cursor = get_cursor(conn)

        query = '''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, is_active, created_at, updated_at
            FROM users
            WHERE 1=1
        '''
        params = []

        if active_only:
            query += ' AND is_active = TRUE'

        # Apply scope-based filtering
        if scope == 'own' and user_context:
            # User can only see themselves
            query += ' AND id = %s'
            params.append(user_context.get('user_id'))
        elif scope == 'department' and user_context:
            # User can see employees in same company + department
            if user_context.get('department') and user_context.get('company'):
                query += ' AND department = %s AND company = %s'
                params.append(user_context['department'])
                params.append(user_context['company'])
        # 'all' scope = no additional filtering

        query += ' ORDER BY name'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        release_db(conn)
        return [dict_from_row(row) for row in rows]

    def get_by_id(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Get a single HR employee by ID.

        Args:
            employee_id: The employee ID

        Returns:
            Employee dict or None if not found
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, is_active, created_at, updated_at
            FROM users WHERE id = %s
        ''', (employee_id,))
        row = cursor.fetchone()
        release_db(conn)
        return dict_from_row(row) if row else None

    def can_access(
        self,
        employee_id: int,
        scope: str,
        user_context: Dict[str, Any]
    ) -> bool:
        """Check if user can access an employee based on their scope.

        Args:
            employee_id: The employee ID to check
            scope: Permission scope ('own', 'department', 'all')
            user_context: Dict with user_id, company, department

        Returns:
            True if user can access, False otherwise
        """
        if scope == 'all':
            return True

        employee = self.get_by_id(employee_id)
        if not employee:
            return False

        if scope == 'own':
            # User can only access their own record
            return employee.get('id') == user_context.get('user_id')

        if scope == 'department':
            # User can access employees in their company + department
            return (employee.get('company') == user_context.get('company') and
                    employee.get('departments') == user_context.get('department'))

        return False

    def create(
        self,
        name: str,
        department: str = None,
        subdepartment: str = None,
        brand: str = None,
        company: str = None,
        email: str = None,
        phone: str = None,
        notify_on_allocation: bool = True
    ) -> int:
        """Create a new HR employee.

        Args:
            name: Employee name
            department: Department name
            subdepartment: Subdepartment name
            brand: Brand name
            company: Company name
            email: Email address
            phone: Phone number
            notify_on_allocation: Whether to notify on allocation

        Returns:
            The new employee ID
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            INSERT INTO users (name, department, subdepartment, brand, company, email, phone, notify_on_allocation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, department, subdepartment, brand, company, email, phone, notify_on_allocation))
        employee_id = cursor.fetchone()['id']
        conn.commit()
        release_db(conn)
        return employee_id

    def update(
        self,
        employee_id: int,
        name: str,
        department: str = None,
        subdepartment: str = None,
        brand: str = None,
        company: str = None,
        email: str = None,
        phone: str = None,
        notify_on_allocation: bool = True,
        is_active: bool = True
    ) -> bool:
        """Update an HR employee.

        Args:
            employee_id: The employee ID
            name: Employee name
            department: Department name
            subdepartment: Subdepartment name
            brand: Brand name
            company: Company name
            email: Email address
            phone: Phone number
            notify_on_allocation: Whether to notify on allocation
            is_active: Whether employee is active

        Returns:
            True if successful
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE users
            SET name = %s, department = %s, subdepartment = %s, brand = %s, company = %s,
                email = %s, phone = %s, notify_on_allocation = %s,
                is_active = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (name, department, subdepartment, brand, company, email, phone,
              notify_on_allocation, is_active, employee_id))
        conn.commit()
        release_db(conn)
        return True

    def delete(self, employee_id: int) -> bool:
        """Soft delete an HR employee (set is_active = FALSE).

        Args:
            employee_id: The employee ID

        Returns:
            True if successful
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE users SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s
        ''', (employee_id,))
        conn.commit()
        release_db(conn)
        return True

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search HR employees by name.

        Args:
            query: Search query string

        Returns:
            List of matching employee dictionaries
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, is_active, created_at, updated_at
            FROM users
            WHERE is_active = TRUE AND name ILIKE %s
            ORDER BY name
            LIMIT 20
        ''', (f'%{query}%',))
        rows = cursor.fetchall()
        release_db(conn)
        return [dict_from_row(row) for row in rows]
