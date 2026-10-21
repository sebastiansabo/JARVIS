"""Leasing Company Repository — data access for carpark_leasing_companies
(Task 1 of the CarPark "Documente vânzare" feature).

carpark_leasing_companies is a GLOBAL directory (no company_id): the
"Cumpărător" party details for a sale-via-leasing contract, shared across all
tenant companies and picked by id from a frontend picker added in a later
task of this plan.
"""
from typing import Any, Dict, List, Optional

from core.base_repository import BaseRepository

# Columns a caller may set via create(). Deliberately excludes id/created_by/
# created_at/updated_at (identity + server-managed), mirroring the
# _UPDATABLE whitelist pattern in autovit_listing_repository.py.
_FIELDS = {
    'name', 'cui', 'reg_no', 'address', 'city', 'county',
    'legal_rep', 'legal_rep_role', 'phone', 'email', 'iban',
}


class LeasingCompanyRepository(BaseRepository):
    """Data access for the global carpark_leasing_companies directory."""

    def list_all(self) -> List[Dict[str, Any]]:
        return self.query_all('SELECT * FROM carpark_leasing_companies ORDER BY name')

    def get(self, id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            'SELECT * FROM carpark_leasing_companies WHERE id = %s', (id,))

    def create(self, data: Dict[str, Any], created_by: int) -> Dict[str, Any]:
        """Insert a new leasing company. Unknown keys in `data` are silently
        dropped (not written); `name` is required."""
        if not data.get('name'):
            raise ValueError('name is required')

        cols = {k: v for k, v in data.items() if k in _FIELDS}
        colnames = list(cols.keys()) + ['created_by']
        placeholders = ', '.join(['%s'] * len(colnames))
        values = list(cols.values()) + [created_by]

        return self.execute(
            f"INSERT INTO carpark_leasing_companies ({', '.join(colnames)}) "
            f"VALUES ({placeholders}) RETURNING *",
            tuple(values), returning=True)
