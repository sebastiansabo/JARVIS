"""Data access for fp_document_types — the per-company, user-defined document
type registry (Vânzări / Mașini de curtoazie / …). A document type IS its
contract: it carries the template (title/body/T&C) and an is_rental flag
(rental types expose the car pricing fields). Supersedes the per-(company, brand)
fp_contract_configs read-path. 'sales' is a fixed default (no template, not
rental, not editable/deletable via the API)."""
import re
import unicodedata

from core.base_repository import BaseRepository

# Romanian diacritics → ASCII so slugs are clean, url/DB-safe keys.
_RO_MAP = str.maketrans({
    'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ş': 's', 'ț': 't', 'ţ': 't',
    'Ă': 'a', 'Â': 'a', 'Î': 'i', 'Ș': 's', 'Ş': 's', 'Ț': 't', 'Ţ': 't',
})


def slugify(label: str) -> str:
    """A lowercase ascii slug (letters/digits/dashes) for a type key."""
    s = (label or '').translate(_RO_MAP)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return s or 'tip'


def _has_template(row) -> bool:
    return bool((row or {}).get('body_template'))


class DocumentTypeRepository(BaseRepository):

    def list_for_company(self, company_id, active_only=True) -> list:
        """Document types for a company, sales first, then by sort_order/label.
        `active_only` filters to what the header/car selectors offer; Settings
        passes active_only=False to manage inactive rows too."""
        if not company_id:
            return []
        where = 'WHERE company_id = %s'
        params = [company_id]
        if active_only:
            where += ' AND is_active = TRUE'
        rows = self.query_all(
            f'''SELECT id, key, label, title, body_template, general_conditions,
                       is_rental, is_active, is_default, sort_order
                FROM fp_document_types
                {where}
                ORDER BY is_default DESC, sort_order, label''',
            tuple(params),
        ) or []
        for r in rows:
            r['has_template'] = _has_template(r)
        return rows

    def get(self, company_id, key):
        """Full row for a (company, key), or None."""
        if not company_id or not key:
            return None
        return self.query_one(
            'SELECT * FROM fp_document_types WHERE company_id = %s AND key = %s',
            (company_id, key),
        )

    def get_template(self, company_id, key):
        """The template row (title/body/T&C) for a type, or None when the type
        has no template (e.g. sales) or does not exist. Used by the PDF."""
        row = self.get(company_id, key)
        return row if _has_template(row) else None

    def is_rental(self, company_id, key) -> bool:
        row = self.get(company_id, key)
        return bool(row and row.get('is_rental'))

    def add(self, company_id, label, is_rental=False) -> str:
        """Create a new (non-default) type; returns its generated unique key."""
        if not company_id:
            raise ValueError('company_id required')
        label = (label or '').strip()
        if not label:
            raise ValueError('label required')
        existing = {r['key'] for r in self.list_for_company(company_id, active_only=False)}
        base = slugify(label)
        if base in ('sales', 'service') and base in existing:
            base = f'{base}-1'
        key = base
        n = 2
        while key in existing:
            key = f'{base}-{n}'
            n += 1
        next_order = 1 + max(
            [r.get('sort_order') or 0 for r in self.list_for_company(company_id, active_only=False)],
            default=0,
        )
        self.execute(
            '''INSERT INTO fp_document_types
                   (company_id, key, label, is_rental, is_active, is_default, sort_order, updated_at)
               VALUES (%s, %s, %s, %s, TRUE, FALSE, %s, NOW())''',
            (company_id, key, label, bool(is_rental), next_order),
        )
        return key

    def delete(self, company_id, key):
        """Hard-delete a document type. The default (sales) is protected, and a
        type still referenced by vehicles/sessions is refused (deactivate it
        instead) so no session/vehicle is left pointing at a missing type."""
        if not company_id or not key:
            raise ValueError('company_id and key required')
        row = self.get(company_id, key)
        if not row:
            return  # already gone — no-op
        if row.get('is_default'):
            raise ValueError('The default document type cannot be deleted')
        used = self.query_one(
            '''SELECT
                 (SELECT COUNT(*) FROM fp_vehicles     WHERE company_id = %s AND document_type = %s) AS veh,
                 (SELECT COUNT(*) FROM foi_de_parcurs  WHERE company_id = %s AND document_type = %s) AS ses''',
            (company_id, key, company_id, key),
        ) or {}
        n = int(used.get('veh') or 0) + int(used.get('ses') or 0)
        if n:
            raise ValueError(f'Tipul este folosit de {n} mașini/sesiuni — dezactivează-l în loc să-l ștergi.')
        return self.execute(
            'DELETE FROM fp_document_types WHERE company_id = %s AND key = %s',
            (company_id, key),
        )

    def upsert(self, company_id, key, label, title, body_template,
               general_conditions, is_rental=False, is_active=True):
        """Update an existing type's label/template/flags. The default (sales)
        row is immutable via this path — writes to it are rejected."""
        if not company_id or not key:
            raise ValueError('company_id and key required')
        existing = self.get(company_id, key)
        if existing and existing.get('is_default'):
            raise ValueError('The default document type cannot be modified')
        label = (label or '').strip()
        if not label:
            raise ValueError('label required')
        return self.execute(
            '''INSERT INTO fp_document_types
                   (company_id, key, label, title, body_template, general_conditions,
                    is_rental, is_active, is_default, sort_order, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, 1, NOW())
               ON CONFLICT (company_id, key) DO UPDATE SET
                   label = EXCLUDED.label,
                   title = EXCLUDED.title,
                   body_template = EXCLUDED.body_template,
                   general_conditions = EXCLUDED.general_conditions,
                   is_rental = EXCLUDED.is_rental,
                   is_active = EXCLUDED.is_active,
                   updated_at = NOW()''',
            (company_id, key, label, title, body_template, general_conditions,
             bool(is_rental), bool(is_active)),
        )
