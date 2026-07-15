"""Data access for foi_de_parcurs and foi_de_parcurs_audit tables."""

import json
import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.foi_parcurs.repository')


class FoiParcursRepository(BaseRepository):

    def create_contract(self, data: dict) -> dict:
        """INSERT into foi_de_parcurs with RETURNING *."""
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO foi_de_parcurs ({col_names}) VALUES ({placeholders}) RETURNING *'
        return self.execute(sql, tuple(data[c] for c in cols), returning=True)

    def create_audit_entry(self, data: dict) -> dict:
        """INSERT into foi_de_parcurs_audit."""
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO foi_de_parcurs_audit ({col_names}) VALUES ({placeholders}) RETURNING *'
        return self.execute(sql, tuple(data[c] for c in cols), returning=True)

    def get_contracts(self, vin=None, company_id=None, status=None,
                      batch_id=None, page=1, per_page=25,
                      sort_by='created_at', sort_dir='DESC'):
        """Paginated list with optional filters. Returns (rows, total)."""
        allowed_sort = {'created_at', 'contract_id', 'vin', 'km_start', 'km_end',
                        'route_type', 'distance_km', 'status', 'batch_id'}
        if sort_by not in allowed_sort:
            sort_by = 'created_at'
        if sort_dir.upper() not in ('ASC', 'DESC'):
            sort_dir = 'DESC'

        where_clauses = []
        params = []

        if vin:
            where_clauses.append('fp.vin = %s')
            params.append(vin)
        if company_id:
            where_clauses.append('fp.company_id = %s')
            params.append(company_id)
        if status:
            where_clauses.append('fp.status = %s')
            params.append(status)
        if batch_id:
            where_clauses.append('fp.batch_id = %s')
            params.append(batch_id)

        where_sql = (' WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''

        count_row = self.query_one(
            f'SELECT COUNT(*) AS total FROM foi_de_parcurs fp{where_sql}',
            tuple(params),
        )
        total = count_row['total'] if count_row else 0

        offset = (page - 1) * per_page
        data_sql = (
            f'SELECT fp.*, '
            f'c.name AS client_name, c.phone AS client_phone, '
            f'co.company AS company_name '
            f'FROM foi_de_parcurs fp '
            f'LEFT JOIN fp_clients c ON c.id = fp.client_id '
            f'LEFT JOIN companies co ON co.id = fp.company_id'
            f'{where_sql} '
            f'ORDER BY fp.{sort_by} {sort_dir} '
            f'LIMIT %s OFFSET %s'
        )
        params.extend([per_page, offset])
        rows = self.query_all(data_sql, tuple(params))

        return rows, total

    def get_contract_by_id(self, contract_id: int) -> dict:
        """Single contract with client + company join."""
        sql = (
            'SELECT fp.*, '
            'c.name AS client_name, c.phone AS client_phone, '
            'co.company AS company_name '
            'FROM foi_de_parcurs fp '
            'LEFT JOIN fp_clients c ON c.id = fp.client_id '
            'LEFT JOIN companies co ON co.id = fp.company_id '
            'WHERE fp.id = %s'
        )
        return self.query_one(sql, (contract_id,))

    def get_contracts_by_batch_id(self, batch_id: str) -> list:
        """Get all contracts for a batch."""
        sql = (
            'SELECT fp.*, '
            'c.name AS client_name, c.phone AS client_phone, '
            'co.company AS company_name '
            'FROM foi_de_parcurs fp '
            'LEFT JOIN fp_clients c ON c.id = fp.client_id '
            'LEFT JOIN companies co ON co.id = fp.company_id '
            'WHERE fp.batch_id = %s '
            'ORDER BY fp.slot_number ASC'
        )
        return self.query_all(sql, (batch_id,))

    def create_from_td_form(self, data: dict) -> dict:
        """Create a FILLED contract from test drive form data."""
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO foi_de_parcurs ({col_names}) VALUES ({placeholders}) RETURNING *'
        row = self.execute(sql, tuple(data[c] for c in cols), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row

    def allocate_client(self, contract_id: int, data: dict) -> dict:
        """Update a PENDING contract with client allocation data."""
        sets = ', '.join(f'{k} = %s' for k in data.keys())
        sql = f'UPDATE foi_de_parcurs SET {sets}, updated_at = NOW() WHERE id = %s RETURNING *'
        params = list(data.values()) + [contract_id]
        return self.execute(sql, tuple(params), returning=True)

    def record_return(self, contract_id: int, data: dict) -> dict:
        """Update a TD contract with return data (km/fuel/damage/signatures) and mark COMPLETED.

        `return_datetime` (if provided in data) is stored as-is; if missing/falsy,
        it defaults to NOW() via COALESCE.
        """
        data = dict(data)
        if 'return_damage' in data:
            data['return_damage'] = json.dumps(data['return_damage'])
        return_datetime = data.pop('return_datetime', None)

        sets = [f'{k} = %s' for k in data.keys()]
        params = list(data.values())
        sets.append('return_datetime = COALESCE(%s, NOW())')
        params.append(return_datetime)

        sets_sql = ', '.join(sets)
        sql = (
            f'UPDATE foi_de_parcurs SET {sets_sql}, '
            f"returned_at = NOW(), status = 'COMPLETED', updated_at = NOW() "
            f"WHERE id = %s AND route_type = 'TD' RETURNING *"
        )
        params.append(contract_id)
        row = self.execute(sql, tuple(params), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row
