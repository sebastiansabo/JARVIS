"""Read-only data access for first-party integrations.

Sources the JARVIS **company structure** (the existing ``companies`` table) as the
single source of truth for which tenants exist — no parallel membership store.
Only ``is_active`` companies are selectable as BUSINESS CONTROL tenants.
"""
from core.base_repository import BaseRepository


class IntegrationsRepository(BaseRepository):
    """Company-structure reads for the BUSINESS CONTROL multi-tenant selector."""

    def list_active_companies(self) -> list:
        """All active companies, ordered by name. Each: {id, company}."""
        return self.query_all(
            'SELECT id, company FROM companies WHERE is_active = TRUE ORDER BY company'
        ) or []

    def get_active_company(self, company_id):
        """A single active company by id, or None (also None for a NULL id)."""
        if company_id is None:
            return None
        return self.query_one(
            'SELECT id, company FROM companies WHERE id = %s AND is_active = TRUE',
            (company_id,),
        )
