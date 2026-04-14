"""Employee Repository - Data access for HR employees.

Handles all database operations for the users table (formerly responsables).
"""
from typing import Optional, List, Dict, Any

from core.base_repository import BaseRepository
from core.utils.scope_filter import apply_scope_filter


class EmployeeRepository(BaseRepository):
    """Repository for employee data access operations."""

    def get_all(self, active_only: bool = True, scope: str = 'all',
                user_context: Dict[str, Any] = None,
                contract_status: str = None) -> List[Dict[str, Any]]:
        """Get all HR employees from users table with scope-based filtering."""
        query = '''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, notify_missing_punch, is_active, contract_status, created_at, updated_at
            FROM users
            WHERE 1=1
        '''
        params = []

        if contract_status:
            query += ' AND contract_status = %s'
            params.append(contract_status)
        elif active_only:
            query += ' AND is_active = TRUE'

        scope_sql, scope_params = apply_scope_filter(scope, user_context)
        query += scope_sql
        params.extend(scope_params)

        query += ' ORDER BY name'
        return self.query_all(query, params)

    def get_by_id(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Get a single HR employee by ID."""
        return self.query_one('''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, notify_missing_punch, is_active, contract_status, created_at, updated_at
            FROM users WHERE id = %s
        ''', (employee_id,))

    def can_access(self, employee_id: int, scope: str, user_context: Dict[str, Any]) -> bool:
        """Check if user can access an employee based on their scope."""
        if scope == 'all':
            return True
        employee = self.get_by_id(employee_id)
        if not employee:
            return False
        if scope == 'own':
            return employee.get('id') == user_context.get('user_id')
        if scope == 'department':
            return (employee.get('company') == user_context.get('company') and
                    employee.get('departments') == user_context.get('department'))
        return False

    def create(self, name: str, department: str = None, subdepartment: str = None,
               brand: str = None, company: str = None, email: str = None,
               phone: str = None, notify_on_allocation: bool = True) -> int:
        """Create a new HR employee. Returns the new employee ID."""
        result = self.execute('''
            INSERT INTO users (name, department, subdepartment, brand, company, email, phone, notify_on_allocation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, department, subdepartment, brand, company, email, phone, notify_on_allocation),
            returning=True)
        return result['id']

    def update(self, employee_id: int, name: str, department: str = None,
               subdepartment: str = None, brand: str = None, company: str = None,
               email: str = None, phone: str = None, notify_on_allocation: bool = True,
               is_active: bool = True, contract_status: str = None,
               notify_missing_punch: bool = None) -> bool:
        """Update an HR employee."""
        self.execute('''
            UPDATE users
            SET name = %s, department = %s, subdepartment = %s, brand = %s, company = %s,
                email = %s, phone = %s, notify_on_allocation = %s,
                is_active = %s, contract_status = COALESCE(%s, contract_status),
                notify_missing_punch = COALESCE(%s, notify_missing_punch),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (name, department, subdepartment, brand, company, email, phone,
              notify_on_allocation, is_active, contract_status, notify_missing_punch, employee_id))
        return True

    def delete(self, employee_id: int) -> bool:
        """Soft delete an HR employee (set contract_status = 'closed', trigger syncs is_active)."""
        self.execute('''
            UPDATE users SET contract_status = 'closed', updated_at = CURRENT_TIMESTAMP WHERE id = %s
        ''', (employee_id,))
        return True

    def bulk_toggle_missing_punch(self, user_ids: List[int] = None, enabled: bool = True,
                                   scope: str = 'all', user_context: Dict[str, Any] = None) -> int:
        """Toggle notify_missing_punch for given user IDs, or scoped active users if user_ids is None."""
        if user_ids:
            placeholders = ','.join(['%s'] * len(user_ids))
            query = f'''
                UPDATE users SET notify_missing_punch = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
            '''
            params = [enabled] + list(user_ids)
        else:
            query = '''
                UPDATE users SET notify_missing_punch = %s, updated_at = CURRENT_TIMESTAMP
                WHERE COALESCE(contract_status, 'active') = 'active'
            '''
            params = [enabled]

        # Apply scope filter so non-admin users only affect their scope
        if scope != 'all' and user_context:
            scope_sql, scope_params = apply_scope_filter(scope, user_context)
            query += scope_sql
            params.extend(scope_params)

        result = self.execute(query, params)
        return result if isinstance(result, int) else 0

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search HR employees by name (active + suspended only)."""
        return self.query_all('''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, notify_missing_punch, is_active, contract_status, created_at, updated_at
            FROM users
            WHERE is_active = TRUE AND name ILIKE %s
            ORDER BY name
            LIMIT 20
        ''', (f'%{query}%',))
