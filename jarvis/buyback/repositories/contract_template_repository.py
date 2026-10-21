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
