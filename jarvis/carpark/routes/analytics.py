"""Analytics API routes — Dashboard, KPIs, and aggregated stats."""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.routes.vehicles import carpark_required
from carpark.services.analytics_service import AnalyticsService

logger = logging.getLogger('jarvis.carpark.analytics')

_analytics = AnalyticsService()


def _user_company_id():
    return getattr(current_user, 'company_id', None)


# ── Full dashboard ─────────────────────────────────────────

@carpark_bp.route('/analytics/dashboard', methods=['GET'])
@login_required
@carpark_required
def analytics_dashboard():
    """Full dashboard payload — single endpoint for the frontend."""
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    period = request.args.get('period', '90', type=str)
    try:
        period_days = int(period)
    except (ValueError, TypeError):
        period_days = 90
    data = _analytics.get_dashboard(cid, profit_period=period_days)
    return jsonify(data)


# ── Individual endpoints ───────────────────────────────────

@carpark_bp.route('/analytics/summary', methods=['GET'])
@login_required
@carpark_required
def analytics_summary():
    """Lightweight inventory summary."""
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify(_analytics.get_summary(cid))


@carpark_bp.route('/analytics/kpis', methods=['GET'])
@login_required
@carpark_required
def analytics_kpis():
    """KPI metrics only."""
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify(_analytics.get_kpis(cid))


@carpark_bp.route('/analytics/status-breakdown', methods=['GET'])
@login_required
@carpark_required
def analytics_status_breakdown():
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'breakdown': _analytics.get_status_breakdown(cid)})


@carpark_bp.route('/analytics/category-breakdown', methods=['GET'])
@login_required
@carpark_required
def analytics_category_breakdown():
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'breakdown': _analytics.get_category_breakdown(cid)})


@carpark_bp.route('/analytics/aging', methods=['GET'])
@login_required
@carpark_required
def analytics_aging():
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'distribution': _analytics.get_aging_distribution(cid)})


@carpark_bp.route('/analytics/brands', methods=['GET'])
@login_required
@carpark_required
def analytics_brands():
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'brands': _analytics.get_brand_breakdown(cid)})


@carpark_bp.route('/analytics/monthly-sales', methods=['GET'])
@login_required
@carpark_required
def analytics_monthly_sales():
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    months = request.args.get('months', '12', type=str)
    try:
        m = int(months)
    except (ValueError, TypeError):
        m = 12
    return jsonify({'sales': _analytics.get_monthly_sales(cid, m)})


@carpark_bp.route('/analytics/costs', methods=['GET'])
@login_required
@carpark_required
def analytics_costs():
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    return jsonify({'costs': _analytics.get_cost_overview(cid)})


@carpark_bp.route('/analytics/activity', methods=['GET'])
@login_required
@carpark_required
def analytics_activity():
    cid = _user_company_id()
    if not cid:
        return jsonify({'success': False, 'error': 'No company assigned'}), 400
    limit = request.args.get('limit', '15', type=str)
    try:
        lim = min(int(limit), 50)
    except (ValueError, TypeError):
        lim = 15
    return jsonify({'activity': _analytics.get_recent_activity(cid, lim)})
