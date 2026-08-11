"""Transfer Repository — Data access for carpark_transfers (the
inter-company transfer log) and AutoWorld sibling-company group lookups.

AUTOWORLD GROUP: `companies` has `id, company, parent_company_id`.
AUTOWORLD S.R.L. (id=16) is the group root; its subsidiaries (9 PLUS,
10 INTERNATIONAL, 11 PREMIUM, 12 PRESTIGE, 13 NEXT, 14 INSURANCE, 15 ONE)
carry `parent_company_id=16`. A company's GROUP = every company sharing the
same root, computed as `COALESCE(parent_company_id, id)` — this also makes
non-AutoWorld companies (e.g. sentinel test companies, or any future
standalone tenant) each their own single-member group, so the same query
works for both without a hardcoded AutoWorld id anywhere.
"""
from typing import Any, Dict, List, Optional

from core.base_repository import BaseRepository


TRANSFER_FIELDS = (
    'vehicle_id', 'from_company_id', 'to_company_id', 'transfer_price',
    'transfer_currency', 'transfer_date', 'document_id', 'notes', 'created_by',
)


class TransferRepository(BaseRepository):
    """Data access for carpark_transfers + AutoWorld group company lookups."""

    # ── AUTOWORLD GROUP ──

    def group_company_ids(self, company_id: int) -> List[int]:
        """All company ids sharing company_id's group root (INCLUDES
        company_id itself) — used by DispoService.transfer to validate a
        requested to_company_id is a legal destination."""
        rows = self.query_all('''
            SELECT id FROM companies
            WHERE COALESCE(parent_company_id, id) = (
                SELECT COALESCE(parent_company_id, id) FROM companies WHERE id = %s
            )
        ''', (company_id,))
        return [r['id'] for r in rows]

    def group_companies(self, company_id: int) -> List[Dict[str, Any]]:
        """Sibling companies in company_id's group (id, company name),
        EXCLUDING company_id itself, ordered by name — feeds the frontend's
        transfer-destination picker (GET /vehicles/transfer-destinations)."""
        return self.query_all('''
            SELECT id, company FROM companies
            WHERE COALESCE(parent_company_id, id) = (
                SELECT COALESCE(parent_company_id, id) FROM companies WHERE id = %s
            )
            AND id != %s
            ORDER BY company
        ''', (company_id, company_id))

    def company_name(self, company_id: int) -> Optional[str]:
        """Single company's display name — used for best-effort transfer
        notification copy. Returns None if the id doesn't exist."""
        row = self.query_one('SELECT company FROM companies WHERE id = %s', (company_id,))
        return row['company'] if row else None

    def company_editor_user_ids(self, company_id: int, limit: int = 10) -> List[int]:
        """Active users of company_id with carpark edit permission — the
        best-effort destination-side notify targets for a transfer landing
        in their 'În pregătire' queue. Capped small (default 10) since this
        is a courtesy notification, not a distribution list."""
        rows = self.query_all('''
            SELECT u.id FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.company_id = %s AND u.is_active = TRUE AND r.can_edit_carpark = TRUE
            ORDER BY u.id
            LIMIT %s
        ''', (company_id, limit))
        return [r['id'] for r in rows]

    # ── TRANSFERS LOG ──

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a carpark_transfers row. Returns the created record."""
        safe = {k: data[k] for k in TRANSFER_FIELDS if k in data}
        columns = list(safe.keys())
        values = [safe[c] for c in columns]
        placeholders = ', '.join(['%s'] * len(columns))
        col_str = ', '.join(columns)
        return self.execute(
            f'INSERT INTO carpark_transfers ({col_str}) VALUES ({placeholders}) RETURNING *',
            tuple(values), returning=True
        )

    def list_outbound(self, company_id: int) -> List[Dict[str, Any]]:
        """Transfers originating FROM company_id (source-side history),
        most recent first, joined with the vehicle's identifying fields and
        the destination company's name for display convenience. Built now
        for the later source-side 'Transferat' read-only surfacing task —
        not yet wired into a route."""
        return self.query_all('''
            SELECT t.*, v.vin, v.brand, v.model, v.nr_stoc,
                   c.company AS to_company_name
            FROM carpark_transfers t
            JOIN carpark_vehicles v ON v.id = t.vehicle_id
            LEFT JOIN companies c ON c.id = t.to_company_id
            WHERE t.from_company_id = %s
            ORDER BY t.transfer_date DESC, t.id DESC
        ''', (company_id,))
