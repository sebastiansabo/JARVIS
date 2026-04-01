"""Field Sales / KAM API routes — visits, client enrichment, fleet, manager overview."""

import logging
import threading
from datetime import date, datetime
from functools import wraps

from flask import jsonify, request, g, current_app
from flask_login import current_user

from . import field_sales_bp
from .repositories.visit_repository import VisitRepository
from .repositories.client_fs_repository import ClientFSRepository
from .services import ai_service, segmentation_service
from .notifications import (
    notify_visit_planned, notify_high_value_opportunity,
    notify_risk_flags, notify_high_renewal_score,
    notify_business_client_detected,
)
from core.roles.repositories import PermissionRepository

logger = logging.getLogger('jarvis.field_sales.routes')

_visit_repo = VisitRepository()
_client_repo = ClientFSRepository()
_perm_repo = PermissionRepository()


def _get_current_user():
    """Return the authenticated user from JWT (mobile) or Flask-Login (web)."""
    jwt_user = getattr(request, '_jwt_user', None)
    if jwt_user:
        return jwt_user
    if current_user and current_user.is_authenticated:
        return current_user
    return None


def jwt_or_login_required(f):
    """Accept either JWT Bearer token (mobile) or Flask-Login session (web)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Try JWT first (mobile app sends Authorization: Bearer ...)
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            from core.mobile.routes import _decode_token, _JWT_SECRET
            from core.auth.repositories import UserRepository
            from core.auth.models import User
            token = auth_header[7:]
            payload = _decode_token(token, _JWT_SECRET)
            if not payload or payload.get('type') != 'access':
                return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
            _user_repo = UserRepository()
            user_data = _user_repo.get_by_id(payload['sub'])
            if not user_data or not user_data.get('is_active', True):
                return jsonify({'success': False, 'error': 'User not found or inactive'}), 401
            request._jwt_user = User(user_data)
            return f(*args, **kwargs)
        # Fall back to Flask-Login session
        if current_user and current_user.is_authenticated:
            return f(*args, **kwargs)
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    return decorated


ALLOWED_VISIT_TYPES = frozenset({
    'fleet_review', 'renewal_discussion', 'test_drive_followup',
    'service_followup', 'new_acquisition', 'contract_negotiation',
    'prospecting', 'general',
})
ALLOWED_OUTCOMES = frozenset({
    'completed', 'no_show', 'rescheduled', 'partial',
})


def _safe_error(e):
    """Return a safe error message, never leaking internals."""
    if isinstance(e, (ValueError, KeyError, TypeError)):
        return str(e)
    return 'An internal error occurred'


def _has_permission(module, entity, action):
    """Check if current user has a specific V2 permission. Returns False if no role_id."""
    user = _get_current_user()
    role_id = getattr(user, 'role_id', None) if user else None
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, module, entity, action)
    return bool(perm.get('has_permission'))


def _is_manager():
    """Check if current user has field_sales.team.view permission."""
    return _has_permission('field_sales', 'team', 'view')


# ════════════════════════════════════════════════════════════════
# Permission decorators
# ════════════════════════════════════════════════════════════════

def field_sales_required(f):
    """Require field_sales.module.access V2 permission. Sets g.permission_scope."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        role_id = getattr(user, 'role_id', None)
        if not role_id:
            return jsonify({'success': False, 'error': 'Field Sales access denied'}), 403
        perm = _perm_repo.check_permission_v2(role_id, 'field_sales', 'module', 'access')
        if not perm.get('has_permission'):
            return jsonify({'success': False, 'error': 'Field Sales access denied'}), 403
        g.permission_scope = perm.get('scope', 'all')
        return f(*args, **kwargs)
    return decorated


def field_sales_manager_required(f):
    """Require field_sales.team.view V2 permission for manager endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        role_id = getattr(user, 'role_id', None)
        if not role_id:
            return jsonify({'success': False, 'error': 'Manager access denied'}), 403
        perm = _perm_repo.check_permission_v2(role_id, 'field_sales', 'team', 'view')
        if not perm.get('has_permission'):
            return jsonify({'success': False, 'error': 'Manager access denied'}), 403
        g.permission_scope = perm.get('scope', 'all')
        return f(*args, **kwargs)
    return decorated


def _require_fleet_permission():
    """Check field_sales.fleet.manage. Returns error response tuple or None."""
    if not _has_permission('field_sales', 'fleet', 'manage'):
        return jsonify({'success': False, 'error': 'Fleet management access denied'}), 403
    return None


# ════════════════════════════════════════════════════════════════
# Background task helper
# ════════════════════════════════════════════════════════════════

def _run_background(app, fn):
    """Run fn in a daemon thread with proper Flask app context."""
    def _wrapper():
        with app.app_context():
            try:
                fn()
            except Exception:
                logger.exception('Background task failed')
    threading.Thread(target=_wrapper, daemon=True).start()


# ════════════════════════════════════════════════════════════════
# Visits
# ════════════════════════════════════════════════════════════════

@field_sales_bp.route('/api/field-sales/visits/today', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_visits_today():
    """Get visits for the current KAM for a given date (default: today)."""
    try:
        date_str = request.args.get('date')
        if date_str:
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            date_str = date.today().isoformat()

        visits = _visit_repo.get_by_kam_and_date(_get_current_user().id, date_str)
        return jsonify({'success': True, 'visits': visits, 'date': date_str})
    except Exception as e:
        logger.exception('Error fetching visits for today')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_create_visit():
    """Create a new visit plan."""
    try:
        data = request.get_json(silent=True) or {}

        client_id = data.get('client_id')
        planned_date = data.get('planned_date')

        if not client_id:
            return jsonify({'success': False, 'error': 'client_id is required'}), 400
        if not planned_date:
            return jsonify({'success': False, 'error': 'planned_date is required'}), 400

        try:
            client_id = int(client_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'client_id must be an integer'}), 400

        try:
            datetime.strptime(planned_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        visit_type = data.get('visit_type', 'general')
        if visit_type not in ALLOWED_VISIT_TYPES:
            return jsonify({'success': False, 'error': f'Invalid visit_type. Allowed: {", ".join(sorted(ALLOWED_VISIT_TYPES))}'}), 400

        # Verify client exists
        client = _client_repo.query_one(
            'SELECT id FROM crm_clients WHERE id = %s', (client_id,)
        )
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        visit_data = {
            'kam_id': _get_current_user().id,
            'client_id': client_id,
            'planned_date': planned_date,
            'planned_time': data.get('planned_time'),
            'visit_type': visit_type,
            'goals': data.get('goals'),
        }

        visit = _visit_repo.create(visit_data)
        visit_id = visit['id']

        # Fetch client name for notifications
        client = _client_repo.query_one(
            'SELECT display_name FROM crm_clients WHERE id = %s', (client_id,)
        )
        visit['client_name'] = client.get('display_name', 'Client') if client else 'Client'

        # Generate AI brief in background with proper app context
        app = current_app._get_current_object()
        kam_name = getattr(current_user, 'name', None) or 'KAM'

        def _generate_brief():
            context = _visit_repo.get_client_context(visit_id)
            if context:
                brief = ai_service.generate_visit_brief(context)
                if brief:
                    _visit_repo.update_brief(visit_id, brief)

        _run_background(app, _generate_brief)

        # Notify manager about planned visit (fire-and-forget in background)
        _visit_notification = dict(visit)
        _visit_notification['kam_id'] = _get_current_user().id

        def _send_planned_notification():
            notify_visit_planned(_visit_notification, kam_name=kam_name)

        _run_background(app, _send_planned_notification)

        return jsonify({'success': True, 'visit': visit}), 201
    except Exception as e:
        logger.exception('Error creating visit')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_visit_detail(visit_id):
    """Get full visit details including notes."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR check: KAM sees own visits, managers see all
        if visit['kam_id'] != _get_current_user().id and not _is_manager():
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        return jsonify({'success': True, 'visit': visit})
    except Exception as e:
        logger.exception('Error fetching visit detail')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/checkin', methods=['PUT', 'POST'])
@jwt_or_login_required
@field_sales_required
def api_visit_checkin(visit_id):
    """Check in to a visit with optional GPS coordinates."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR: only own visits
        if visit['kam_id'] != _get_current_user().id:
            return jsonify({'success': False, 'error': 'Can only check in to your own visits'}), 403

        if visit['status'] not in ('planned', 'in_progress'):
            return jsonify({'success': False, 'error': f'Cannot check in to a {visit["status"]} visit'}), 400

        data = request.get_json(silent=True) or {}
        lat = data.get('lat')
        lng = data.get('lng')

        # Validate GPS coordinates if provided
        if lat is not None:
            try:
                lat = float(lat)
                if not (-90 <= lat <= 90):
                    return jsonify({'success': False, 'error': 'lat must be between -90 and 90'}), 400
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'lat must be a number'}), 400
        if lng is not None:
            try:
                lng = float(lng)
                if not (-180 <= lng <= 180):
                    return jsonify({'success': False, 'error': 'lng must be between -180 and 180'}), 400
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'lng must be a number'}), 400

        updated = _visit_repo.checkin(visit_id, lat=lat, lng=lng)
        return jsonify({'success': True, 'visit': updated})
    except Exception as e:
        logger.exception('Error checking in to visit')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/checkout', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_visit_checkout(visit_id):
    """Check out from a visit (complete without note)."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        if visit['kam_id'] != _get_current_user().id:
            return jsonify({'success': False, 'error': 'Can only check out from your own visits'}), 403

        if visit['status'] != 'in_progress':
            return jsonify({'success': False, 'error': 'Can only check out from in_progress visits'}), 400

        data = request.get_json(silent=True) or {}
        outcome = data.get('outcome', 'completed')
        if outcome not in ALLOWED_OUTCOMES:
            return jsonify({'success': False, 'error': f'Invalid outcome. Allowed: {", ".join(sorted(ALLOWED_OUTCOMES))}'}), 400

        updated = _visit_repo.complete(visit_id, outcome)
        return jsonify({'success': True, 'visit': updated})
    except Exception as e:
        logger.exception('Error checking out from visit')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/note', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_visit_note(visit_id):
    """Submit a visit note. Structures via AI and completes the visit."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR: only own visits
        if visit['kam_id'] != _get_current_user().id:
            return jsonify({'success': False, 'error': 'Can only add notes to your own visits'}), 403

        data = request.get_json(silent=True) or {}
        raw_note = data.get('raw_note', '').strip()
        outcome = data.get('outcome', 'completed')

        if not raw_note:
            return jsonify({'success': False, 'error': 'raw_note is required'}), 400
        if len(raw_note) > 10000:
            return jsonify({'success': False, 'error': 'raw_note must be under 10000 characters'}), 400
        if outcome not in ALLOWED_OUTCOMES:
            return jsonify({'success': False, 'error': f'Invalid outcome. Allowed: {", ".join(sorted(ALLOWED_OUTCOMES))}'}), 400

        # 1. Save raw note first
        note = _visit_repo.add_note(visit_id, raw_note)

        # 2. Structure via AI (synchronous — user waits)
        structured = None
        try:
            client_context = _visit_repo.get_client_context(visit_id)
            structured = ai_service.structure_visit_note(raw_note, client_context)
        except Exception:
            logger.exception('AI structuring failed for visit %s', visit_id)

        # 3. Save structured note
        if structured and not structured.get('error'):
            _visit_repo.update_note_structured(note['id'], structured)
            note['structured_note'] = structured
            note['structured_at'] = datetime.now().isoformat()

        # 4. Complete visit
        _visit_repo.complete(visit_id, outcome)

        # 5. Background: recompute renewal score + send notifications
        client_id = visit['client_id']
        client_name = visit.get('client_name', 'Client')
        app = current_app._get_current_object()
        kam_name = getattr(current_user, 'name', None) or 'KAM'
        _visit_copy = dict(visit)
        _structured_copy = dict(structured) if structured else None

        def _post_note_tasks():
            # Recompute renewal score and trigger threshold notification
            profile = _client_repo.get_or_create_profile(client_id)
            previous_score = profile.get('renewal_score') or 0
            new_score = segmentation_service.compute_renewal_score(client_id, _client_repo)
            _client_repo.update_renewal_score(client_id, new_score)

            assigned_kam_id = profile.get('assigned_kam_id') or _visit_copy.get('kam_id')
            notify_high_renewal_score(
                client_id, client_name, new_score, previous_score,
                assigned_kam_id=assigned_kam_id,
            )

            # High value opportunity notification
            notify_high_value_opportunity(_visit_copy, _structured_copy, kam_name=kam_name)

            # Risk flags notification
            notify_risk_flags(_visit_copy, _structured_copy, kam_name=kam_name)

        _run_background(app, _post_note_tasks)

        return jsonify({
            'success': True,
            'note': note,
            'structured_note': structured,
            'visit_status': 'completed',
        })
    except Exception as e:
        logger.exception('Error submitting visit note')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/brief', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_visit_brief(visit_id):
    """Get or regenerate the AI brief for a visit."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR: own visits or manager
        if visit['kam_id'] != _get_current_user().id and not _is_manager():
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        refresh = request.args.get('refresh', '').lower() in ('1', 'true')

        if visit.get('ai_brief') and not refresh:
            return jsonify({
                'success': True,
                'brief': visit['ai_brief'],
                'generated_at': visit.get('ai_brief_generated_at'),
            })

        # Generate fresh brief
        context = _visit_repo.get_client_context(visit_id)
        if not context:
            return jsonify({'success': False, 'error': 'Could not build client context'}), 500

        brief = ai_service.generate_visit_brief(context)
        if brief:
            _visit_repo.update_brief(visit_id, brief)

        return jsonify({
            'success': True,
            'brief': brief or '',
            'generated_at': datetime.now().isoformat() if brief else None,
        })
    except Exception as e:
        logger.exception('Error generating visit brief')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


# ════════════════════════════════════════════════════════════════
# Clients
# ════════════════════════════════════════════════════════════════

@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/360', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_client_360(client_id):
    """Get comprehensive 360-degree client view."""
    try:
        data = _client_repo.get_360(client_id)
        if not data.get('client'):
            return jsonify({'success': False, 'error': 'Client not found'}), 404
        return jsonify({'success': True, **data})
    except Exception as e:
        logger.exception('Error fetching client 360')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/fiscal', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_client_fiscal(client_id):
    """Get ANAF fiscal data for a client. Requires field_sales.fiscal.view."""
    try:
        if not _has_permission('field_sales', 'fiscal', 'view'):
            return jsonify({'success': False, 'error': 'Fiscal data access denied'}), 403

        profile = _client_repo.get_or_create_profile(client_id)
        cui = profile.get('cui')

        if not cui:
            return jsonify({'success': True, 'fiscal': None, 'message': 'No CUI on profile'})

        anaf_data = segmentation_service.get_or_refresh_anaf(client_id, cui, _client_repo)
        return jsonify({
            'success': True,
            'fiscal': anaf_data,
            'cui': cui,
            'fetched_at': profile.get('anaf_fetched_at'),
        })
    except Exception as e:
        logger.exception('Error fetching fiscal data')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/refresh-fiscal', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_client_refresh_fiscal(client_id):
    """Force-refresh ANAF fiscal data for a client. Requires field_sales.fiscal.view."""
    try:
        if not _has_permission('field_sales', 'fiscal', 'view'):
            return jsonify({'success': False, 'error': 'Fiscal data access denied'}), 403

        profile = _client_repo.get_or_create_profile(client_id)
        cui = profile.get('cui')

        if not cui:
            return jsonify({'success': True, 'fiscal': None, 'message': 'No CUI on profile'})

        # Force refresh by clearing the cache timestamp
        _client_repo.update_profile(client_id, {'anaf_fetched_at': None})
        anaf_data = segmentation_service.get_or_refresh_anaf(client_id, cui, _client_repo)
        return jsonify({
            'success': True,
            'fiscal': anaf_data,
            'cui': cui,
        })
    except Exception as e:
        logger.exception('Error refreshing fiscal data')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/enrich', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_client_enrich(client_id):
    """Trigger full client profile enrichment."""
    try:
        data = request.get_json(silent=True) or {}

        client = _client_repo.query_one(
            'SELECT id, display_name, company_name FROM crm_clients WHERE id = %s',
            (client_id,)
        )
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        company_name = data.get('company_name') or client.get('company_name') or client.get('display_name')
        cui = data.get('cui')

        if not cui:
            profile = _client_repo.get_or_create_profile(client_id)
            cui = profile.get('cui')

        # Check previous client_type before enrichment
        profile_before = _client_repo.get_or_create_profile(client_id)
        was_business = profile_before.get('client_type') == 'business'

        updated = segmentation_service.enrich_client_profile(
            client_id, company_name, cui, _client_repo
        )

        # Notify if client was newly identified as business
        if not was_business and updated and updated.get('client_type') == 'business':
            app = current_app._get_current_object()

            def _send_business_notification():
                notify_business_client_detected(
                    client_id,
                    client.get('display_name') or client.get('company_name') or 'Client',
                    updated,
                    triggered_by_user_id=_get_current_user().id,
                )

            _run_background(app, _send_business_notification)

        return jsonify({'success': True, 'profile': updated})
    except Exception as e:
        logger.exception('Error enriching client')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/search', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_client_search():
    """Search clients by name, company, nr_reg, or CUI."""
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify({'success': False, 'error': 'Search query must be at least 2 characters'}), 400

        limit = request.args.get('limit', 20, type=int)
        limit = min(max(limit, 1), 100)

        results = _client_repo.search_clients(query, limit=limit)
        return jsonify({'success': True, 'clients': results, 'count': len(results)})
    except Exception as e:
        logger.exception('Error searching clients')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


# ════════════════════════════════════════════════════════════════
# Fleet
# ════════════════════════════════════════════════════════════════

@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/fleet', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_client_fleet(client_id):
    """Get fleet vehicles for a client."""
    try:
        fleet = _client_repo.get_fleet(client_id)
        return jsonify({'success': True, 'fleet': fleet})
    except Exception as e:
        logger.exception('Error fetching fleet')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/fleet', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_add_fleet_vehicle(client_id):
    """Add a vehicle to a client's fleet. Requires field_sales.fleet.manage."""
    try:
        perm_err = _require_fleet_permission()
        if perm_err:
            return perm_err

        # Verify client exists
        client = _client_repo.query_one(
            'SELECT id FROM crm_clients WHERE id = %s', (client_id,)
        )
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        data = request.get_json(silent=True) or {}
        data['client_id'] = client_id

        vehicle = _client_repo.upsert_fleet_vehicle(data)

        # Update fleet_size on profile
        try:
            fleet = _client_repo.get_fleet(client_id)
            active_count = len([v for v in fleet if v.get('status') == 'active']) if fleet else 0
            _client_repo.update_profile(client_id, {'fleet_size': active_count})
        except Exception:
            pass

        return jsonify({'success': True, 'vehicle': vehicle}), 201
    except Exception as e:
        logger.exception('Error adding fleet vehicle')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/fleet/<int:vehicle_id>', methods=['PUT'])
@jwt_or_login_required
@field_sales_required
def api_update_fleet_vehicle(vehicle_id):
    """Update a fleet vehicle. Requires field_sales.fleet.manage."""
    try:
        perm_err = _require_fleet_permission()
        if perm_err:
            return perm_err

        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        vehicle = _client_repo.update_fleet_vehicle(vehicle_id, data)
        if not vehicle:
            return jsonify({'success': False, 'error': 'Vehicle not found or no editable fields'}), 404

        # Update fleet_size on profile
        try:
            client_id = vehicle.get('client_id')
            if client_id:
                fleet = _client_repo.get_fleet(client_id)
                active_count = len([v for v in fleet if v.get('status') == 'active']) if fleet else 0
                _client_repo.update_profile(client_id, {'fleet_size': active_count})
        except Exception:
            pass

        return jsonify({'success': True, 'vehicle': vehicle})
    except Exception as e:
        logger.exception('Error updating fleet vehicle')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


# ════════════════════════════════════════════════════════════════
# Manager Overview
# ════════════════════════════════════════════════════════════════

@field_sales_bp.route('/api/field-sales/manager/overview', methods=['GET'])
@jwt_or_login_required
@field_sales_manager_required
def api_manager_overview():
    """Get manager overview of all KAM visits in a date range."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        if not date_from or not date_to:
            return jsonify({'success': False, 'error': 'date_from and date_to are required'}), 400

        try:
            datetime.strptime(date_from, '%Y-%m-%d')
            datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        kam_id = request.args.get('kam_id', type=int)

        visits = _visit_repo.get_team_visits(date_from, date_to, kam_id=kam_id)

        # Compute summary stats
        total = len(visits)
        by_status = {}
        by_kam = {}
        for v in visits:
            st = v.get('status', 'unknown')
            by_status[st] = by_status.get(st, 0) + 1

            kam_name = v.get('kam_name', 'Unknown')
            if kam_name not in by_kam:
                by_kam[kam_name] = {'total': 0, 'completed': 0, 'in_progress': 0, 'planned': 0}
            by_kam[kam_name]['total'] += 1
            if st in by_kam[kam_name]:
                by_kam[kam_name][st] += 1

        return jsonify({
            'success': True,
            'visits': visits,
            'summary': {
                'total': total,
                'by_status': by_status,
                'by_kam': by_kam,
            },
        })
    except Exception as e:
        logger.exception('Error fetching manager overview')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/manager/clients', methods=['GET'])
@jwt_or_login_required
@field_sales_manager_required
def api_manager_clients():
    """Get clients with profiles for manager view, with filtering."""
    try:
        priority = request.args.get('priority')
        country_code = request.args.get('country_code')
        min_renewal_score = request.args.get('min_renewal_score', type=int)
        assigned_kam_id = request.args.get('assigned_kam_id', type=int)
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        if priority and priority not in ('low', 'medium', 'high'):
            return jsonify({'success': False, 'error': 'Invalid priority. Use low/medium/high'}), 400

        clients, total = _client_repo.get_managed_clients(
            priority=priority,
            country_code=country_code,
            min_renewal_score=min_renewal_score,
            assigned_kam_id=assigned_kam_id,
            limit=min(max(limit, 1), 200),
            offset=max(offset, 0),
        )

        return jsonify({
            'success': True,
            'clients': clients,
            'total': total,
        })
    except Exception as e:
        logger.exception('Error fetching manager clients')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
