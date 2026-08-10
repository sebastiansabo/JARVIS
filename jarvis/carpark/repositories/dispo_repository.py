"""Dispo Repository — CarPark pipeline dashboard: filtered/paginated vehicle
summary with computed financials, plus company-wide KPIs.

All SQL lives here (never in routes/services), per repo convention. Every
user-supplied filter value is passed as a parameterized query argument —
never string-interpolated into SQL.
"""
from datetime import date, datetime, time
from typing import Optional, Dict, Any, List

from core.base_repository import BaseRepository


# Pipeline stage -> underlying carpark_vehicles.status values.
#
# Every one of the 16 valid vehicle statuses (see VALID_STATUSES in
# carpark.repositories.vehicle_repository) appears in exactly one stage
# bucket below — keep the two in sync if a new status is ever added.
STAGE_STATUS_MAP: Dict[str, List[str]] = {
    'in_pregatire': ['ACQUIRED', 'IN_TRANSIT', 'INSPECTION', 'RECONDITIONING', 'AT_BODYSHOP'],
    'in_stoc': ['READY_FOR_SALE'],
    'promovat': ['LISTED', 'PRICE_REDUCED', 'AUCTION_CANDIDATE'],
    'rezervat': ['RESERVED'],
    'vandut': ['SOLD'],
    'livrat': ['DELIVERED'],
    'iesit': ['RETURNED', 'SCRAPPED', 'TRANSFERRED', 'INSURANCE_CLAIM'],
}

# Stages considered "active" — still moving through the pipeline, not sold,
# delivered, or exited. Used by kpis() for avg_days_in_stock / aged_over_60.
_ACTIVE_STAGES = ('in_pregatire', 'in_stoc', 'promovat', 'rezervat')
_ACTIVE_STATUSES: List[str] = [
    status for stage in _ACTIVE_STAGES for status in STAGE_STATUS_MAP[stage]
]

# status -> stage reverse lookup, built once at import time.
_STATUS_TO_STAGE: Dict[str, str] = {
    status: stage for stage, statuses in STAGE_STATUS_MAP.items() for status in statuses
}

# Columns/expressions a caller may sort by, whitelisted to prevent SQL
# injection via sort_by (which ultimately comes from request query params).
_SORTABLE_COLUMNS: Dict[str, str] = {
    'acquisition_date': 'v.acquisition_date',
    'sale_date': 'v.sale_date',
    'listing_date': 'v.listing_date',
    'delivery_date': 'v.delivery_date',
    'days_in_stock': 'days_in_stock',
    'gross_margin': 'gross_margin',
    'current_price': 'v.current_price',
    'sale_price': 'v.sale_price',
    'acquisition_price': 'v.acquisition_price',
    'brand': 'v.brand',
    'model': 'v.model',
    'status': 'v.status',
    'vin': 'v.vin',
    'created_at': 'v.created_at',
}

# Shared CTEs: per-vehicle cost/revenue totals, the most recent ACTIVE
# reservation, and the distinct set of uploaded document types. Each CTE is
# GROUP BY/DISTINCT ON vehicle_id, so every LEFT JOIN below is at most
# one-row-per-vehicle — joining them never fans out the vehicle row count.
_CTE = """
WITH cost_totals AS (
    SELECT vehicle_id, COALESCE(SUM(amount), 0) AS total_costs
    FROM carpark_vehicle_costs
    GROUP BY vehicle_id
),
rev_totals AS (
    SELECT vehicle_id,
           COALESCE(SUM(amount), 0) AS total_revenues,
           COALESCE(SUM(amount) FILTER (WHERE revenue_type = 'bonus_leasing'), 0) AS bonus_leasing
    FROM carpark_vehicle_revenues
    GROUP BY vehicle_id
),
active_res AS (
    SELECT DISTINCT ON (vehicle_id)
           vehicle_id, id AS reservation_id, reservation_end, client_name,
           deposit_amount, deposit_paid
    FROM carpark_reservations
    WHERE status = 'active'
    ORDER BY vehicle_id, reservation_end DESC NULLS LAST
),
doc_types AS (
    SELECT vehicle_id, array_agg(DISTINCT document_type) AS doc_types
    FROM carpark_vehicle_documents
    GROUP BY vehicle_id
)
"""

_JOINS = """
FROM carpark_vehicles v
LEFT JOIN cost_totals ct ON ct.vehicle_id = v.id
LEFT JOIN rev_totals rt ON rt.vehicle_id = v.id
LEFT JOIN active_res ar ON ar.vehicle_id = v.id
LEFT JOIN doc_types dt ON dt.vehicle_id = v.id
"""


def _margin_pct(gross_margin, sale_price) -> Optional[float]:
    """gross_margin / sale_price * 100, guarded against NULL/zero sale_price."""
    if gross_margin is None or not sale_price:
        return None
    return float(gross_margin) / float(sale_price) * 100


# Key lifecycle dates recorded directly on carpark_vehicles, surfaced as
# timeline() events when non-null — (column, Romanian label). Kept in one
# place so a new lifecycle date field is a one-line addition here.
_TIMELINE_VEHICLE_DATE_FIELDS: List[tuple] = [
    ('acquisition_date', 'Achiziție'),
    ('supplier_payment_date', 'Plată furnizor'),
    ('intake_pv_date', 'PV intrare'),
    ('listing_date', 'Publicare anunț'),
    ('sale_date', 'Vânzare'),
    ('delivery_date', 'Livrare'),
    ('stock_removed_date', 'Scos din stoc'),
]


def _timeline_sort_key(value) -> datetime:
    """Normalize a timeline event's `date` (a date, datetime, or None) into
    a datetime for sorting — carpark_status_history/carpark_vehicle_documents
    carry TIMESTAMPs while the vehicle lifecycle columns are plain DATEs, and
    Python refuses to compare date and datetime directly."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return datetime.min


class DispoRepository(BaseRepository):
    """Aggregated pipeline view over carpark_vehicles for the Dispo dashboard."""

    # ── WHERE-clause builder (shared by summary's rows/count/totals queries
    #    and by the stage_counts query) ──

    def _build_where(self, company_id: int, filters: Dict[str, Any],
                      include_stage: bool = True):
        """Build (where_sql, params) for the given filters.

        Always scopes to company_id + not-soft-deleted. `include_stage=False`
        drops the stage filter — used for stage_counts, so each pipeline tab
        count is computed against every OTHER active filter but NOT the
        stage filter itself (otherwise selecting a tab would collapse every
        other tab's count to zero).
        """
        filters = filters or {}
        clauses = ['v.company_id = %s', 'v.deleted_at IS NULL']
        params: List[Any] = [company_id]

        if include_stage and filters.get('stage'):
            stage_statuses = STAGE_STATUS_MAP.get(filters['stage'])
            if stage_statuses:
                clauses.append('v.status = ANY(%s)')
                params.append(stage_statuses)

        if filters.get('brand'):
            clauses.append('v.brand = %s')
            params.append(filters['brand'])

        if filters.get('location_id'):
            clauses.append('v.location_id = %s')
            params.append(filters['location_id'])

        if filters.get('salesperson_user_id'):
            clauses.append('v.salesperson_user_id = %s')
            params.append(filters['salesperson_user_id'])

        if filters.get('source'):
            clauses.append('v.source = %s')
            params.append(filters['source'])

        if filters.get('sale_type'):
            clauses.append('v.sale_type = %s')
            params.append(filters['sale_type'])

        # Acquisition date range
        if filters.get('date_from'):
            clauses.append('v.acquisition_date >= %s')
            params.append(filters['date_from'])
        if filters.get('date_to'):
            clauses.append('v.acquisition_date <= %s')
            params.append(filters['date_to'])

        # Sale date range
        if filters.get('sale_date_from'):
            clauses.append('v.sale_date >= %s')
            params.append(filters['sale_date_from'])
        if filters.get('sale_date_to'):
            clauses.append('v.sale_date <= %s')
            params.append(filters['sale_date_to'])

        if filters.get('search'):
            term = f"%{filters['search']}%"
            clauses.append(
                '(v.vin ILIKE %s OR v.model ILIKE %s OR v.brand ILIKE %s OR v.buyer_name ILIKE %s)'
            )
            params.extend([term, term, term, term])

        if filters.get('stock_removed') is not None:
            clauses.append('v.stock_removed = %s')
            params.append(bool(filters['stock_removed']))

        return ' AND '.join(clauses), params

    # ── SUMMARY (the Dispo dashboard's main query) ──

    def summary(self, company_id: int, filters: Dict[str, Any] = None,
                page: int = 1, per_page: int = 25,
                sort_by: str = 'acquisition_date', sort_dir: str = 'desc') -> Dict[str, Any]:
        """Paginated, filtered pipeline summary.

        One CTE-backed query (see module-level `_CTE`/`_JOINS`) joins
        per-vehicle cost/revenue totals, the most recent ACTIVE reservation,
        and distinct uploaded document types, and computes `days_in_stock`
        and `gross_margin` in SQL. `margin_pct` is computed here in Python
        (not SQL) since it needs a NULL/zero-guarded division that's awkward
        to express safely per-row in a SELECT list; `gross_margin` and
        `sale_price` are already present on every returned row.

        `missing_docs` is intentionally NOT computed here — each row's
        `doc_types` array is returned so the service/route layer (which owns
        the required-document checklist per vehicle status) can derive it.

        Returns:
            {
                'rows': [...],                        # one dict per vehicle
                'stage_counts': {stage: int, ..., 'all': int},
                'totals': {'acquisition_price': .., 'total_costs': ..,
                           'sale_price': .., 'gross_margin': ..},
                'total': int,      # rows matching filters (for pagination)
                'page': int,
                'per_page': int,
            }
        """
        filters = filters or {}
        page = max(1, int(page))
        per_page = max(1, min(int(per_page), 200))
        offset = (page - 1) * per_page

        sort_col = _SORTABLE_COLUMNS.get(sort_by, _SORTABLE_COLUMNS['acquisition_date'])
        sort_dir_sql = 'ASC' if str(sort_dir).lower() == 'asc' else 'DESC'

        where_sql, params = self._build_where(company_id, filters, include_stage=True)

        # ── total count (matches filtered rows; the CTE joins are all
        #    one-row-per-vehicle so they'd never change a COUNT(*) here —
        #    skip them entirely) ──
        total_row = self.query_one(
            f'SELECT COUNT(*) AS total FROM carpark_vehicles v WHERE {where_sql}',
            tuple(params)
        )
        total = total_row['total'] if total_row else 0

        # ── paginated rows ──
        rows_sql = f"""
            {_CTE}
            SELECT
                v.*,
                COALESCE(ct.total_costs, 0) AS total_costs,
                COALESCE(rt.total_revenues, 0) AS total_revenues,
                COALESCE(rt.bonus_leasing, 0) AS bonus_leasing,
                (COALESCE(v.sale_date, CURRENT_DATE) - v.acquisition_date) AS days_in_stock,
                (v.sale_price - v.acquisition_price - COALESCE(ct.total_costs, 0)) AS gross_margin,
                ar.reservation_id,
                ar.reservation_end,
                ar.client_name AS reservation_client_name,
                ar.deposit_amount AS reservation_deposit_amount,
                ar.deposit_paid AS reservation_deposit_paid,
                COALESCE(dt.doc_types, ARRAY[]::varchar[]) AS doc_types
            {_JOINS}
            WHERE {where_sql}
            ORDER BY {sort_col} {sort_dir_sql} NULLS LAST, v.id DESC
            LIMIT %s OFFSET %s
        """
        rows = self.query_all(rows_sql, tuple(params) + (per_page, offset))

        for row in rows:
            row['margin_pct'] = _margin_pct(row.get('gross_margin'), row.get('sale_price'))

        # ── stage_counts: same filters MINUS the stage filter itself ──
        stage_where_sql, stage_params = self._build_where(company_id, filters, include_stage=False)
        status_counts = self.query_all(f"""
            SELECT v.status, COUNT(*) AS count
            FROM carpark_vehicles v
            WHERE {stage_where_sql}
            GROUP BY v.status
        """, tuple(stage_params))

        stage_counts = {stage: 0 for stage in STAGE_STATUS_MAP}
        all_count = 0
        for row in status_counts:
            cnt = row['count']
            all_count += cnt
            stage = _STATUS_TO_STAGE.get(row['status'])
            if stage:
                stage_counts[stage] += cnt
        stage_counts['all'] = all_count

        # ── totals: SUM of money columns across the FULL filtered set
        #    (respects the stage filter too, unlike stage_counts) ──
        totals_row = self.query_one(f"""
            {_CTE}
            SELECT
                COALESCE(SUM(v.acquisition_price), 0) AS acquisition_price,
                COALESCE(SUM(ct.total_costs), 0) AS total_costs,
                COALESCE(SUM(v.sale_price), 0) AS sale_price,
                COALESCE(SUM(v.sale_price - v.acquisition_price - COALESCE(ct.total_costs, 0)), 0) AS gross_margin
            {_JOINS}
            WHERE {where_sql}
        """, tuple(params))

        return {
            'rows': rows,
            'stage_counts': stage_counts,
            'totals': totals_row or {
                'acquisition_price': 0, 'total_costs': 0, 'sale_price': 0, 'gross_margin': 0,
            },
            'total': total,
            'page': page,
            'per_page': per_page,
        }

    # ── AGING ALERTS ──

    def aged_unsold(self, min_days: int) -> List[Dict[str, Any]]:
        """Unsold vehicles (company-agnostic — the scheduler job scans every
        tenant) whose days_in_stock exceeds min_days.

        "Unsold" = status NOT IN the terminal-exit set (SOLD, DELIVERED,
        SCRAPPED, TRANSFERRED, RETURNED) — deliberately broader than
        _ACTIVE_STATUSES (which also excludes RESERVED): a reserved-but-not-
        yet-sold car has still been sitting in stock and is exactly the kind
        of aging inventory this alert exists to surface. Soft-deleted rows
        are excluded. days_in_stock is CURRENT_DATE - acquisition_date; a
        NULL acquisition_date makes the comparison NULL (excluded by WHERE),
        so no explicit NULL guard is needed, but one is added anyway for
        readability.
        """
        return self.query_all("""
            SELECT id, vin, brand, model,
                   (CURRENT_DATE - acquisition_date) AS days_in_stock,
                   salesperson_user_id, acquisition_manager_id, company_id
            FROM carpark_vehicles
            WHERE status NOT IN ('SOLD', 'DELIVERED', 'SCRAPPED', 'TRANSFERRED', 'RETURNED')
              AND deleted_at IS NULL
              AND acquisition_date IS NOT NULL
              AND (CURRENT_DATE - acquisition_date) > %s
            ORDER BY days_in_stock DESC
        """, (min_days,))

    # ── KPIs ──

    def kpis(self, company_id: int) -> Dict[str, Any]:
        """Company-wide Dispo KPI tile values (unfiltered by pipeline stage).

        Definitions (documented since the brief left them open to
        interpretation):
          - cars_in_stock: vehicles in the 'in_stoc' or 'promovat' stage
            (READY_FOR_SALE / LISTED / PRICE_REDUCED / AUCTION_CANDIDATE) —
            ready-and-actively-being-marketed stock, matching the spec's
            "READY_FOR_SALE + promovat stages" wording.
          - reserved: vehicles currently in status RESERVED.
          - sold_this_month: vehicles with sale_date in the current calendar
            month — status-independent, since a vehicle keeps its sale_date
            after later moving to DELIVERED, so it's still "sold this month".
          - delivered_this_month: vehicles with delivery_date in the current
            calendar month.
          - avg_days_in_stock: average (today - acquisition_date) across
            "active" vehicles — every stage except vandut/livrat/iesit.
          - aged_over_60: count of those same active vehicles with
            (today - acquisition_date) > 60.
          - gross_margin_mtd: SUM(sale_price - acquisition_price - total_costs)
            for vehicles whose sale_date falls in the current calendar month.
        """
        row = self.query_one(f"""
            {_CTE}
            SELECT
                COUNT(*) FILTER (WHERE v.status = ANY(%(in_stock_statuses)s)) AS cars_in_stock,
                COUNT(*) FILTER (WHERE v.status = 'RESERVED') AS reserved,
                COUNT(*) FILTER (
                    WHERE v.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
                      AND v.sale_date < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
                ) AS sold_this_month,
                COUNT(*) FILTER (
                    WHERE v.delivery_date >= DATE_TRUNC('month', CURRENT_DATE)
                      AND v.delivery_date < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
                ) AS delivered_this_month,
                COALESCE(ROUND(AVG(CURRENT_DATE - v.acquisition_date)
                    FILTER (WHERE v.status = ANY(%(active_statuses)s))), 0) AS avg_days_in_stock,
                COUNT(*) FILTER (
                    WHERE v.status = ANY(%(active_statuses)s)
                      AND (CURRENT_DATE - v.acquisition_date) > 60
                ) AS aged_over_60,
                COALESCE(SUM(v.sale_price - v.acquisition_price - COALESCE(ct.total_costs, 0)) FILTER (
                    WHERE v.sale_date >= DATE_TRUNC('month', CURRENT_DATE)
                      AND v.sale_date < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
                ), 0) AS gross_margin_mtd
            {_JOINS}
            WHERE v.company_id = %(company_id)s AND v.deleted_at IS NULL
        """, {
            'company_id': company_id,
            'in_stock_statuses': STAGE_STATUS_MAP['in_stoc'] + STAGE_STATUS_MAP['promovat'],
            'active_statuses': _ACTIVE_STATUSES,
        })
        return row or {
            'cars_in_stock': 0, 'reserved': 0, 'sold_this_month': 0,
            'delivered_this_month': 0, 'avg_days_in_stock': 0,
            'aged_over_60': 0, 'gross_margin_mtd': 0,
        }

    # ── TIMELINE ──

    def timeline(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """Merged, chronologically-sorted event history for a vehicle,
        combining three sources (three separate queries — each is a plain
        one-table SELECT, not worth forcing into a single join):
          - carpark_status_history: every status transition
          - carpark_vehicles: key lifecycle date columns (see
            _TIMELINE_VEHICLE_DATE_FIELDS), one event per non-null column
          - carpark_vehicle_documents: every document upload

        Every event has the shape {type, label, date, meta}. The route
        layer does no assembly of its own — this is the merge point, per
        the module's no-SQL-in-routes convention.
        """
        vehicle_row = self.query_one(
            f"""SELECT {', '.join(field for field, _ in _TIMELINE_VEHICLE_DATE_FIELDS)}
                FROM carpark_vehicles WHERE id = %s""",
            (vehicle_id,)
        ) or {}

        status_rows = self.query_all("""
            SELECT old_status, new_status, notes, changed_by, created_at
            FROM carpark_status_history
            WHERE vehicle_id = %s
            ORDER BY created_at
        """, (vehicle_id,))

        doc_rows = self.query_all("""
            SELECT id, document_type, title, upload_date
            FROM carpark_vehicle_documents
            WHERE vehicle_id = %s
            ORDER BY upload_date
        """, (vehicle_id,))

        events: List[Dict[str, Any]] = []

        for row in status_rows:
            old_status = row.get('old_status')
            new_status = row.get('new_status')
            events.append({
                'type': 'status_change',
                'label': f"{old_status} → {new_status}" if old_status else f"→ {new_status}",
                'date': row.get('created_at'),
                'meta': {
                    'old_status': old_status,
                    'new_status': new_status,
                    'notes': row.get('notes'),
                    'changed_by': row.get('changed_by'),
                },
            })

        for field, label in _TIMELINE_VEHICLE_DATE_FIELDS:
            value = vehicle_row.get(field)
            if value is not None:
                events.append({
                    'type': 'vehicle_date',
                    'label': label,
                    'date': value,
                    'meta': {'field': field},
                })

        for row in doc_rows:
            events.append({
                'type': 'document',
                'label': row.get('document_type'),
                'date': row.get('upload_date'),
                'meta': {
                    'id': row.get('id'),
                    'document_type': row.get('document_type'),
                    'title': row.get('title'),
                },
            })

        events.sort(key=lambda e: _timeline_sort_key(e['date']))
        return events
