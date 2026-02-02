"""JARVIS Profile Page Routes.

API endpoints and page routes for the user profile page.
Uses user data directly (organizational fields stored in users table).
"""
import traceback
from flask import render_template, jsonify, request
from flask_login import login_required, current_user

from . import profile_bp
from database import (
    get_user_invoices_by_responsible_name,
    get_user_invoices_count,
    get_user_invoices_summary,
    get_user_activity,
    get_user_activity_count,
)


# ============== Page Route ==============

@profile_bp.route('/')
@login_required
def profile_page():
    """Render the profile page."""
    return render_template('core/profile.html')


# ============== API Endpoints ==============

@profile_bp.route('/api/summary')
@login_required
def api_profile_summary():
    """Get summary stats for current user's profile."""
    try:
        # Build user info from current_user (includes org fields from users table)
        user_info = {
            'id': current_user.id,
            'name': current_user.name,
            'email': current_user.email,
            'phone': getattr(current_user, 'phone', None),
            'role': getattr(current_user, 'role_name', None),
            'company': getattr(current_user, 'company', None),
            'brand': getattr(current_user, 'brand', None),
            'department': getattr(current_user, 'department', None),
            'subdepartment': getattr(current_user, 'subdepartment', None),
        }

        # Get invoice summary using user's email
        invoices_summary = get_user_invoices_summary(current_user.email)
        activity_count = get_user_activity_count(current_user.id)

        return jsonify({
            'user': user_info,
            'invoices': invoices_summary,
            'hr_events': {'total_bonuses': 0, 'total_amount': 0, 'events_count': 0},
            'notifications': {'total': 0, 'sent': 0, 'failed': 0},
            'activity': {'total_events': activity_count},
        })
    except Exception as e:
        print(f"Profile summary API error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@profile_bp.route('/api/invoices')
@login_required
def api_profile_invoices():
    """Get invoices for current user (as responsible)."""
    try:
        # Query params
        status = request.args.get('status', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        search = request.args.get('search', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        # Validate
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 1000:
            per_page = 50

        offset = (page - 1) * per_page

        # Get invoices using user's email (finds user, matches their name to allocation.responsible)
        invoices = get_user_invoices_by_responsible_name(
            user_email=current_user.email,
            status=status if status else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            search=search if search else None,
            limit=per_page,
            offset=offset,
        )

        total = get_user_invoices_count(
            user_email=current_user.email,
            status=status if status else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            search=search if search else None,
        )

        return jsonify({
            'invoices': invoices,
            'total': total,
            'page': page,
            'per_page': per_page,
        })
    except Exception as e:
        print(f"Profile invoices API error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@profile_bp.route('/api/hr-events')
@login_required
def api_profile_hr_events():
    """Get HR event bonuses for current user."""
    try:
        # HR events functionality - placeholder for now
        # TODO: Implement when HR module is updated to use users table
        return jsonify({
            'bonuses': [],
            'total': 0,
            'page': 1,
            'per_page': 20,
        })
    except Exception as e:
        print(f"Profile HR events API error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@profile_bp.route('/api/notifications')
@login_required
def api_profile_notifications():
    """Get notifications sent to current user."""
    try:
        # Notifications functionality - placeholder for now
        # TODO: Implement when notification system is updated to use users table
        return jsonify({
            'notifications': [],
            'total': 0,
            'page': 1,
            'per_page': 20,
        })
    except Exception as e:
        print(f"Profile notifications API error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@profile_bp.route('/api/activity')
@login_required
def api_profile_activity():
    """Get activity log for current user."""
    try:
        # Query params
        event_type = request.args.get('event_type', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 50

        offset = (page - 1) * per_page

        events = get_user_activity(
            user_id=current_user.id,
            event_type=event_type if event_type else None,
            limit=per_page,
            offset=offset,
        )

        total = get_user_activity_count(current_user.id)

        return jsonify({
            'events': events,
            'total': total,
            'page': page,
            'per_page': per_page,
        })
    except Exception as e:
        print(f"Profile activity API error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
