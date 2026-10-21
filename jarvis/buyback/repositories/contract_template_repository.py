"""Data access for buyback_contract_templates — per company×brand purchase/
consignment contract templates (legal body text with {tokens}).

Raw parameterized SQL via BaseRepository; every value is %s-bound. One template
per (company_id, brand_id, document_type) enforced by a UNIQUE constraint, so
upsert() is an INSERT ... ON CONFLICT DO UPDATE.
"""
from core.base_repository import BaseRepository


class ContractTemplateRepository(BaseRepository):

    def get_active(self, company_id, brand_id, document_type):
        """The active template for a (company, brand, type), or None."""
        return self.query_one(
            'SELECT * FROM buyback_contract_templates '
            'WHERE company_id = %s AND brand_id = %s AND document_type = %s '
            'AND is_active = TRUE',
            (company_id, brand_id, document_type),
        )

    def get_active_with_default(self, company_id, brand_id, document_type):
        """`get_active` plus a company-wide-default fallback, for the manual
        "generate contract" route (buyback/routes/contract.py): tries the
        brand-specific active row first, then an active company-default row
        (`brand_id IS NULL`) for the same company/document_type.

        `get_active` alone can't express this fallback — its
        `brand_id = %s` predicate never matches a NULL row (SQL's `NULL = x`
        is always NULL/false, never true), even when `brand_id` is itself
        None. Returns None when neither a brand-specific nor a default
        active row exists.
        """
        row = self.get_active(company_id, brand_id, document_type)
        if row is not None:
            return row
        return self.query_one(
            'SELECT * FROM buyback_contract_templates '
            'WHERE company_id = %s AND brand_id IS NULL AND document_type = %s '
            'AND is_active = TRUE',
            (company_id, document_type),
        )

    def brands_for_company(self, company_id):
        """Active brands assigned to a company (id + name), for the editor's
        per-brand template cards. From the company_brands catalog."""
        return self.query_all(
            'SELECT b.id, b.name FROM company_brands cb '
            'JOIN brands b ON b.id = cb.brand_id '
            'WHERE cb.company_id = %s AND COALESCE(cb.is_active, TRUE) '
            '  AND COALESCE(b.is_active, TRUE) ORDER BY b.name',
            (company_id,),
        )

    def list_for_company(self, company_id):
        """Every template configured for a company, by brand then type."""
        return self.query_all(
            'SELECT * FROM buyback_contract_templates WHERE company_id = %s '
            'ORDER BY brand_id, document_type',
            (company_id,),
        )

    def upsert(self, company_id, brand_id, document_type, title, body_template,
               general_conditions, is_active, updated_by):
        """Create or update the one template for (company, brand, type)."""
        return self.execute(
            'INSERT INTO buyback_contract_templates '
            '(company_id, brand_id, document_type, title, body_template, '
            ' general_conditions, is_active, updated_by) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
            'ON CONFLICT (company_id, brand_id, document_type) DO UPDATE SET '
            '  title = EXCLUDED.title, body_template = EXCLUDED.body_template, '
            '  general_conditions = EXCLUDED.general_conditions, '
            '  is_active = EXCLUDED.is_active, updated_by = EXCLUDED.updated_by, '
            '  updated_at = NOW() '
            'RETURNING *',
            (company_id, brand_id, document_type, title, body_template,
             general_conditions, is_active, updated_by),
            returning=True,
        )
