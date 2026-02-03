"""Structure Repository - Data access for organizational structure.

Handles all database operations for companies, brands, departments, subdepartments,
company_brands, and department_structure tables.
"""
from typing import Optional, List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from database import get_db, get_cursor, release_db, dict_from_row


class StructureRepository:
    """Repository for organizational structure data access operations."""

    # ============== Companies ==============

    def get_all_companies(self) -> List[Dict[str, Any]]:
        """Get all companies with full details including brands.

        Returns:
            List of company dictionaries with brands
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)

            # Get companies
            cur.execute("""
                SELECT id, company, vat, created_at
                FROM companies
                ORDER BY company
            """)
            companies = []
            for r in cur.fetchall():
                companies.append({
                    'id': r['id'],
                    'company': r['company'],
                    'vat': r['vat'],
                    'created_at': r['created_at'].isoformat() if r['created_at'] else None
                })

            # Get brands for all companies
            cur.execute("""
                SELECT cb.id as cb_id, cb.company_id, cb.brand_id, b.name as brand
                FROM company_brands cb
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.is_active = TRUE ORDER BY b.name
            """)
            brands_by_company = {}
            for r in cur.fetchall():
                cid = r['company_id']
                if cid not in brands_by_company:
                    brands_by_company[cid] = []
                brands_by_company[cid].append({
                    'id': r['cb_id'],
                    'brand_id': r['brand_id'],
                    'brand': r['brand']
                })

            # Add brands to companies
            for company in companies:
                brand_list = brands_by_company.get(company['id'], [])
                company['brands'] = ', '.join(b['brand'] for b in brand_list)
                company['brands_list'] = brand_list

            return companies
        finally:
            release_db(conn)

    def create_company(self, company: str, vat: str = None) -> int:
        """Create a new company.

        Args:
            company: Company name
            vat: VAT number

        Returns:
            The new company ID
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("""
                INSERT INTO companies (company, vat)
                VALUES (%s, %s)
                RETURNING id
            """, (company, vat))
            company_id = cur.fetchone()['id']
            conn.commit()
            return company_id
        finally:
            release_db(conn)

    def update_company(self, company_id: int, company: str, vat: str = None) -> bool:
        """Update a company.

        Args:
            company_id: The company ID
            company: Company name
            vat: VAT number

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("""
                UPDATE companies
                SET company = %s, vat = %s
                WHERE id = %s
            """, (company, vat, company_id))
            conn.commit()
            return True
        finally:
            release_db(conn)

    def delete_company(self, company_id: int) -> bool:
        """Delete a company.

        Args:
            company_id: The company ID

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("DELETE FROM companies WHERE id = %s", (company_id,))
            conn.commit()
            return True
        finally:
            release_db(conn)

    # ============== Company Brands ==============

    def get_company_brands(self, company_id: int = None) -> List[Dict[str, Any]]:
        """Get all company brands.

        Args:
            company_id: Optional filter by company

        Returns:
            List of company brand dictionaries
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)

            if company_id:
                cur.execute("""
                    SELECT cb.id, cb.company_id, c.company, cb.brand_id, b.name as brand, cb.is_active, cb.created_at
                    FROM company_brands cb
                    JOIN companies c ON cb.company_id = c.id
                    JOIN brands b ON cb.brand_id = b.id
                    WHERE cb.company_id = %s AND cb.is_active = TRUE
                    ORDER BY b.name
                """, (company_id,))
            else:
                cur.execute("""
                    SELECT cb.id, cb.company_id, c.company, cb.brand_id, b.name as brand, cb.is_active, cb.created_at
                    FROM company_brands cb
                    JOIN companies c ON cb.company_id = c.id
                    JOIN brands b ON cb.brand_id = b.id
                    WHERE cb.is_active = TRUE
                    ORDER BY c.company, b.name
                """)

            rows = cur.fetchall()
            return [dict_from_row(r) for r in rows]
        finally:
            release_db(conn)

    def get_brands_for_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get brands for a specific company.

        Args:
            company_id: The company ID

        Returns:
            List of brand dictionaries
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("""
                SELECT cb.id, cb.brand_id, b.name as brand, cb.is_active
                FROM company_brands cb
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.company_id = %s AND cb.is_active = TRUE
                ORDER BY b.name
            """, (company_id,))
            rows = cur.fetchall()
            return [dict_from_row(r) for r in rows]
        finally:
            release_db(conn)

    def create_company_brand(self, company_id: int, brand_id: int) -> int:
        """Create a new company brand.

        Args:
            company_id: The company ID
            brand_id: The brand ID

        Returns:
            The new company brand ID
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("""
                INSERT INTO company_brands (company_id, brand_id)
                VALUES (%s, %s)
                RETURNING id
            """, (company_id, brand_id))
            cb_id = cur.fetchone()['id']
            conn.commit()
            return cb_id
        finally:
            release_db(conn)

    def update_company_brand(self, brand_id: int, new_brand_id: int, is_active: bool = True) -> bool:
        """Update a company brand.

        Args:
            brand_id: The company brand ID
            new_brand_id: The new brand ID
            is_active: Whether the brand is active

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("""
                UPDATE company_brands
                SET brand_id = %s, is_active = %s
                WHERE id = %s
            """, (new_brand_id, is_active, brand_id))
            conn.commit()
            return True
        finally:
            release_db(conn)

    def delete_company_brand(self, brand_id: int) -> bool:
        """Delete a company brand.

        Args:
            brand_id: The company brand ID

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("DELETE FROM company_brands WHERE id = %s", (brand_id,))
            conn.commit()
            return True
        finally:
            release_db(conn)

    # ============== Department Structure ==============

    def get_all_department_structures(self) -> List[Dict[str, Any]]:
        """Get all department structure entries.

        Returns:
            List of department structure dictionaries
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("""
                SELECT id, company, brand, department, subdepartment, manager, marketing, company_id
                FROM department_structure
                ORDER BY company, brand, department, subdepartment
            """)
            rows = cur.fetchall()
            return [{
                'id': r['id'],
                'company': r['company'],
                'brand': r['brand'],
                'department': r['department'],
                'subdepartment': r['subdepartment'],
                'manager': r['manager'],
                'marketing': r['marketing'],
                'company_id': r['company_id']
            } for r in rows]
        finally:
            release_db(conn)

    def create_department_structure(
        self,
        company_id: int,
        brand_id: int = None,
        department_id: int = None,
        subdepartment_id: int = None,
        manager: str = None
    ) -> int:
        """Create a new department structure entry.

        Args:
            company_id: The company ID
            brand_id: The brand ID (or name)
            department_id: The department ID (or name)
            subdepartment_id: The subdepartment ID (or name)
            manager: Manager name

        Returns:
            The new department structure ID
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)

            # Look up company name
            company_name = None
            if company_id:
                cur.execute("SELECT company FROM companies WHERE id = %s", (company_id,))
                row = cur.fetchone()
                if row:
                    company_name = row['company']

            # Look up names from master tables if numeric IDs are passed
            brand_name = self._resolve_name(cur, 'brands', brand_id)
            dept_name = self._resolve_name(cur, 'departments', department_id)
            subdept_name = self._resolve_name(cur, 'subdepartments', subdepartment_id)

            cur.execute("""
                INSERT INTO department_structure (company_id, company, brand, department, subdepartment, manager)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (company_id, company_name, brand_name, dept_name, subdept_name, manager))
            dept_id = cur.fetchone()['id']
            conn.commit()
            return dept_id
        finally:
            release_db(conn)

    def update_department_structure(
        self,
        dept_id: int,
        company_id: int,
        brand_id: int = None,
        department_id: int = None,
        subdepartment_id: int = None,
        manager: str = None
    ) -> bool:
        """Update a department structure entry.

        Args:
            dept_id: The department structure ID
            company_id: The company ID
            brand_id: The brand ID (or name)
            department_id: The department ID (or name)
            subdepartment_id: The subdepartment ID (or name)
            manager: Manager name

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)

            # Look up company name
            company_name = None
            if company_id:
                cur.execute("SELECT company FROM companies WHERE id = %s", (company_id,))
                row = cur.fetchone()
                if row:
                    company_name = row['company']

            # Look up names from master tables
            brand_name = self._resolve_name(cur, 'brands', brand_id)
            dept_name = self._resolve_name(cur, 'departments', department_id)
            subdept_name = self._resolve_name(cur, 'subdepartments', subdepartment_id)

            cur.execute("""
                UPDATE department_structure
                SET company_id = %s, company = %s, brand = %s, department = %s, subdepartment = %s, manager = %s
                WHERE id = %s
            """, (company_id, company_name, brand_name, dept_name, subdept_name, manager, dept_id))
            conn.commit()
            return True
        finally:
            release_db(conn)

    def delete_department_structure(self, dept_id: int) -> bool:
        """Delete a department structure entry.

        Args:
            dept_id: The department structure ID

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("DELETE FROM department_structure WHERE id = %s", (dept_id,))
            conn.commit()
            return True
        finally:
            release_db(conn)

    # ============== Master Tables ==============

    def get_master_brands(self) -> List[Dict[str, Any]]:
        """Get all brands from master table.

        Returns:
            List of brand dictionaries
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("SELECT id, name, is_active FROM brands WHERE is_active = TRUE ORDER BY name")
            rows = cur.fetchall()
            return [{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in rows]
        finally:
            release_db(conn)

    def create_master_brand(self, name: str) -> int:
        """Create a new brand in master table.

        Args:
            name: Brand name

        Returns:
            The new brand ID
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("INSERT INTO brands (name) VALUES (%s) RETURNING id", (name,))
            brand_id = cur.fetchone()['id']
            conn.commit()
            return brand_id
        finally:
            release_db(conn)

    def update_master_brand(self, brand_id: int, name: str, is_active: bool = True) -> bool:
        """Update a brand in master table.

        Args:
            brand_id: The brand ID
            name: Brand name
            is_active: Whether brand is active

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("UPDATE brands SET name = %s, is_active = %s WHERE id = %s",
                        (name, is_active, brand_id))
            conn.commit()
            return True
        finally:
            release_db(conn)

    def delete_master_brand(self, brand_id: int) -> bool:
        """Soft delete a brand from master table.

        Args:
            brand_id: The brand ID

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("UPDATE brands SET is_active = FALSE WHERE id = %s", (brand_id,))
            conn.commit()
            return True
        finally:
            release_db(conn)

    def get_master_departments(self) -> List[Dict[str, Any]]:
        """Get all departments from master table.

        Returns:
            List of department dictionaries
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("SELECT id, name, is_active FROM departments WHERE is_active = TRUE ORDER BY name")
            rows = cur.fetchall()
            return [{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in rows]
        finally:
            release_db(conn)

    def create_master_department(self, name: str) -> int:
        """Create a new department in master table.

        Args:
            name: Department name

        Returns:
            The new department ID
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("INSERT INTO departments (name) VALUES (%s) RETURNING id", (name,))
            dept_id = cur.fetchone()['id']
            conn.commit()
            return dept_id
        finally:
            release_db(conn)

    def update_master_department(self, dept_id: int, name: str, is_active: bool = True) -> bool:
        """Update a department in master table.

        Args:
            dept_id: The department ID
            name: Department name
            is_active: Whether department is active

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("UPDATE departments SET name = %s, is_active = %s WHERE id = %s",
                        (name, is_active, dept_id))
            conn.commit()
            return True
        finally:
            release_db(conn)

    def delete_master_department(self, dept_id: int) -> bool:
        """Soft delete a department from master table.

        Args:
            dept_id: The department ID

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("UPDATE departments SET is_active = FALSE WHERE id = %s", (dept_id,))
            conn.commit()
            return True
        finally:
            release_db(conn)

    def get_master_subdepartments(self) -> List[Dict[str, Any]]:
        """Get all subdepartments from master table.

        Returns:
            List of subdepartment dictionaries
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("SELECT id, name, is_active FROM subdepartments WHERE is_active = TRUE ORDER BY name")
            rows = cur.fetchall()
            return [{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in rows]
        finally:
            release_db(conn)

    def create_master_subdepartment(self, name: str) -> int:
        """Create a new subdepartment in master table.

        Args:
            name: Subdepartment name

        Returns:
            The new subdepartment ID
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("INSERT INTO subdepartments (name) VALUES (%s) RETURNING id", (name,))
            subdept_id = cur.fetchone()['id']
            conn.commit()
            return subdept_id
        finally:
            release_db(conn)

    def update_master_subdepartment(self, subdept_id: int, name: str, is_active: bool = True) -> bool:
        """Update a subdepartment in master table.

        Args:
            subdept_id: The subdepartment ID
            name: Subdepartment name
            is_active: Whether subdepartment is active

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("UPDATE subdepartments SET name = %s, is_active = %s WHERE id = %s",
                        (name, is_active, subdept_id))
            conn.commit()
            return True
        finally:
            release_db(conn)

    def delete_master_subdepartment(self, subdept_id: int) -> bool:
        """Soft delete a subdepartment from master table.

        Args:
            subdept_id: The subdepartment ID

        Returns:
            True if successful
        """
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute("UPDATE subdepartments SET is_active = FALSE WHERE id = %s", (subdept_id,))
            conn.commit()
            return True
        finally:
            release_db(conn)

    # ============== Helper Methods ==============

    def _resolve_name(self, cursor, table: str, value) -> Optional[str]:
        """Resolve a name from a master table by ID or return the value as-is.

        Args:
            cursor: Database cursor
            table: Table name (brands, departments, subdepartments)
            value: ID or name value

        Returns:
            The resolved name or None
        """
        if not value:
            return None
        if str(value).isdigit():
            cursor.execute(f"SELECT name FROM {table} WHERE id = %s", (int(value),))
            row = cursor.fetchone()
            return row['name'] if row else None
        return value
