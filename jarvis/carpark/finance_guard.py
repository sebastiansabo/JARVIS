"""Single source of truth for CarPark finance fields hidden from users
without can_view_carpark_finance. Used by the Dispo board, the vehicle
detail payload and analytics so JSON/xlsx paths can never drift."""

# ── Dispo summary-row ALIAS names (from DispoRepository) ─────────────────────
# These are the derived/aliased money columns the Dispo board query emits —
# NOT the physical carpark_vehicles table columns. Used by carpark/routes/
# dispo.py for the board rows. Keep these unchanged.
FINANCE_VEHICLE_FIELDS = ('acquisition_price', 'total_costs', 'gross_margin',
                          'margin_pct', 'bonus_leasing')

# ── carpark_vehicles TABLE columns (from schema_carpark.py CREATE TABLE +
#    schema_incremental.py ALTERs) ─────────────────────────────────────────────
# The vehicle-detail payload is `SELECT v.*` from carpark_vehicles and the
# generic PUT writes to it, so the ALIAS tuple above only ever matched
# `acquisition_price` there — the rest of the acquisition/cost/margin data
# leaked and stayed writable. This is the AUTHORITATIVE strip set for that
# table payload. STRIP = acquisition/purchase cost, VAT on cost, cost
# components, the generated total_cost, the negotiation-floor minimum_price
# (the /floor-price endpoint is itself finance-gated), and the cost/margin
# JSON blobs (cost_lines, pricing_sheets — the Fișă de preț snapshots carry
# cost + margin inputs). KEEP (deliberately NOT here) = selling/listing/
# current price columns (list_price, promotional_price, current_price,
# sale_price) — consistent with how the Dispo board keeps sale_price — and
# all non-money attributes/spec/VAT-scheme flags.
FINANCE_VEHICLE_TABLE_FIELDS = (
    'acquisition_value', 'acquisition_vat', 'acquisition_price',
    'acquisition_currency', 'acquisition_exchange_rate',
    'purchase_price_net', 'purchase_price_currency', 'purchase_vat_rate',
    'reconditioning_cost', 'transport_cost', 'registration_cost', 'other_costs',
    'total_cost', 'minimum_price', 'cost_lines', 'pricing_sheets',
)

# ── Analytics finance field names ────────────────────────────────────────────
# Money fields on analytics KPI blocks (Dispo KPIs).
FINANCE_KPI_FIELDS = ('gross_margin_mtd',)
# Nested inventory-summary money field (get_inventory_summary): the acquisition
# spend. total_stock_value (current_price sum) is a selling-side figure and is
# kept. Applies both nested (dashboard summary block) and top-level
# (/analytics/summary payload).
FINANCE_SUMMARY_FIELDS = ('total_acquisition_value',)
# Analytics KPI extras that expose margin: groi = avg_margin_percent × turn_rate
# (recoverable margin). Applies nested (dashboard kpis block) and top-level
# (/analytics/kpis payload).
FINANCE_ANALYTICS_KPI_FIELDS = ('groi',)
# Per-row money on monthly-sales rows (get_monthly_sales): gross_profit
# (= revenue − acquisition − cost) plus any acquisition/cost/margin field.
# month/sold/revenue (revenue == sale_price) survive.
FINANCE_MONTHLY_SALES_ROW_FIELDS = (
    'gross_profit', 'total_acquisition', 'total_cost', 'total_costs',
    'gross_margin', 'margin_pct', 'avg_margin_percent',
)


def strip_finance_fields(payload, fields=FINANCE_VEHICLE_FIELDS):
    """Remove `fields` from a dict in place; returns it. No-op if not a dict."""
    if isinstance(payload, dict):
        for f in fields:
            payload.pop(f, None)
    return payload
