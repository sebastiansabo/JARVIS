"""Mobile dashboard endpoints — aggregated stats and widget data."""
from flask import jsonify, request

from ._shared import mobile_bp, jwt_required, _dashboard_repo, _current_mobile_user, _user_json


# ============== MOBILE DASHBOARD ==============

@mobile_bp.route('/api/mobile/dashboard')
@jwt_required
def api_mobile_dashboard():
    """Aggregated dashboard data for mobile home screen — single request."""
    import logging
    logger = logging.getLogger(__name__)
    user = _current_mobile_user()

    try:
        invoices, revenue, pending_invoices = _dashboard_repo.get_invoice_stats()
        result = {
            'stats': {
                'invoices': invoices,
                'revenue': revenue,
                'pending_invoices': pending_invoices,
                'pending_approvals': _dashboard_repo.get_pending_approvals_count(user.id),
                'pending_signatures': _dashboard_repo.get_pending_signatures_count(user.id),
                'clients': _dashboard_repo.get_client_count(),
            },
            'recent_invoices': [],
            'recent_clients': [],
            'upcoming_events': [],
        }

        recent_invoices = _dashboard_repo.get_recent_invoices()
        for inv in recent_invoices:
            if inv.get('date'):
                inv['date'] = str(inv['date'])
            if inv.get('amount'):
                inv['amount'] = float(inv['amount'])
        result['recent_invoices'] = recent_invoices

        result['recent_clients'] = _dashboard_repo.get_recent_clients()

        upcoming = _dashboard_repo.get_upcoming_events()
        for ev in upcoming:
            if ev.get('date'):
                ev['date'] = str(ev['date'])
            if ev.get('end_date'):
                ev['end_date'] = str(ev['end_date'])
        result['upcoming_events'] = upcoming

        return jsonify(result)
    except Exception as e:
        logger.error('Dashboard endpoint error: %s', e)
        return jsonify({'error': 'An internal error occurred', 'success': False}), 500


# ============== WIDGET DATA (lightweight) ==============

@mobile_bp.route('/api/mobile/widget-data')
@jwt_required
def api_widget_data():
    """Minimal data payload for home screen widgets."""
    from core.checkin.service import CheckinService
    user = _current_mobile_user()

    # Check-in status via existing service
    checkin_svc = CheckinService()
    status = checkin_svc.get_status(user.id)
    punches = status.get('punches', [])
    checked_in = False
    last_punch_time = None
    if punches:
        last = punches[-1]
        checked_in = last.get('direction') == 'IN'
        last_punch_time = last.get('event_datetime')

    pending_count = _dashboard_repo.get_pending_approvals_widget(user.id)
    next_event, next_event_date = _dashboard_repo.get_next_event()

    return jsonify({
        'checked_in': checked_in,
        'last_punch_time': last_punch_time,
        'pending_approvals': pending_count,
        'next_event': next_event,
        'next_event_date': next_event_date,
    })
