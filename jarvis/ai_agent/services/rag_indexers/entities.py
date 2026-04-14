"""
Entity Indexer Mixin

Provides department and employee indexing methods for RAGService:
  - index_department, index_departments_batch, _fetch_department_data, _build_department_content
  - index_employee, index_employees_batch, _fetch_employee_data, _build_employee_content
"""

from typing import Optional, Dict, Any

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ...models import RAGSourceType, ServiceResult

logger = get_logger('jarvis.ai_agent.services.rag')


class EntityIndexerMixin:
    """Mixin providing department and employee indexing methods for RAGService."""

    # ============== Department Indexing ==============

    def _fetch_department_data(self, dept_id: int) -> Optional[Dict]:
        """Fetch department structure data from database."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT * FROM department_structure WHERE id = %s", (dept_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_department_content(self, data: Dict) -> str:
        """Build searchable content from department data."""
        parts = []
        if data.get('department'):
            parts.append(f"Department: {data['department']}")
        if data.get('subdepartment'):
            parts.append(f"Subdepartment: {data['subdepartment']}")
        if data.get('company'):
            parts.append(f"Company: {data['company']}")
        if data.get('brand'):
            parts.append(f"Brand: {data['brand']}")
        if data.get('manager'):
            parts.append(f"Manager: {data['manager']}")
        return "\n".join(parts)

    def index_department(self, dept_id: int) -> ServiceResult:
        """Index a department for RAG search."""
        data = self._fetch_department_data(dept_id)
        if not data:
            return ServiceResult(success=False, error="Department not found")

        content = self._build_department_content(data)
        metadata = {
            'name': data.get('department'),
            'subdepartment': data.get('subdepartment'),
            'company': data.get('company'),
            'brand': data.get('brand'),
        }
        company_id = self._lookup_company_id(data.get('company'))
        return self._index_document(
            RAGSourceType.DEPARTMENT, dept_id, 'department_structure', content, metadata, company_id
        )

    def index_departments_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index departments."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT d.id FROM department_structure d
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'department' AND r.source_id = d.id AND r.is_active = TRUE
                    WHERE r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_department(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} departments")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Department batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Employee Indexing ==============

    def _fetch_employee_data(self, user_id: int) -> Optional[Dict]:
        """Fetch employee/user data from database with org unit and permissions."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT u.*, r.name as role_name,
                       ds.company as org_company, ds.brand as org_brand,
                       ds.department as org_department, ds.subdepartment as org_subdepartment,
                       ds.manager as org_manager
                FROM users u
                LEFT JOIN roles r ON r.id = u.role_id
                LEFT JOIN department_structure ds ON ds.id = u.org_unit_id
                WHERE u.id = %s AND u.is_active = TRUE
            """, (user_id,))
            row = cursor.fetchone()
            if not row:
                return None

            # Fetch permission labels
            cursor.execute("""
                SELECT p.module_label, p.entity_label, p.action_label
                FROM permissions_v2 p
                JOIN role_permissions_v2 rp ON rp.permission_id = p.id
                WHERE rp.role_id = %s
                ORDER BY p.module_label, p.entity_label
            """, (row.get('role_id'),))
            row['permissions'] = [
                f"{r2['module_label']}/{r2['entity_label']}: {r2['action_label']}"
                for r2 in cursor.fetchall()
            ]
            return row
        finally:
            release_db(conn)

    def _build_employee_content(self, data: Dict) -> str:
        """Build searchable content from employee data with Claude enrichment."""
        parts = []
        if data.get('name'):
            parts.append(f"Employee: {data['name']}")
        if data.get('email'):
            parts.append(f"Email: {data['email']}")
        if data.get('phone'):
            parts.append(f"Phone: {data['phone']}")
        # Prefer org unit fields over direct user fields
        company = data.get('org_company') or data.get('company')
        department = data.get('org_department') or data.get('department')
        subdepartment = data.get('org_subdepartment') or data.get('subdepartment')
        brand = data.get('org_brand') or data.get('brand')
        manager = data.get('org_manager')
        if company:
            parts.append(f"Company: {company}")
        if department:
            parts.append(f"Department: {department}")
        if subdepartment:
            parts.append(f"Subdepartment: {subdepartment}")
        if brand:
            parts.append(f"Brand: {brand}")
        if manager:
            parts.append(f"Manager: {manager}")
        if data.get('role_name'):
            parts.append(f"Role: {data['role_name']}")
        # Permissions
        perms = data.get('permissions', [])
        if perms:
            parts.append(f"Permissions: {', '.join(perms)}")
        # Access flags
        access = []
        if data.get('can_access_accounting'):
            access.append('Accounting')
        if data.get('can_add_invoices'):
            access.append('Add Invoices')
        if data.get('can_delete_invoices'):
            access.append('Delete Invoices')
        if data.get('can_access_settings'):
            access.append('Settings')
        if data.get('can_access_connectors'):
            access.append('Connectors')
        if access:
            parts.append(f"Access: {', '.join(access)}")
        # Dates
        if data.get('created_at'):
            parts.append(f"Hire date (account created): {data['created_at']}")
        if data.get('last_login'):
            parts.append(f"Last login: {data['last_login']}")

        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "employee profile")

    def index_employee(self, user_id: int) -> ServiceResult:
        """Index an employee for RAG search."""
        data = self._fetch_employee_data(user_id)
        if not data:
            return ServiceResult(success=False, error="Employee not found")

        content = self._build_employee_content(data)
        metadata = {
            'name': data.get('name'),
            'department': data.get('department'),
            'company': data.get('company'),
            'role': data.get('role_name'),
        }
        company_id = self._lookup_company_id(data.get('company'))
        return self._index_document(
            RAGSourceType.EMPLOYEE, user_id, 'users', content, metadata, company_id
        )

    def index_employees_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index employees."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT u.id FROM users u
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'employee' AND r.source_id = u.id AND r.is_active = TRUE
                    WHERE u.is_active = TRUE AND r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_employee(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} employees")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Employee batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))
