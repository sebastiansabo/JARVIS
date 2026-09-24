"""Data access for buyback_records (vehicle buyback/trade-in lifecycle).

Mirrors foi_parcurs/repositories/foi_parcurs_repository.py::get_contracts:
raw parameterized SQL via BaseRepository's query_one/query_all/execute, a
lean `_LIST_COLUMNS` constant for the list endpoint, and a sort whitelist +
ASC/DESC guard — the ONLY place an identifier is interpolated into SQL text.
Every other value (including dict-driven INSERT/UPDATE columns, which come
from server-controlled dicts, never raw request bodies) is bound via %s.
"""

from core.base_repository import BaseRepository

# Lean column set for the LIST endpoint — every scalar the list view renders,
# excluding the two heavy free-text blobs (damage_details, other_details)
# that only the detail endpoint (get_by_id, which does SELECT *) needs.
_LIST_COLUMNS = (
    'r.id, r.record_code, r.company_id, r.brand_id, r.status, '
    'r.acquisition_type, r.is_trade_in, r.advisor_id, r.advisor_name, '
    'r.client_type, r.vat_status, r.client_id, '
    'r.seller_name, r.seller_email, r.seller_phone, r.seller_cui, '
    'r.brand, r.model, r.variant, r.equipment, '
    'r.vin, r.mileage_km, r.engine_capacity_cm3, '
    'r.fuel_type, r.transmission, r.gearbox, '
    'r.manufacture_date, r.first_registration_date, '
    'r.service_history_uptodate, r.extra_wheels, r.keys_count, '
    'r.has_damage, r.general_condition, '
    'r.client_asking_price_eur, r.client_source, '
    'r.drive_folder_link, r.target_vehicle_text, '
    'r.target_carpark_vehicle_id, r.crm_deal_id, '
    'r.inspection_report_key, r.inspection_rating, r.reconditioning_cost_eur, '
    'r.inspection_notes, r.inspected_by, r.inspected_at, '
    'r.purchase_price_eur, r.carpark_vehicle_id, '
    'r.bought_at, r.finalized_by, r.lost_reason, '
    'r.created_by, r.updated_by, r.created_at, r.updated_at, r.closed_at'
)

_SORT_WHITELIST = {'created_at', 'record_code', 'vin', 'status', 'brand', 'client_asking_price_eur'}

# Columns a generic update() may set. Deliberately excludes id, record_code,
# company_id, created_at, created_by (identity/immutable) and status (which
# has its own dedicated set_status() so lifecycle transitions go through one
# sanctioned path). An unrecognized key is silently dropped, never reaches
# SQL as a column identifier.
_UPDATABLE_COLUMNS = {
    'brand_id', 'acquisition_type', 'is_trade_in', 'advisor_id', 'advisor_name',
    'client_type', 'vat_status', 'client_id',
    'seller_name', 'seller_email', 'seller_phone', 'seller_cui',
    'brand', 'model', 'variant', 'equipment',
    'vin', 'mileage_km', 'engine_capacity_cm3',
    'fuel_type', 'transmission', 'gearbox',
    'manufacture_date', 'first_registration_date',
    'service_history_uptodate', 'extra_wheels', 'keys_count',
    'has_damage', 'damage_details', 'general_condition',
    'client_asking_price_eur', 'client_source',
    'other_details', 'drive_folder_link',
    'target_vehicle_text', 'target_carpark_vehicle_id', 'crm_deal_id',
    'inspection_report_key', 'inspection_rating', 'reconditioning_cost_eur',
    'inspection_notes', 'inspected_by', 'inspected_at',
    'purchase_price_eur', 'carpark_vehicle_id',
    'bought_at', 'finalized_by', 'lost_reason',
    'updated_by', 'closed_at',
}


class RecordRepository(BaseRepository):

    def create(self, data: dict) -> dict:
        """INSERT into buyback_records with RETURNING *. `data` is a
        server-controlled dict (built by the service/route layer, not a raw
        request body) — its keys drive the column list; only the values are
        parameterized."""
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO buyback_records ({col_names}) VALUES ({placeholders}) RETURNING *'
        return self.execute(sql, tuple(data[c] for c in cols), returning=True)

    def get_by_id(self, id) -> dict | None:
        """Full row (SELECT *) — includes the heavy text blobs the list view omits."""
        return self.query_one('SELECT * FROM buyback_records WHERE id = %s', (id,))

    def list(self, company_id=None, status=None, acquisition_type=None, q=None,
             date_from=None, date_to=None, page=1, per_page=25,
             sort_by='created_at', sort_dir='DESC'):
        """Paginated, filtered list. Returns (rows, total).

        `q` is an ILIKE substring match over brand/model/vin/record_code.
        date_from/date_to filter on created_at; date_to is inclusive of the
        whole day. `sort_by`/`sort_dir` are validated against a whitelist —
        the only place a caller-influenced value is interpolated into SQL
        text rather than bound as a parameter.
        """
        if sort_by not in _SORT_WHITELIST:
            sort_by = 'created_at'
        sort_dir = str(sort_dir).upper() if str(sort_dir).upper() in ('ASC', 'DESC') else 'DESC'

        where_clauses = []
        params = []

        if company_id:
            where_clauses.append('r.company_id = %s')
            params.append(company_id)
        if status:
            where_clauses.append('r.status = %s')
            params.append(status)
        if acquisition_type:
            where_clauses.append('r.acquisition_type = %s')
            params.append(acquisition_type)
        if q:
            where_clauses.append(
                '(r.brand ILIKE %s OR r.model ILIKE %s OR r.vin ILIKE %s OR r.record_code ILIKE %s)'
            )
            like = f'%{q}%'
            params.extend([like, like, like, like])
        if date_from:
            where_clauses.append('r.created_at >= %s')
            params.append(date_from)
        if date_to:
            # inclusive of the whole end day
            where_clauses.append("r.created_at < (%s::date + INTERVAL '1 day')")
            params.append(date_to)

        where_sql = (' WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''

        count_row = self.query_one(
            f'SELECT COUNT(*) AS total FROM buyback_records r{where_sql}',
            tuple(params),
        )
        total = count_row['total'] if count_row else 0

        offset = (page - 1) * per_page
        data_sql = (
            f'SELECT {_LIST_COLUMNS}, co.company AS company_name '
            f'FROM buyback_records r '
            f'LEFT JOIN companies co ON co.id = r.company_id'
            f'{where_sql} '
            f'ORDER BY r.{sort_by} {sort_dir} '
            f'LIMIT %s OFFSET %s'
        )
        data_params = params + [per_page, offset]
        rows = self.query_all(data_sql, tuple(data_params))

        return rows, total

    def update(self, id, data: dict) -> dict:
        """Dynamic SET built only from `_UPDATABLE_COLUMNS`-whitelisted keys
        present in `data`; unrecognized keys are silently dropped (never
        reach SQL as a column identifier). Bumps updated_at. Returns the
        fresh row (a no-op update, e.g. every key unrecognized, just
        re-fetches the current row)."""
        sets = {k: data[k] for k in data if k in _UPDATABLE_COLUMNS}
        if not sets:
            return self.get_by_id(id)
        cols = ', '.join(f'{k} = %s' for k in sets)
        sql = f'UPDATE buyback_records SET {cols}, updated_at = NOW() WHERE id = %s RETURNING *'
        params = list(sets.values()) + [id]
        return self.execute(sql, tuple(params), returning=True)

    def set_status(self, id, status, actor) -> dict:
        """Flip the lifecycle status. `actor` is accepted for interface
        parity with callers that log an audit event alongside this call
        (e.g. via buyback_events) — it is not itself written by this method."""
        sql = 'UPDATE buyback_records SET status = %s, updated_at = NOW() WHERE id = %s RETURNING *'
        return self.execute(sql, (status, id), returning=True)
