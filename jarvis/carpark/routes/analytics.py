"""Analytics API routes — Dashboard, KPIs, and aggregated stats."""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.finance_guard import (
    FINANCE_VEHICLE_FIELDS, FINANCE_KPI_FIELDS, FINANCE_SUMMARY_FIELDS,
    FINANCE_ANALYTICS_KPI_FIELDS, FINANCE_MONTHLY_SALES_ROW_FIELDS,
    strip_finance_fields,
)
from carpark.routes.vehicles import carpark_required, carpark_finance_required, _acting_company_id
from carpark.services.analytics_service import AnalyticsService

logger = logging.getLogger('jarvis.carpark.analytics')

_analytics = AnalyticsService()


def _strip_analytics_finance(data):
    """Redact finance data from an analytics payload for callers without
    carpark.view_finance. One helper covers every analytics shape — the full
    dashboard, the /kpis payload, the /summary payload and the /monthly-sales
    payload — so no sibling endpoint can drift. Verified against the real
    repository output in carpark/repositories/analytics_repository.py:
      - `profitability` (get_profitability_overview) is entirely money/margin —
        dropped wholesale. Present top-level on get_dashboard() and get_kpis().
      - `cost_overview` (get_cost_overview) is a per-cost-type spend breakdown —
        dropped. Dashboard-only (pop is a no-op elsewhere).
      - `summary.total_acquisition_value` (get_inventory_summary) is acquisition
        spend — dropped, whether nested under a dashboard `summary` block or the
        top-level /analytics/summary payload. total_stock_value (current_price
        sum) is a selling-side figure and is kept.
      - `groi` (avg_margin_percent × turn_rate — recoverable margin) — dropped,
        whether nested under the dashboard `kpis` block or top-level on the
        /analytics/kpis payload.
      - monthly-sales rows carry `gross_profit` (= revenue − acquisition − cost);
        that per-row profit is dropped while month/sold/revenue stay — mirrors
        how /dispo keeps sale_price (revenue) but strips acquisition/cost/margin.
        Rows live under `monthly_sales` (dashboard) or `sales` (/monthly-sales).
    The trailing FINANCE_VEHICLE_FIELDS/FINANCE_KPI_FIELDS strips are
    forward-compat only. Mutates `data` in place; returns it."""
    if not isinstance(data, dict):
        return data
    # Structural removal — wholesale finance-bearing blocks.
    data.pop('profitability', None)
    data.pop('cost_overview', None)
    # Inventory-summary acquisition spend — nested (dashboard) + top-level (/summary).
    summary = data.get('summary')
    if isinstance(summary, dict):
        strip_finance_fields(summary, FINANCE_SUMMARY_FIELDS)
    strip_finance_fields(data, FINANCE_SUMMARY_FIELDS)
    # GROI margin KPI — nested (dashboard kpis block) + top-level (/kpis).
    kpis = data.get('kpis')
    if isinstance(kpis, dict):
        strip_finance_fields(kpis, FINANCE_ANALYTICS_KPI_FIELDS)
    strip_finance_fields(data, FINANCE_ANALYTICS_KPI_FIELDS)
    # Per-row sales profit — dashboard `monthly_sales` + /monthly-sales `sales`.
    for key in ('monthly_sales', 'sales'):
        rows = data.get(key)
        if isinstance(rows, list):
            for row in rows:
                strip_finance_fields(row, FINANCE_MONTHLY_SALES_ROW_FIELDS + FINANCE_VEHICLE_FIELDS)
    # Forward-compat literal-name strip (harmless; no top-level match today).
    strip_finance_fields(data, FINANCE_VEHICLE_FIELDS)
    strip_finance_fields(data, FINANCE_KPI_FIELDS)
    return data


# ── Full dashboard ─────────────────────────────────────────

@carpark_bp.route('/analytics/dashboard', methods=['GET'])
@login_required
@carpark_required
def analytics_dashboard():
    """Full dashboard payload — single endpoint for the frontend."""
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    period = request.args.get('period', '90', type=str)
    try:
        period_days = int(period)
    except (ValueError, TypeError):
        period_days = 90
    data = _analytics.get_dashboard(cid, profit_period=period_days)
    if not getattr(current_user, 'can_view_carpark_finance', False):
        _strip_analytics_finance(data)
    return jsonify(data)


# ── Individual endpoints ───────────────────────────────────

@carpark_bp.route('/analytics/summary', methods=['GET'])
@login_required
@carpark_required
def analytics_summary():
    """Lightweight inventory summary."""
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    data = _analytics.get_summary(cid)
    if not getattr(current_user, 'can_view_carpark_finance', False):
        _strip_analytics_finance(data)
    return jsonify(data)


@carpark_bp.route('/analytics/kpis', methods=['GET'])
@login_required
@carpark_required
def analytics_kpis():
    """KPI metrics only."""
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    data = _analytics.get_kpis(cid)
    if not getattr(current_user, 'can_view_carpark_finance', False):
        _strip_analytics_finance(data)
    return jsonify(data)


@carpark_bp.route('/analytics/status-breakdown', methods=['GET'])
@login_required
@carpark_required
def analytics_status_breakdown():
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'breakdown': _analytics.get_status_breakdown(cid)})


@carpark_bp.route('/analytics/category-breakdown', methods=['GET'])
@login_required
@carpark_required
def analytics_category_breakdown():
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'breakdown': _analytics.get_category_breakdown(cid)})


@carpark_bp.route('/analytics/aging', methods=['GET'])
@login_required
@carpark_required
def analytics_aging():
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'distribution': _analytics.get_aging_distribution(cid)})


@carpark_bp.route('/analytics/brands', methods=['GET'])
@login_required
@carpark_required
def analytics_brands():
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'brands': _analytics.get_brand_breakdown(cid)})


@carpark_bp.route('/analytics/monthly-sales', methods=['GET'])
@login_required
@carpark_required
def analytics_monthly_sales():
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    months = request.args.get('months', '12', type=str)
    try:
        m = int(months)
    except (ValueError, TypeError):
        m = 12
    data = {'sales': _analytics.get_monthly_sales(cid, m)}
    if not getattr(current_user, 'can_view_carpark_finance', False):
        _strip_analytics_finance(data)
    return jsonify(data)


@carpark_bp.route('/analytics/costs', methods=['GET'])
@login_required
@carpark_finance_required
def analytics_costs():
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'costs': _analytics.get_cost_overview(cid)})


@carpark_bp.route('/analytics/activity', methods=['GET'])
@login_required
@carpark_required
def analytics_activity():
    cid = _acting_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    limit = request.args.get('limit', '15', type=str)
    try:
        lim = min(int(limit), 50)
    except (ValueError, TypeError):
        lim = 15
    return jsonify({'activity': _analytics.get_recent_activity(cid, lim)})
