"""Data access for buyback_records (vehicle buyback/trade-in lifecycle).

Mirrors foi_parcurs/repositories/foi_parcurs_repository.py::get_contracts:
raw parameterized SQL via BaseRepository's query_one/query_all/execute, and a
lean `_LIST_COLUMNS` constant for the list endpoint.

Injection posture — every WHERE/SET/INSERT/VALUES *value* is bound via %s;
the only things ever interpolated into SQL text are identifiers, in exactly
three controlled spots:
  (a) `list()` interpolates `sort_by`/`sort_dir` — both first validated
      against `_SORT_WHITELIST` / {ASC,DESC}, so a caller value that isn't
      an exact match is discarded and can never reach the query.
  (b) `create()` interpolates the INSERT column NAMES from the caller's
      `data.keys()` (only the VALUES are %s-bound). This is intentional —
      keys are server-controlled — so callers MUST pass a service/route-built
      dict, NEVER unfiltered request JSON.
  (c) `update()` interpolates the SET column names too, but restricts them to
      the `_UPDATABLE_COLUMNS` whitelist first; any unrecognized key is
      silently dropped and never becomes a SQL identifier.
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
    'r.client_asking_price_eur, r.market_price_eur, r.client_source, '
    'r.drive_folder_link, r.target_vehicle_text, '
    'r.target_carpark_vehicle_id, r.crm_deal_id, '
    'r.inspection_report_key, r.inspection_rating, r.reconditioning_cost_eur, '
    'r.inspection_notes, r.inspected_by, r.inspected_at, '
    'r.purchase_price_eur, r.carpark_vehicle_id, '
    'r.bought_at, r.finalized_by, r.lost_reason, '
    'r.created_by, r.updated_by, r.created_at, r.updated_at, r.closed_at, '
    'r.hold_prior_status, r.hold_reason, r.hold_note, r.held_at, r.held_by'
)

_SORT_WHITELIST = {'created_at', 'record_code', 'vin', 'status', 'brand',
                   'client_asking_price_eur', 'market_price_eur'}

# Columns a generic update() may set. Deliberately excludes id, record_code,
# company_id, created_at, created_by (identity/immutable) and status (which
# has its own dedicated set_status() so lifecycle transitions go through one
# sanctioned path). An unrecognized key is silently dropped, never reaches
# SQL as a column identifier.
_UPDATABLE_COLUMNS = {
    'brand_id', 'acquisition_type', 'is_trade_in', 'advisor_id', 'advisor_name',
    'client_type', 'vat_status', 'client_id',
    'seller_name', 'seller_email', 'seller_phone', 'seller_cui',
    'seller_address', 'seller_cnp', 'seller_ci_serie', 'seller_ci_number',
    'seller_reg_no', 'seller_iban', 'seller_legal_rep',
    'brand', 'model', 'variant', 'equipment',
    'vin', 'mileage_km', 'engine_capacity_cm3',
    'fuel_type', 'transmission', 'gearbox',
    'manufacture_date', 'first_registration_date',
    'service_history_uptodate', 'extra_wheels', 'keys_count',
    'has_damage', 'damage_details', 'general_condition',
    'client_asking_price_eur', 'market_price_eur', 'client_source',
    'other_details', 'drive_folder_link',
    'target_vehicle_text', 'target_carpark_vehicle_id', 'crm_deal_id',
    'inspection_report_key', 'inspection_rating', 'reconditioning_cost_eur',
    'inspection_notes', 'inspected_by', 'inspected_at',
    'purchase_price_eur', 'carpark_vehicle_id',
    'bought_at', 'finalized_by', 'lost_reason',
    'hold_prior_status', 'hold_reason', 'hold_note', 'held_at', 'held_by',
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

    def group_company_ids(self, company_id) -> list:
        """Every company id in the same corporate family as `company_id`: the
        root parent (one level up via `parent_company_id`, or the company
        itself when it has no parent) plus every company sharing that root.

        This is the scope for cross-company buyback VIN-history — a car
        evaluated at one Autoworld dealership (e.g. International) must surface
        when the same VIN reappears at a sibling (e.g. Premium). Falls back to
        `[company_id]` when the company row is unknown, so the scope can never
        silently widen to all companies."""
        rows = self.query_all(
            'WITH target AS ('
            '  SELECT COALESCE(parent_company_id, id) AS root'
            '  FROM companies WHERE id = %s'
            ') '
            'SELECT c.id FROM companies c, target t '
            'WHERE c.id = t.root OR c.parent_company_id = t.root',
            (company_id,),
        )
        return [r['id'] for r in rows] or [company_id]

    def vin_history(self, vin, company_ids, exclude_record_id=None) -> list:
        """Prior buyback evaluations for `vin` across `company_ids` (the caller's
        corporate family — see group_company_ids), newest first, each with its
        MOST RECENT offer attached (amount/type/vat/date). Powers the
        'been to buyback before' signal: a car evaluated at one dealership
        surfaces when the same VIN reappears at a sibling.

        VIN is matched case/space-insensitively. A blank VIN or empty
        company_ids returns [] (never a cross-tenant scan). `exclude_record_id`
        drops the record being viewed/created so a record never lists itself.
        """
        norm = str(vin or '').strip()
        if not norm or not company_ids:
            return []
        params = [norm, list(company_ids)]
        exclude_sql = ''
        if exclude_record_id is not None:
            exclude_sql = ' AND r.id <> %s'
            params.append(exclude_record_id)
        return self.query_all(
            'SELECT r.id, r.record_code, r.company_id, co.company AS company_name, '
            '       r.advisor_name, r.status, r.created_at, '
            '       r.client_asking_price_eur, r.market_price_eur, r.purchase_price_eur, '
            '       o.amount_eur AS last_offer_eur, o.offer_type AS last_offer_type, '
            '       o.vat_status AS last_offer_vat, o.created_at AS last_offer_at '
            'FROM buyback_records r '
            'LEFT JOIN companies co ON co.id = r.company_id '
            'LEFT JOIN LATERAL ('
            '    SELECT amount_eur, offer_type, vat_status, created_at '
            '    FROM buyback_offers WHERE record_id = r.id '
            '    ORDER BY created_at DESC, id DESC LIMIT 1'
            ') o ON TRUE '
            'WHERE r.vin IS NOT NULL AND UPPER(TRIM(r.vin)) = UPPER(%s) '
            '  AND r.company_id = ANY(%s)'
            f'{exclude_sql} '
            'ORDER BY r.created_at DESC',
            tuple(params),
        )

    def list(self, company_id=None, status=None, acquisition_type=None, q=None,
             date_from=None, date_to=None, page=1, per_page=25,
             sort_by='created_at', sort_dir='DESC', repeat_scope_ids=None):
        """Paginated, filtered list. Returns (rows, total).

        `q` is an ILIKE substring match over brand/model/vin/record_code and
        the seller/client fields (seller_name/email/phone/cui).
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
            # `status` may be a single value or a comma-separated set (the Hub
            # multi-select filter) → match any of them.
            vals = [s for s in str(status).split(',') if s]
            if len(vals) == 1:
                where_clauses.append('r.status = %s')
                params.append(vals[0])
            elif vals:
                where_clauses.append('r.status = ANY(%s)')
                params.append(vals)
        if acquisition_type:
            where_clauses.append('r.acquisition_type = %s')
            params.append(acquisition_type)
        if q:
            where_clauses.append(
                '(r.brand ILIKE %s OR r.model ILIKE %s OR r.vin ILIKE %s OR r.record_code ILIKE %s'
                ' OR r.seller_name ILIKE %s OR r.seller_email ILIKE %s'
                ' OR r.seller_phone ILIKE %s OR r.seller_cui ILIKE %s)'
            )
            like = f'%{q}%'
            params.extend([like] * 8)
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
        # is_repeat: does this VIN appear in ANOTHER record within the caller's
        # company family (the digital equivalent of their Excel yellow
        # highlight)? Scoped to `repeat_scope_ids` (group_company_ids) when
        # given; otherwise compared across all records. The ANY(%s) sits in the
        # SELECT clause, so its param is bound BEFORE the WHERE params.
        repeat_params = []
        if repeat_scope_ids:
            repeat_scope_sql = ' AND r2.company_id = ANY(%s)'
            repeat_params = [list(repeat_scope_ids)]
        else:
            # No explicit family scope supplied → fall back to the row's OWN
            # company, never a cross-tenant "exists anywhere" oracle. Keeps a
            # future caller that forgets the arg from leaking a repeat flag
            # across unrelated tenants.
            repeat_scope_sql = ' AND r2.company_id = r.company_id'
        is_repeat_expr = (
            'EXISTS(SELECT 1 FROM buyback_records r2 '
            "WHERE r2.vin IS NOT NULL AND TRIM(r2.vin) <> '' "
            'AND UPPER(TRIM(r2.vin)) = UPPER(TRIM(r.vin)) '
            f'AND r2.id <> r.id{repeat_scope_sql}) AS is_repeat'
        )
        data_sql = (
            f'SELECT {_LIST_COLUMNS}, co.company AS company_name, {is_repeat_expr} '
            f'FROM buyback_records r '
            f'LEFT JOIN companies co ON co.id = r.company_id'
            f'{where_sql} '
            f'ORDER BY r.{sort_by} {sort_dir} '
            f'LIMIT %s OFFSET %s'
        )
        data_params = repeat_params + params + [per_page, offset]
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

    def delete(self, id) -> int:
        """Hard delete a buyback_records row — this table has no deleted_at
        column (unlike e.g. buyback_photos), so a record delete is
        permanent. buyback_offers/buyback_photos/buyback_events all declare
        `record_id BIGINT ... REFERENCES buyback_records(id) ON DELETE
        CASCADE`, so their rows for this record are removed automatically by
        Postgres — no explicit child cleanup needed here. Returns the
        rowcount (0 if `id` didn't exist, 1 if it did) so callers (the
        DELETE route) can tell a not-found id from a real delete."""
        return self.execute('DELETE FROM buyback_records WHERE id = %s', (id,))
