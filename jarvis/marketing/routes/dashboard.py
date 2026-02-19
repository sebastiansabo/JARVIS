"""Marketing dashboard and report endpoints."""

import logging
from flask import jsonify, request
from flask_login import login_required

from database import get_db, get_cursor, release_db
from marketing import marketing_bp
from marketing.routes.projects import mkt_permission_required

logger = logging.getLogger('jarvis.marketing.routes.dashboard')


@marketing_bp.route('/api/dashboard/summary', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_dashboard_summary():
    """Active project count, total budget, alerts."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT
                COUNT(*) FILTER (WHERE status = 'active') as active_count,
                COUNT(*) FILTER (WHERE status = 'draft') as draft_count,
                COUNT(*) FILTER (WHERE status = 'pending_approval') as pending_count,
                COUNT(*) FILTER (WHERE status = 'completed') as completed_count,
                COUNT(*) as total_count,
                COALESCE(SUM(total_budget) FILTER (WHERE status IN ('active','approved')), 0) as total_active_budget,
                COALESCE(SUM(total_budget), 0) as total_budget
            FROM mkt_projects
            WHERE deleted_at IS NULL
        ''')
        summary = dict(cursor.fetchone())

        # Budget utilization
        cursor.execute('''
            SELECT
                COALESCE(SUM(bl.spent_amount) FILTER (WHERE p.status IN ('active', 'approved')), 0) as active_spent,
                COALESCE(SUM(bl.spent_amount), 0) as all_spent
            FROM mkt_budget_lines bl
            JOIN mkt_projects p ON p.id = bl.project_id
            WHERE p.deleted_at IS NULL
        ''')
        spent_row = cursor.fetchone()

        # Event bonus costs from linked HR events
        cursor.execute('''
            SELECT
                COALESCE(SUM(eb.bonus_net) FILTER (WHERE p.status IN ('active', 'approved')), 0) as active_event_cost,
                COALESCE(SUM(eb.bonus_net), 0) as all_event_cost
            FROM mkt_project_events pe
            JOIN hr.event_bonuses eb ON eb.event_id = pe.event_id
            JOIN mkt_projects p ON p.id = pe.project_id
            WHERE p.deleted_at IS NULL
        ''')
        event_row = cursor.fetchone()

        summary['total_spent'] = float(spent_row['all_spent']) + float(event_row['all_event_cost'])
        summary['total_active_spent'] = float(spent_row['active_spent']) + float(event_row['active_event_cost'])
        summary['total_event_cost'] = float(event_row['all_event_cost'])

        # KPI alerts
        cursor.execute('''
            SELECT COUNT(*) as at_risk_count
            FROM mkt_project_kpis pk
            JOIN mkt_projects p ON p.id = pk.project_id
            WHERE p.deleted_at IS NULL AND p.status = 'active'
              AND pk.status IN ('at_risk', 'behind')
        ''')
        summary['kpi_alerts'] = cursor.fetchone()['at_risk_count']

        return jsonify({'summary': summary})
    finally:
        release_db(conn)


@marketing_bp.route('/api/dashboard/budget-overview', methods=['GET'])
@login_required
@mkt_permission_required('budget', 'view')
def api_budget_overview():
    """Cross-project planned vs spent by channel."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT bl.channel,
                   SUM(bl.planned_amount) as planned,
                   SUM(bl.approved_amount) as approved,
                   SUM(bl.spent_amount) as spent,
                   COUNT(DISTINCT bl.project_id) as project_count
            FROM mkt_budget_lines bl
            JOIN mkt_projects p ON p.id = bl.project_id
            WHERE p.deleted_at IS NULL AND p.status IN ('active', 'approved', 'completed')
            GROUP BY bl.channel
            ORDER BY SUM(bl.planned_amount) DESC
        ''')
        channels = [dict(r) for r in cursor.fetchall()]
        return jsonify({'channels': channels})
    finally:
        release_db(conn)


@marketing_bp.route('/api/dashboard/kpi-scoreboard', methods=['GET'])
@login_required
@mkt_permission_required('kpi', 'view')
def api_kpi_scoreboard():
    """All active projects KPI health."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT p.id as project_id, p.name as project_name,
                   pk.id as kpi_id, kd.name as kpi_name, kd.slug, kd.unit, kd.direction,
                   pk.target_value, pk.current_value, pk.status, pk.channel
            FROM mkt_project_kpis pk
            JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
            JOIN mkt_projects p ON p.id = pk.project_id
            WHERE p.deleted_at IS NULL AND p.status = 'active'
            ORDER BY p.name, kd.sort_order
        ''')
        kpis = [dict(r) for r in cursor.fetchall()]
        return jsonify({'kpis': kpis})
    finally:
        release_db(conn)


@marketing_bp.route('/api/reports/budget-vs-actual', methods=['GET'])
@login_required
@mkt_permission_required('report', 'view')
def api_report_budget_vs_actual():
    """Per-project budget vs actual spend."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT p.id, p.name, p.status, p.total_budget,
                   COALESCE(SUM(bl.spent_amount), 0)
                     + COALESCE((SELECT SUM(eb.bonus_net) FROM mkt_project_events pe JOIN hr.event_bonuses eb ON eb.event_id = pe.event_id WHERE pe.project_id = p.id), 0)
                     as total_spent,
                   COALESCE(SUM(bl.approved_amount), 0) as total_approved,
                   COALESCE((SELECT SUM(eb.bonus_net) FROM mkt_project_events pe JOIN hr.event_bonuses eb ON eb.event_id = pe.event_id WHERE pe.project_id = p.id), 0) as event_cost,
                   CASE WHEN p.total_budget > 0
                        THEN ROUND((COALESCE(SUM(bl.spent_amount), 0)
                          + COALESCE((SELECT SUM(eb.bonus_net) FROM mkt_project_events pe JOIN hr.event_bonuses eb ON eb.event_id = pe.event_id WHERE pe.project_id = p.id), 0))
                          / p.total_budget * 100, 1)
                        ELSE 0 END as utilization_pct
            FROM mkt_projects p
            LEFT JOIN mkt_budget_lines bl ON bl.project_id = p.id
            WHERE p.deleted_at IS NULL AND p.status IN ('active', 'approved', 'completed')
            GROUP BY p.id, p.name, p.status, p.total_budget
            ORDER BY p.name
        ''')
        projects = [dict(r) for r in cursor.fetchall()]
        return jsonify({'projects': projects})
    finally:
        release_db(conn)


@marketing_bp.route('/api/reports/channel-performance', methods=['GET'])
@login_required
@mkt_permission_required('report', 'view')
def api_report_channel_performance():
    """ROI by channel across projects."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT bl.channel,
                   SUM(bl.planned_amount) as total_planned,
                   SUM(bl.spent_amount) as total_spent,
                   COUNT(DISTINCT bl.project_id) as project_count,
                   AVG(CASE WHEN bl.planned_amount > 0
                       THEN bl.spent_amount / bl.planned_amount * 100 ELSE 0 END) as avg_utilization
            FROM mkt_budget_lines bl
            JOIN mkt_projects p ON p.id = bl.project_id
            WHERE p.deleted_at IS NULL
            GROUP BY bl.channel
            ORDER BY SUM(bl.spent_amount) DESC
        ''')
        channels = [dict(r) for r in cursor.fetchall()]
        return jsonify({'channels': channels})
    finally:
        release_db(conn)
