"""Data access for fp_contract_configs (per company+brand contract template).

The existence of an active document_type='service' row is what enables the
Service context for a (company, brand). Mirrors DealerConfigRepository."""
from core.base_repository import BaseRepository


class ContractConfigRepository(BaseRepository):

    def list_for_company(self, company_id, document_type='service'):
        """Per-brand contract config for a company's active brands. LEFT JOIN so
        brands without a row appear with empty values (ready to edit)."""
        return self.query_all(
            '''SELECT b.id AS brand_id, b.name AS brand_name,
                      cc.id AS config_id, cc.title, cc.body_template,
                      cc.general_conditions,
                      COALESCE(cc.is_active, FALSE) AS is_active
               FROM company_brands cb
               JOIN brands b ON b.id = cb.brand_id
               LEFT JOIN fp_contract_configs cc
                      ON cc.company_id = cb.company_id AND cc.brand_id = cb.brand_id
                     AND cc.document_type = %s
               WHERE cb.company_id = %s AND cb.is_active = TRUE AND b.is_active = TRUE
               ORDER BY b.name''',
            (document_type, company_id),
        )

    def upsert(self, company_id, brand_id, title, body_template,
               general_conditions, is_active=True, document_type='service'):
        return self.execute(
            '''INSERT INTO fp_contract_configs
                   (company_id, brand_id, document_type, title, body_template,
                    general_conditions, is_active, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
               ON CONFLICT (company_id, brand_id, document_type) DO UPDATE SET
                   title = EXCLUDED.title,
                   body_template = EXCLUDED.body_template,
                   general_conditions = EXCLUDED.general_conditions,
                   is_active = EXCLUDED.is_active,
                   updated_at = NOW()''',
            (company_id, brand_id, document_type, title, body_template,
             general_conditions, is_active),
        )

    def get_active(self, company_id, brand_name, document_type='service'):
        """The active contract template for a (company, brand-name), or None.
        Resolves by brand NAME (JOIN brands) — runtime callers hold the vehicle's
        brand name, not its id — mirroring DealerConfigRepository.get_general_conditions."""
        if not company_id or not brand_name:
            return None
        return self.query_one(
            '''SELECT cc.* FROM fp_contract_configs cc
               JOIN brands b ON b.id = cc.brand_id
               WHERE cc.company_id = %s AND LOWER(b.name) = LOWER(%s)
                 AND cc.document_type = %s AND cc.is_active = TRUE''',
            (company_id, brand_name, document_type),
        )

    def service_enabled(self, company_id, document_type='service') -> list:
        """brand_ids that have an active contract config for this company."""
        rows = self.query_all(
            '''SELECT brand_id FROM fp_contract_configs
               WHERE company_id = %s AND document_type = %s AND is_active = TRUE''',
            (company_id, document_type),
        )
        return [r['brand_id'] for r in (rows or [])]
