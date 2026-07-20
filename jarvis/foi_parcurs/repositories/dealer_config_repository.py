"""Data access for fp_dealer_config (per company+brand review link + contact)."""
from core.base_repository import BaseRepository


class DealerConfigRepository(BaseRepository):

    def list_for_company(self, company_id):
        """Per-brand dealer config for a company's linked brands. LEFT JOIN so
        brands without a config row appear with empty values."""
        return self.query_all(
            '''SELECT b.id AS brand_id, b.name AS brand_name,
                      dc.review_url, dc.address, dc.phone, dc.email,
                      dc.general_conditions,
                      COALESCE(dc.show_in_foi_parcurs, TRUE) AS show_in_foi_parcurs
               FROM company_brands cb
               JOIN brands b ON b.id = cb.brand_id
               LEFT JOIN fp_dealer_config dc
                      ON dc.company_id = cb.company_id AND dc.brand_id = cb.brand_id
               WHERE cb.company_id = %s AND cb.is_active = TRUE AND b.is_active = TRUE
               ORDER BY b.name''',
            (company_id,),
        )

    def upsert(self, company_id, brand_id, review_url, address, phone, email,
               show_in_foi_parcurs=True, general_conditions=None):
        return self.execute(
            '''INSERT INTO fp_dealer_config
                   (company_id, brand_id, review_url, address, phone, email,
                    show_in_foi_parcurs, general_conditions, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
               ON CONFLICT (company_id, brand_id) DO UPDATE SET
                   review_url = EXCLUDED.review_url,
                   address    = EXCLUDED.address,
                   phone      = EXCLUDED.phone,
                   email      = EXCLUDED.email,
                   show_in_foi_parcurs = EXCLUDED.show_in_foi_parcurs,
                   general_conditions  = EXCLUDED.general_conditions,
                   updated_at = NOW()''',
            (company_id, brand_id, review_url, address, phone, email,
             show_in_foi_parcurs, general_conditions),
        )

    def get_general_conditions(self, company_id, brand_name) -> str:
        """The general-conditions text for a (company, brand-name), '' when unset."""
        if not company_id or not brand_name:
            return ''
        row = self.query_one(
            '''SELECT dc.general_conditions
               FROM fp_dealer_config dc
               JOIN brands b ON b.id = dc.brand_id
               WHERE dc.company_id = %s AND LOWER(b.name) = LOWER(%s)''',
            (company_id, brand_name),
        )
        return ((row or {}).get('general_conditions') or '')
