"""JARVIS Profile Page Routes.

API endpoints and page routes for the user profile page.
Uses user data directly (organizational fields stored in users table).
"""
from flask import jsonify, request, redirect
from flask_login import login_required, current_user

from . import profile_bp
from core.profile.repositories import ProfileRepository
from core.auth.repositories.user_repository import UserRepository
from core.utils.api_helpers import safe_error_response

_profile_repo = ProfileRepository()
_user_repo = UserRepository()


# ============== Page Route ==============

@profile_bp.route('/')
@login_required
def profile_page():
    """Redirect to React profile page."""
    return redirect('/app/profile')


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
            'cnp': getattr(current_user, 'cnp', None),
            'birthdate': str(current_user.birthdate) if getattr(current_user, 'birthdate', None) else None,
            'position': getattr(current_user, 'position', None),
            'contract_work_date': str(current_user.contract_work_date) if getattr(current_user, 'contract_work_date', None) else None,
        }

        # Get invoice summary using user's email
        invoices_summary = _profile_repo.get_user_invoices_summary(current_user.email)
        activity_count = _profile_repo.get_user_activity_count(current_user.id)

        # Get HR events summary for this user
        hr_events_summary = _profile_repo.get_user_event_bonuses_summary(current_user.id)

        return jsonify({
            'user': user_info,
            'invoices': invoices_summary,
            'hr_events': hr_events_summary,
            'notifications': {'total': 0, 'sent': 0, 'failed': 0},
            'activity': {'total_events': activity_count},
        })
    except Exception as e:
        return safe_error_response(e)


@profile_bp.route('/api/update', methods=['PUT'])
@login_required
def api_profile_update():
    """Update current user's profile details."""
    try:
        data = request.get_json() or {}

        # Only allow users to edit specific personal fields
        allowed_fields = {'phone', 'cnp', 'birthdate', 'position', 'contract_work_date'}
        update_kwargs = {}
        for field in allowed_fields:
            if field in data:
                val = data[field]
                # Allow empty string to clear a field
                if val == '':
                    val = None
                update_kwargs[field] = val

        if not update_kwargs:
            return jsonify({'error': 'No valid fields to update'}), 400

        _user_repo.update(current_user.id, **update_kwargs)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


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
        invoices = _profile_repo.get_user_invoices_by_responsible_name(
            user_email=current_user.email,
            status=status if status else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            search=search if search else None,
            limit=per_page,
            offset=offset,
        )

        total = _profile_repo.get_user_invoices_count(
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
        return safe_error_response(e)


@profile_bp.route('/api/hr-events')
@login_required
def api_profile_hr_events():
    """Get HR event bonuses for current user."""
    try:
        # Query params
        year = request.args.get('year', '', type=str)
        month = request.args.get('month', '', type=str)
        search = request.args.get('search', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        # Validate
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 1000:
            per_page = 50

        offset = (page - 1) * per_page

        # Convert year/month to int if provided
        year_int = int(year) if year else None
        month_int = int(month) if month else None

        # Get bonuses for current user
        bonuses = _profile_repo.get_user_event_bonuses(
            user_id=current_user.id,
            year=year_int,
            month=month_int,
            search=search if search else None,
            limit=per_page,
            offset=offset,
        )

        total = _profile_repo.get_user_event_bonuses_count(
            user_id=current_user.id,
            year=year_int,
            month=month_int,
            search=search if search else None,
        )

        return jsonify({
            'bonuses': bonuses,
            'total': total,
            'page': page,
            'per_page': per_page,
        })
    except Exception as e:
        return safe_error_response(e)


@profile_bp.route('/api/pontaje')
@login_required
def api_profile_pontaje():
    """Get pontaje (attendance) data for the current user from BioStar."""
    try:
        from core.connectors.biostar.services import BioStarSyncService
        service = BioStarSyncService()

        # Find BioStar employee mapped to current user
        employee = service.repo.query_one(
            '''SELECT be.*, u.name AS mapped_jarvis_user_name, u.email AS mapped_jarvis_user_email
               FROM biostar_employees be
               LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
               WHERE be.mapped_jarvis_user_id = %s AND be.status = 'active'
            ''', (current_user.id,)
        )
        if not employee:
            return jsonify({'success': True, 'mapped': False, 'employee': None,
                            'history': [], 'today_punches': []})

        biostar_id = employee['biostar_user_id']
        start = request.args.get('start', '')
        end = request.args.get('end', '')
        if not start or not end:
            from datetime import datetime, timedelta
            end = datetime.now().strftime('%Y-%m-%d')
            start = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

        today = __import__('datetime').datetime.now().strftime('%Y-%m-%d')

        history = service.get_employee_daily_history(biostar_id, start, end)
        today_punches = service.get_employee_punches(biostar_id, today)

        return jsonify({
            'success': True,
            'mapped': True,
            'employee': {
                'biostar_user_id': employee['biostar_user_id'],
                'name': employee['name'],
                'lunch_break_minutes': employee.get('lunch_break_minutes', 60),
                'working_hours': employee.get('working_hours', 8),
                'schedule_start': employee.get('schedule_start'),
                'schedule_end': employee.get('schedule_end'),
                'user_group_name': employee.get('user_group_name'),
            },
            'history': history,
            'today_punches': today_punches,
        })
    except Exception as e:
        return safe_error_response(e)


@profile_bp.route('/api/team-pontaje')
@login_required
def api_profile_team_pontaje():
    """Get team pontaje (attendance) data for employees managed by current user.

    mode=daily (default): today's per-employee punch summary
    mode=range: aggregated summary over start..end
    """
    try:
        from datetime import datetime, timedelta
        from hr.events.database import get_managed_employee_ids, is_manager
        from core.connectors.biostar.services import BioStarSyncService

        if not is_manager(current_user.id):
            return jsonify({'success': True, 'is_manager': False, 'mode': 'daily',
                            'summary': [], 'date': datetime.now().strftime('%Y-%m-%d')})

        managed_ids = get_managed_employee_ids(current_user.id)
        if not managed_ids:
            return jsonify({'success': True, 'is_manager': True, 'mode': 'daily',
                            'summary': [], 'date': datetime.now().strftime('%Y-%m-%d')})

        service = BioStarSyncService()
        mode = request.args.get('mode', 'daily')

        if mode == 'range':
            start = request.args.get('start', '')
            end = request.args.get('end', '')
            if not start or not end:
                end = datetime.now().strftime('%Y-%m-%d')
                start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            summary = service.repo.get_range_summary(start, end, jarvis_user_ids=managed_ids)
            return jsonify({
                'success': True,
                'is_manager': True,
                'mode': 'range',
                'summary': summary,
                'start': start,
                'end': end,
            })
        else:
            date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
            summary = service.repo.get_daily_summary(date_str, jarvis_user_ids=managed_ids)
            return jsonify({
                'success': True,
                'is_manager': True,
                'mode': 'daily',
                'summary': summary,
                'date': date_str,
            })
    except Exception as e:
        return safe_error_response(e)


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
        return safe_error_response(e)


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

        events = _profile_repo.get_user_activity(
            user_id=current_user.id,
            event_type=event_type if event_type else None,
            limit=per_page,
            offset=offset,
        )

        total = _profile_repo.get_user_activity_count(current_user.id)

        return jsonify({
            'events': events,
            'total': total,
            'page': page,
            'per_page': per_page,
        })
    except Exception as e:
        return safe_error_response(e)
