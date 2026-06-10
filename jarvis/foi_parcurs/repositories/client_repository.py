"""Data access for fp_clients table (foi de parcurs individual person clients)."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.foi_parcurs.client_repository')


class FPClientRepository(BaseRepository):
    """Repository for fp_clients — individual person clients for foi de parcurs.

    This is SEPARATE from the CRM module's business client table.
    """

    def search_clients(self, query: str, limit: int = 20) -> list:
        """Search by name, phone, or id_document_no using ILIKE."""
        sql = (
            'SELECT id, name, phone, email, date_of_birth, '
            'id_document_type, id_document_no, driver_license_combined, '
            'address, previous_test_drives, previous_comadats, created_at '
            'FROM fp_clients '
            'WHERE name ILIKE %s OR phone ILIKE %s OR id_document_no ILIKE %s '
            'ORDER BY name ASC '
            'LIMIT %s'
        )
        pattern = f'%{query}%'
        return self.query_all(sql, (pattern, pattern, pattern, limit))

    def create_client(self, data: dict) -> dict:
        """INSERT into fp_clients RETURNING *."""
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO fp_clients ({col_names}) VALUES ({placeholders}) RETURNING *'
        return self.execute(sql, tuple(data[c] for c in cols), returning=True)

    def get_client_by_id(self, client_id: int) -> dict:
        """Get a single client by ID."""
        return self.query_one(
            'SELECT * FROM fp_clients WHERE id = %s', (client_id,)
        )

    def update_client_counters(self, client_id: int, route_type: str):
        """Increment previous_test_drives or previous_comadats counter."""
        if route_type == 'TD':
            sql = (
                'UPDATE fp_clients '
                'SET previous_test_drives = COALESCE(previous_test_drives, 0) + 1 '
                'WHERE id = %s'
            )
        else:
            sql = (
                'UPDATE fp_clients '
                'SET previous_comadats = COALESCE(previous_comadats, 0) + 1 '
                'WHERE id = %s'
            )
        return self.execute(sql, (client_id,))
