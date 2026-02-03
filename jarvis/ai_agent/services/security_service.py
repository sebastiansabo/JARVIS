"""
Security Service

Handles authorization and data filtering for AI Agent module.
Ensures users only access data they're permitted to see.
"""

from typing import Optional, List, Dict, Any

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger

logger = get_logger('jarvis.ai_agent.services.security')


class SecurityService:
    """
    Security service for AI Agent data access control.

    Handles:
    - User permission validation
    - Company-level data filtering
    - Sensitive data masking
    """

    def get_user_companies(self, user_id: int) -> List[int]:
        """
        Get list of company IDs the user has access to.

        Args:
            user_id: User ID

        Returns:
            List of company IDs user can access
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            # For now, return all companies the user has interacted with
            # Future: implement proper RBAC based on user role/department
            cursor.execute("""
                SELECT DISTINCT c.id
                FROM companies c
                JOIN invoices i ON i.dedicated_to = c.company
                JOIN users u ON u.id = %s
                WHERE u.can_view_invoices = TRUE
                ORDER BY c.id
            """, (user_id,))

            return [row['id'] for row in cursor.fetchall()]

        finally:
            release_db(conn)

    def can_access_invoice(self, user_id: int, invoice_id: int) -> bool:
        """
        Check if user can access a specific invoice.

        Args:
            user_id: User ID
            invoice_id: Invoice ID

        Returns:
            True if user has access
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                SELECT 1
                FROM invoices i
                JOIN users u ON u.id = %s
                WHERE i.id = %s AND u.can_view_invoices = TRUE
            """, (user_id, invoice_id))

            return cursor.fetchone() is not None

        finally:
            release_db(conn)

    def can_access_conversation(self, user_id: int, conversation_id: int) -> bool:
        """
        Check if user owns a conversation.

        Args:
            user_id: User ID
            conversation_id: Conversation ID

        Returns:
            True if user owns the conversation
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                SELECT 1
                FROM ai_agent.conversations
                WHERE id = %s AND user_id = %s
            """, (conversation_id, user_id))

            return cursor.fetchone() is not None

        finally:
            release_db(conn)

    def filter_rag_results(
        self,
        results: List[Dict],
        user_id: int,
    ) -> List[Dict]:
        """
        Filter RAG results based on user permissions.

        Args:
            results: RAG search results
            user_id: User ID

        Returns:
            Filtered results user is permitted to see
        """
        # Get user's accessible companies
        accessible_companies = set(self.get_user_companies(user_id))

        filtered = []
        for result in results:
            company_id = result.get('company_id')

            # Allow if no company restriction or user has access
            if company_id is None or company_id in accessible_companies:
                filtered.append(result)

        logger.debug(f"Filtered {len(results)} -> {len(filtered)} RAG results for user {user_id}")
        return filtered

    def mask_sensitive_data(
        self,
        content: str,
        mask_patterns: Optional[List[str]] = None,
    ) -> str:
        """
        Mask sensitive data in content.

        Args:
            content: Content to mask
            mask_patterns: Optional patterns to mask

        Returns:
            Content with sensitive data masked
        """
        import re

        if not content:
            return content

        masked = content

        # Default patterns to mask
        patterns = mask_patterns or [
            # Bank account numbers (IBAN)
            (r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b', '[IBAN MASKED]'),
            # Credit card numbers
            (r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[CARD MASKED]'),
            # Personal identification numbers (CNP)
            (r'\b[1-8]\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{6}\b', '[CNP MASKED]'),
        ]

        for pattern, replacement in patterns:
            masked = re.sub(pattern, replacement, masked)

        return masked

    def get_user_permissions(self, user_id: int) -> Dict[str, bool]:
        """
        Get user's permission flags.

        Args:
            user_id: User ID

        Returns:
            Dict of permission flags
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                SELECT can_add_invoices, can_edit_invoices, can_delete_invoices,
                       can_view_invoices, can_access_accounting, can_access_settings,
                       can_access_hr
                FROM users
                WHERE id = %s
            """, (user_id,))

            row = cursor.fetchone()
            if not row:
                return {}

            return {
                'can_add_invoices': row['can_add_invoices'],
                'can_edit_invoices': row['can_edit_invoices'],
                'can_delete_invoices': row['can_delete_invoices'],
                'can_view_invoices': row['can_view_invoices'],
                'can_access_accounting': row['can_access_accounting'],
                'can_access_settings': row['can_access_settings'],
                'can_access_hr': row['can_access_hr'],
            }

        finally:
            release_db(conn)

    def is_admin(self, user_id: int) -> bool:
        """
        Check if user has admin privileges.

        Args:
            user_id: User ID

        Returns:
            True if user is admin
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                SELECT r.name
                FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE u.id = %s
            """, (user_id,))

            row = cursor.fetchone()
            if not row:
                return False

            return row['name'].lower() in ('admin', 'administrator', 'superadmin')

        finally:
            release_db(conn)
