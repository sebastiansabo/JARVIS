"""Structure Repository - Data access for organizational structure.

Handles all database operations for companies, brands, departments, subdepartments,
company_brands, and department_structure tables.
"""
from typing import Optional, List, Dict, Any

from core.base_repository import BaseRepository


class StructureRepository(BaseRepository):
    """Repository for organizational structure data access operations."""

    # ============== Companies ==============

    def get_all_companies(self) -> List[Dict[str, Any]]:
        """Get all companies with full details including brands."""
        def _work(cursor):
            cursor.execute("""
                SELECT id, company, vat, created_at
                FROM companies
                ORDER BY company
            """)
            companies = []
            for r in cursor.fetchall():
                companies.append({
                    'id': r['id'],
                    'company': r['company'],
                    'vat': r['vat'],
                    'created_at': r['created_at'].isoformat() if r['created_at'] else None
                })

            cursor.execute("""
                SELECT cb.id as cb_id, cb.company_id, cb.brand_id, b.name as brand
                FROM company_brands cb
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.is_active = TRUE ORDER BY b.name
            """)
            brands_by_company = {}
            for r in cursor.fetchall():
                cid = r['company_id']
                if cid not in brands_by_company:
                    brands_by_company[cid] = []
                brands_by_company[cid].append({
                    'id': r['cb_id'],
                    'brand_id': r['brand_id'],
                    'brand': r['brand']
                })

            for company in companies:
                brand_list = brands_by_company.get(company['id'], [])
                company['brands'] = ', '.join(b['brand'] for b in brand_list)
                company['brands_list'] = brand_list

            return companies
        return self.execute_many(_work)

    def create_company(self, company: str, vat: str = None) -> int:
        """Create a new company. Returns the new company ID."""
        result = self.execute("""
            INSERT INTO companies (company, vat)
            VALUES (%s, %s)
            RETURNING id
        """, (company, vat), returning=True)
        return result['id']

    def update_company(self, company_id: int, company: str, vat: str = None) -> bool:
        """Update a company."""
        self.execute("""
            UPDATE companies
            SET company = %s, vat = %s
            WHERE id = %s
        """, (company, vat, company_id))
        return True

    def delete_company(self, company_id: int) -> bool:
        """Delete a company."""
        self.execute("DELETE FROM companies WHERE id = %s", (company_id,))
        return True

    # ============== Company Brands ==============

    def get_company_brands(self, company_id: int = None) -> List[Dict[str, Any]]:
        """Get all company brands."""
        if company_id:
            return self.query_all("""
                SELECT cb.id, cb.company_id, c.company, cb.brand_id, b.name as brand, cb.is_active, cb.created_at
                FROM company_brands cb
                JOIN companies c ON cb.company_id = c.id
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.company_id = %s AND cb.is_active = TRUE
                ORDER BY b.name
            """, (company_id,))
        return self.query_all("""
            SELECT cb.id, cb.company_id, c.company, cb.brand_id, b.name as brand, cb.is_active, cb.created_at
            FROM company_brands cb
            JOIN companies c ON cb.company_id = c.id
            JOIN brands b ON cb.brand_id = b.id
            WHERE cb.is_active = TRUE
            ORDER BY c.company, b.name
        """)

    def get_brands_for_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get brands for a specific company."""
        return self.query_all("""
            SELECT cb.id, cb.brand_id, b.name as brand, cb.is_active
            FROM company_brands cb
            JOIN brands b ON cb.brand_id = b.id
            WHERE cb.company_id = %s AND cb.is_active = TRUE
            ORDER BY b.name
        """, (company_id,))

    def create_company_brand(self, company_id: int, brand_id: int) -> int:
        """Create a new company brand. Returns the new company brand ID."""
        result = self.execute("""
            INSERT INTO company_brands (company_id, brand_id)
            VALUES (%s, %s)
            RETURNING id
        """, (company_id, brand_id), returning=True)
        return result['id']

    def update_company_brand(self, brand_id: int, new_brand_id: int, is_active: bool = True) -> bool:
        """Update a company brand."""
        self.execute("""
            UPDATE company_brands
            SET brand_id = %s, is_active = %s
            WHERE id = %s
        """, (new_brand_id, is_active, brand_id))
        return True

    def delete_company_brand(self, brand_id: int) -> bool:
        """Delete a company brand."""
        self.execute("DELETE FROM company_brands WHERE id = %s", (brand_id,))
        return True

    # ============== Department Structure ==============

    def get_all_department_structures(self) -> List[Dict[str, Any]]:
        """Get all department structure entries."""
        def _work(cursor):
            cursor.execute("""
                SELECT id, company, brand, department, subdepartment, manager, marketing, company_id
                FROM department_structure
                ORDER BY company, brand, department, subdepartment
            """)
            return [{
                'id': r['id'],
                'company': r['company'],
                'brand': r['brand'],
                'department': r['department'],
                'subdepartment': r['subdepartment'],
                'manager': r['manager'],
                'marketing': r['marketing'],
                'company_id': r['company_id']
            } for r in cursor.fetchall()]
        return self.execute_many(_work)

    def create_department_structure(
        self, company_id: int, brand_id: int = None,
        department_id: int = None, subdepartment_id: int = None,
        manager: str = None
    ) -> int:
        """Create a new department structure entry. Returns the new ID."""
        def _work(cursor):
            company_name = None
            if company_id:
                cursor.execute("SELECT company FROM companies WHERE id = %s", (company_id,))
                row = cursor.fetchone()
                if row:
                    company_name = row['company']

            brand_name = self._resolve_name(cursor, 'brands', brand_id)
            dept_name = self._resolve_name(cursor, 'departments', department_id)
            subdept_name = self._resolve_name(cursor, 'subdepartments', subdepartment_id)

            cursor.execute("""
                INSERT INTO department_structure (company_id, company, brand, department, subdepartment, manager)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (company_id, company_name, brand_name, dept_name, subdept_name, manager))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def update_department_structure(
        self, dept_id: int, company_id: int, brand_id: int = None,
        department_id: int = None, subdepartment_id: int = None,
        manager: str = None
    ) -> bool:
        """Update a department structure entry."""
        def _work(cursor):
            company_name = None
            if company_id:
                cursor.execute("SELECT company FROM companies WHERE id = %s", (company_id,))
                row = cursor.fetchone()
                if row:
                    company_name = row['company']

            brand_name = self._resolve_name(cursor, 'brands', brand_id)
            dept_name = self._resolve_name(cursor, 'departments', department_id)
            subdept_name = self._resolve_name(cursor, 'subdepartments', subdepartment_id)

            cursor.execute("""
                UPDATE department_structure
                SET company_id = %s, company = %s, brand = %s, department = %s, subdepartment = %s, manager = %s
                WHERE id = %s
            """, (company_id, company_name, brand_name, dept_name, subdept_name, manager, dept_id))
        self.execute_many(_work)
        return True

    def delete_department_structure(self, dept_id: int) -> bool:
        """Delete a department structure entry."""
        self.execute("DELETE FROM department_structure WHERE id = %s", (dept_id,))
        return True

    # ============== Master Tables ==============

    def get_master_brands(self) -> List[Dict[str, Any]]:
        """Get all brands from master table."""
        def _work(cursor):
            cursor.execute("SELECT id, name, is_active FROM brands WHERE is_active = TRUE ORDER BY name")
            return [{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in cursor.fetchall()]
        return self.execute_many(_work)

    def create_master_brand(self, name: str) -> int:
        """Create a new brand in master table. Returns the new brand ID."""
        result = self.execute("INSERT INTO brands (name) VALUES (%s) RETURNING id", (name,), returning=True)
        return result['id']

    def update_master_brand(self, brand_id: int, name: str, is_active: bool = True) -> bool:
        """Update a brand in master table."""
        self.execute("UPDATE brands SET name = %s, is_active = %s WHERE id = %s",
                     (name, is_active, brand_id))
        return True

    def delete_master_brand(self, brand_id: int) -> bool:
        """Soft delete a brand from master table."""
        self.execute("UPDATE brands SET is_active = FALSE WHERE id = %s", (brand_id,))
        return True

    def get_master_departments(self) -> List[Dict[str, Any]]:
        """Get all departments from master table."""
        def _work(cursor):
            cursor.execute("SELECT id, name, is_active FROM departments WHERE is_active = TRUE ORDER BY name")
            return [{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in cursor.fetchall()]
        return self.execute_many(_work)

    def create_master_department(self, name: str) -> int:
        """Create a new department in master table. Returns the new department ID."""
        result = self.execute("INSERT INTO departments (name) VALUES (%s) RETURNING id", (name,), returning=True)
        return result['id']

    def update_master_department(self, dept_id: int, name: str, is_active: bool = True) -> bool:
        """Update a department in master table."""
        self.execute("UPDATE departments SET name = %s, is_active = %s WHERE id = %s",
                     (name, is_active, dept_id))
        return True

    def delete_master_department(self, dept_id: int) -> bool:
        """Soft delete a department from master table."""
        self.execute("UPDATE departments SET is_active = FALSE WHERE id = %s", (dept_id,))
        return True

    def get_master_subdepartments(self) -> List[Dict[str, Any]]:
        """Get all subdepartments from master table."""
        def _work(cursor):
            cursor.execute("SELECT id, name, is_active FROM subdepartments WHERE is_active = TRUE ORDER BY name")
            return [{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in cursor.fetchall()]
        return self.execute_many(_work)

    def create_master_subdepartment(self, name: str) -> int:
        """Create a new subdepartment in master table. Returns the new subdepartment ID."""
        result = self.execute("INSERT INTO subdepartments (name) VALUES (%s) RETURNING id", (name,), returning=True)
        return result['id']

    def update_master_subdepartment(self, subdept_id: int, name: str, is_active: bool = True) -> bool:
        """Update a subdepartment in master table."""
        self.execute("UPDATE subdepartments SET name = %s, is_active = %s WHERE id = %s",
                     (name, is_active, subdept_id))
        return True

    def delete_master_subdepartment(self, subdept_id: int) -> bool:
        """Soft delete a subdepartment from master table."""
        self.execute("UPDATE subdepartments SET is_active = FALSE WHERE id = %s", (subdept_id,))
        return True

    # ============== Helper Methods ==============

    _ALLOWED_TABLES = frozenset({
        'brands', 'departments', 'subdepartments',
        'positions', 'locations', 'cost_centers',
    })

    def _resolve_name(self, cursor, table: str, value) -> Optional[str]:
        """Resolve a name from a master table by ID or return the value as-is."""
        if not value:
            return None
        if table not in self._ALLOWED_TABLES:
            return None
        if str(value).isdigit():
            cursor.execute(f"SELECT name FROM {table} WHERE id = %s", (int(value),))
            row = cursor.fetchone()
            return row['name'] if row else None
        return value
