"""Auth module API routes.

User management, employee management, password management, and event log routes.
Note: Page routes (login, logout, forgot-password, reset-password) and basic auth
API routes (current-user, change-password, heartbeat, online-users) remain in app.py
until template url_for references are migrated.
"""
from flask import jsonify, request
from flask_login import login_required, current_user

from . import auth_bp
from .repositories import UserRepository, EventRepository
from core.utils.api_helpers import admin_required, safe_error_response

_user_repo = UserRepository()
_event_repo = EventRepository()


# ============== USER MANAGEMENT ==============

@auth_bp.route('/api/users', methods=['GET'])
@login_required
def api_get_users():
    """Get all users with role information."""
    users = _user_repo.get_all()
    return jsonify(users)


@auth_bp.route('/api/users/<int:user_id>', methods=['GET'])
@login_required
def api_get_user(user_id):
    """Get a specific user with role information."""
    user = _user_repo.get_by_id(user_id)
    if user:
        return jsonify(user)
    return jsonify({'error': 'User not found'}), 404


@auth_bp.route('/api/users', methods=['POST'])
@admin_required
def api_create_user():
    """Create a new user."""
    data = request.get_json()
    name = data.get('name', '').strip() if data.get('name') else ''
    email = data.get('email', '').strip() if data.get('email') else ''
    phone = data.get('phone', '').strip() if data.get('phone') else ''
    password = data.get('password', '').strip() if data.get('password') else ''

    if not name or not email:
        return jsonify({'error': 'Name and email are required'}), 400

    try:
        user_id = _user_repo.save(
            name=name,
            email=email,
            phone=phone if phone else None,
            role_id=data.get('role_id'),
            is_active=data.get('is_active', True)
        )
        if password:
            _user_repo.update_password(user_id, password)
        return jsonify({'success': True, 'id': user_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@auth_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def api_update_user(user_id):
    """Update a user."""
    data = request.get_json()
    try:
        updated = _user_repo.update(
            user_id=user_id,
            name=data.get('name'),
            email=data.get('email'),
            phone=data.get('phone'),
            role_id=data.get('role_id'),
            is_active=data.get('is_active'),
            notify_on_allocation=data.get('notify_on_allocation'),
            company=data.get('company'),
            brand=data.get('brand'),
            department=data.get('department'),
            subdepartment=data.get('subdepartment')
        )
        if updated:
            password = data.get('password', '').strip() if data.get('password') else ''
            if password:
                _user_repo.update_password(user_id, password)
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'User not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@auth_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user(user_id):
    """Delete a user."""
    if _user_repo.delete(user_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'User not found'}), 404


@auth_bp.route('/api/users/bulk-delete', methods=['POST'])
@admin_required
def api_bulk_delete_users():
    """Delete multiple users."""
    data = request.get_json()
    user_ids = data.get('ids', [])
    if not user_ids:
        return jsonify({'success': False, 'error': 'No IDs provided'}), 400
    try:
        user_ids = [int(id) for id in user_ids]
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid ID format'}), 400
    deleted_count = _user_repo.delete_bulk(user_ids)
    return jsonify({'success': True, 'deleted': deleted_count})


# ============== EMPLOYEE MANAGEMENT (legacy alias) ==============

@auth_bp.route('/api/employees', methods=['GET'])
@login_required
def api_get_employees():
    """Get all users as employees."""
    users = _user_repo.get_all()
    for user in users:
        user['departments'] = user.get('department')
    return jsonify(users)


@auth_bp.route('/api/employees/<int:employee_id>', methods=['GET'])
@login_required
def api_get_employee(employee_id):
    """Get a specific user as employee."""
    user = _user_repo.get_by_id(employee_id)
    if user:
        user['departments'] = user.get('department')
        return jsonify(user)
    return jsonify({'error': 'Employee not found'}), 404


@auth_bp.route('/api/employees', methods=['POST'])
@admin_required
def api_create_employee():
    """Create a new user/employee."""
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip() if data.get('email') else None
    phone = data.get('phone', '').strip() if data.get('phone') else None
    department = data.get('department') or data.get('departments')
    department = department.strip() if department else None
    subdepartment = data.get('subdepartment', '').strip() if data.get('subdepartment') else None
    company = data.get('company', '').strip() if data.get('company') else None
    brand = data.get('brand', '').strip() if data.get('brand') else None

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    try:
        user_id = _user_repo.save(
            name=name,
            email=email,
            phone=phone,
            department=department,
            subdepartment=subdepartment,
            company=company,
            brand=brand,
            notify_on_allocation=data.get('notify_on_allocation', True),
            is_active=data.get('is_active', True)
        )
        return jsonify({'success': True, 'id': user_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@auth_bp.route('/api/employees/<int:employee_id>', methods=['PUT'])
@admin_required
def api_update_employee(employee_id):
    """Update a user/employee."""
    data = request.get_json()
    department = data.get('department') if data.get('department') is not None else data.get('departments')
    try:
        updated = _user_repo.update(
            user_id=employee_id,
            name=data.get('name'),
            email=data.get('email'),
            phone=data.get('phone'),
            department=department,
            subdepartment=data.get('subdepartment'),
            company=data.get('company'),
            brand=data.get('brand'),
            notify_on_allocation=data.get('notify_on_allocation'),
            is_active=data.get('is_active')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Employee not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@auth_bp.route('/api/employees/<int:employee_id>', methods=['DELETE'])
@admin_required
def api_delete_employee(employee_id):
    """Delete a user/employee."""
    if _user_repo.delete(employee_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Employee not found'}), 404


# ============== PASSWORD MANAGEMENT ==============

@auth_bp.route('/api/auth/update-profile', methods=['POST'])
@login_required
def api_update_profile():
    """Update current user's profile (name, phone)."""
    data = request.get_json()
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip() or None

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    if len(name) < 2:
        return jsonify({'success': False, 'error': 'Name must be at least 2 characters'}), 400

    _user_repo.update(current_user.id, name=name, phone=phone)
    from core.auth.repositories import EventRepository
    EventRepository().log_event('profile_updated', event_description=f'User updated their profile: name={name}')
    return jsonify({'success': True, 'message': 'Profile updated successfully', 'name': name})


@auth_bp.route('/api/users/<int:user_id>/set-password', methods=['POST'])
@login_required
def api_set_user_password(user_id):
    """Admin route to set a user's password."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    new_password = data.get('password', '')
    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

    user = _user_repo.get_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    _user_repo.update_password(user_id, new_password)
    from core.auth.repositories import EventRepository
    EventRepository().log_event('admin_password_reset', event_description=f'Password reset for user {user["email"]}', entity_type='user', entity_id=user_id)
    return jsonify({'success': True, 'message': f'Password set for {user["name"]}'})


@auth_bp.route('/api/users/set-default-passwords', methods=['POST'])
@login_required
def api_set_default_passwords():
    """Set default password for all users without one."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json() or {}
    default_password = data.get('password', 'changeme123')
    updated_count = _user_repo.set_default_passwords(default_password)
    from core.auth.repositories import EventRepository
    EventRepository().log_event('bulk_password_set', event_description=f'Set default password for {updated_count} users')
    return jsonify({
        'success': True,
        'message': f'Default password set for {updated_count} users',
        'updated_count': updated_count
    })


# ============== EVENT LOG ==============

@auth_bp.route('/api/events', methods=['GET'])
@login_required
def api_get_events():
    """Get user events/audit log."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    user_id = request.args.get('user_id', type=int)
    event_type = request.args.get('event_type', '')
    entity_type = request.args.get('entity_type', '')

    events = _event_repo.get_events(
        limit=limit,
        offset=offset,
        user_id=user_id if user_id else None,
        event_type=event_type if event_type else None,
        entity_type=entity_type if entity_type else None
    )
    return jsonify(events)


@auth_bp.route('/api/events/types', methods=['GET'])
@login_required
def api_get_event_types():
    """Get distinct event types for filtering."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    return jsonify(_event_repo.get_event_types())
