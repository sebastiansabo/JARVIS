"""Structure Repository - Data access layer for department structure operations.

Handles department structure CRUD and organizational lookups.
"""
from typing import Optional

from core.base_repository import BaseRepository


class StructureRepository(BaseRepository):
    """Repository for department structure data access operations."""

    def get_all(self) -> list[dict]:
        """Get all department structures with responsable info."""
        return self.query_all('''
            SELECT ds.*, u.name as responsable_name, u.email as responsable_email
            FROM department_structure ds
            LEFT JOIN users u ON ds.responsable_id = u.id
            ORDER BY ds.company, ds.brand, ds.department, ds.subdepartment
        ''')

    def get(self, structure_id: int) -> Optional[dict]:
        """Get a specific department structure by ID."""
        return self.query_one('''
            SELECT ds.*, u.name as responsable_name, u.email as responsable_email
            FROM department_structure ds
            LEFT JOIN users u ON ds.responsable_id = u.id
            WHERE ds.id = %s
        ''', (structure_id,))

    def save(self, company: str, department: str, brand: str = None,
             subdepartment: str = None, manager: str = None,
             marketing: str = None, responsable_id: int = None,
             manager_ids: list = None, marketing_ids: list = None,
             cc_email: str = None) -> int:
        """Create a new department structure entry. Returns structure ID."""
        result = self.execute('''
            INSERT INTO department_structure
                (company, brand, department, subdepartment, manager, marketing,
                 responsable_id, manager_ids, marketing_ids, cc_email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (company, brand, department, subdepartment, manager, marketing,
              responsable_id, manager_ids, marketing_ids, cc_email),
            returning=True)
        return result['id']

    def update(self, structure_id: int, company: str = None, department: str = None,
               brand: str = None, subdepartment: str = None, manager: str = None,
               marketing: str = None, responsable_id: int = None,
               manager_ids: list = None, marketing_ids: list = None,
               cc_email: str = None) -> bool:
        """Update a department structure entry. Returns True if updated."""
        updates = []
        params = []

        if company is not None:
            updates.append('company = %s')
            params.append(company)
        if department is not None:
            updates.append('department = %s')
            params.append(department)
        if brand is not None:
            updates.append('brand = %s')
            params.append(brand)
        if subdepartment is not None:
            updates.append('subdepartment = %s')
            params.append(subdepartment)
        if manager is not None:
            updates.append('manager = %s')
            params.append(manager)
        if marketing is not None:
            updates.append('marketing = %s')
            params.append(marketing)
        if responsable_id is not None:
            updates.append('responsable_id = %s')
            params.append(responsable_id if responsable_id != 0 else None)
        if manager_ids is not None:
            updates.append('manager_ids = %s')
            params.append(manager_ids if manager_ids else None)
        if marketing_ids is not None:
            updates.append('marketing_ids = %s')
            params.append(marketing_ids if marketing_ids else None)
        if cc_email is not None:
            updates.append('cc_email = %s')
            params.append(cc_email if cc_email else None)

        if not updates:
            return False

        params.append(structure_id)
        return self.execute(
            f'UPDATE department_structure SET {", ".join(updates)} WHERE id = %s',
            params
        ) > 0

    def delete(self, structure_id: int) -> bool:
        """Delete a department structure entry."""
        return self.execute('DELETE FROM department_structure WHERE id = %s', (structure_id,)) > 0

    def get_cc_email(self, company: str, department: str) -> Optional[str]:
        """Get the CC email for a specific department in a company."""
        row = self.query_one('''
            SELECT cc_email FROM department_structure
            WHERE company = %s AND department = %s
              AND cc_email IS NOT NULL AND cc_email != ''
            LIMIT 1
        ''', (company, department))
        return row['cc_email'] if row else None

    def get_unique_departments(self, company: str = None) -> list[str]:
        """Get unique department names, optionally filtered by company."""
        if company:
            rows = self.query_all('''
                SELECT DISTINCT department FROM department_structure
                WHERE department IS NOT NULL AND company = %s
                ORDER BY department
            ''', (company,))
        else:
            rows = self.query_all('''
                SELECT DISTINCT department FROM department_structure
                WHERE department IS NOT NULL
                ORDER BY department
            ''')
        return [row['department'] for row in rows]

    def get_unique_brands(self, company: str = None) -> list[str]:
        """Get unique brand names, optionally filtered by company."""
        if company:
            rows = self.query_all('''
                SELECT DISTINCT brand FROM department_structure
                WHERE brand IS NOT NULL AND brand != '' AND company = %s
                ORDER BY brand
            ''', (company,))
        else:
            rows = self.query_all('''
                SELECT DISTINCT brand FROM department_structure
                WHERE brand IS NOT NULL AND brand != ''
                ORDER BY brand
            ''')
        return [row['brand'] for row in rows]
