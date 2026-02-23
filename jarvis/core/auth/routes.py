"""Auth module routes.

All authentication, user management, employee management, password management,
and event log routes.
"""
from flask import jsonify, request, render_template, redirect, url_for, flash
from flask_login import login_required, login_user, logout_user, current_user

from . import auth_bp
from .models import User
from .repositories import UserRepository, EventRepository
from core.utils.api_helpers import admin_required, error_response, safe_error_response, RateLimiter

_user_repo = UserRepository()
_event_repo = EventRepository()
_auth_limiter = RateLimiter()

# Lazy-initialized password reset service
_auth_service = None


def _get_auth_service():
    global _auth_service
    if _auth_service is None:
        from core.auth.services import AuthService
        _auth_service = AuthService()
    return _auth_service


def _log_event(event_type, description=None, entity_type=None, entity_id=None, details=None):
    """Log user event with current user info."""
    user_id = current_user.id if current_user.is_authenticated else None
    user_email = current_user.email if current_user.is_authenticated else None
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent', '')[:500] if request else None

    _event_repo.log_event(
        event_type=event_type,
        event_description=description,
        user_id=user_id,
        user_email=user_email,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details
    )


# ============== AUTHENTICATION ROUTES ==============

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and form handler."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        allowed, retry_after = _auth_limiter.is_allowed(
            f'login:{request.remote_addr}', max_requests=10, window_seconds=300)
        if not allowed:
            flash(f'Too many login attempts. Try again in {retry_after} seconds.', 'error')
            return render_template('core/login.html')

        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('core/login.html')

        user_data = _user_repo.authenticate(email, password)
        if user_data:
            user = User(user_data)
            remember = request.form.get('remember') == 'on'
            login_user(user, remember=remember)
            _user_repo.update_last_login(user.id)
            _log_event('login', f'User {email} logged in')

            next_page = request.args.get('next')
            if next_page and (not next_page.startswith('/') or next_page.startswith('//')):
                next_page = None
            return redirect(next_page or url_for('index'))
        else:
            _log_event('login_failed', f'Failed login attempt for {email}')
            flash('Invalid email or password.', 'error')

    return render_template('core/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout current user."""
    _log_event('logout', f'User {current_user.email} logged out')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password page and form handler."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        allowed, retry_after = _auth_limiter.is_allowed(
            f'forgot:{request.remote_addr}', max_requests=5, window_seconds=900)
        if not allowed:
            flash(f'Too many requests. Try again in {retry_after} seconds.', 'error')
            return redirect(url_for('auth.forgot_password'))

        email = request.form.get('email', '').strip()
        base_url = request.host_url
        _get_auth_service().request_password_reset(email, base_url)

        _log_event('password_reset_requested', f'Password reset requested for {email}')

        flash('If an account exists with that email, a reset link has been sent.', 'info')
        return redirect(url_for('auth.forgot_password'))

    return render_template('core/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password page and form handler."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    auth_svc = _get_auth_service()
    token_data = auth_svc.validate_reset_token(token)
    if not token_data:
        flash('This reset link is invalid or has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('core/reset_password.html', token=token)

        result = auth_svc.reset_password(token, new_password)
        if result.success:
            _log_event('password_reset_completed',
                       f'Password reset completed for {token_data["email"]}')
            flash('Your password has been reset. You can now sign in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash(result.error, 'error')
            return render_template('core/reset_password.html', token=token)

    return render_template('core/reset_password.html', token=token)


@auth_bp.route('/api/auth/current-user')
def api_current_user():
    """Get current user info for UI."""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': {
                'id': current_user.id,
                'name': current_user.name,
                'email': current_user.email,
                'role_id': current_user.role_id,
                'role_name': current_user.role_name,
                'is_active': current_user.is_active,
                'company': current_user.company,
                'brand': current_user.brand,
                'department': current_user.department,
                'subdepartment': current_user.subdepartment,
                'can_add_invoices': current_user.can_add_invoices,
                'can_edit_invoices': current_user.can_edit_invoices,
                'can_delete_invoices': current_user.can_delete_invoices,
                'can_view_invoices': current_user.can_view_invoices,
                'can_access_accounting': current_user.can_access_accounting,
                'can_access_settings': current_user.can_access_settings,
                'can_access_connectors': current_user.can_access_connectors,
                'can_access_templates': current_user.can_access_templates,
                'can_access_hr': current_user.can_access_hr,
                'is_hr_manager': current_user.is_hr_manager,
                'can_access_efactura': current_user.can_access_efactura,
                'can_access_statements': current_user.can_access_statements,
            }
        })
    return jsonify({'authenticated': False})


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    """Change current user's password."""
    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'Both current and new passwords are required'}), 400

    if len(new_password) < 10:
        return jsonify({'success': False, 'error': 'New password must be at least 10 characters'}), 400

    user_data = _user_repo.authenticate(current_user.email, current_password)
    if not user_data:
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400

    _user_repo.update_password(current_user.id, new_password)
    _log_event('password_changed', 'User changed their password')

    return jsonify({'success': True, 'message': 'Password changed successfully'})


@auth_bp.route('/api/heartbeat', methods=['POST'])
@login_required
def api_heartbeat():
    """Update user's last_seen timestamp (called periodically by frontend)."""
    _user_repo.update_last_seen(current_user.id)
    return jsonify({'success': True})


@auth_bp.route('/api/online-users')
@login_required
def api_online_users():
    """Get count and list of currently online users (active in last 3 minutes)."""
    result = _user_repo.get_online_count(minutes=3)
    return jsonify(result)


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
    """Get a specific user with role information.
    Users can view their own profile; admin required for others.
    """
    if user_id != current_user.id and not current_user.can_access_settings:
        return error_response('Permission denied', 403)
    user = _user_repo.get_by_id(user_id)
    if user:
        return jsonify(user)
    return error_response('User not found', 404)


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
        return error_response('Name and email are required')

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


@auth_bp.route('/api/users/bulk-update-role', methods=['POST'])
@admin_required
def api_bulk_update_role():
    """Set role for multiple users."""
    data = request.get_json()
    user_ids = data.get('ids', [])
    role_id = data.get('role_id')
    if not user_ids or not role_id:
        return jsonify({'success': False, 'error': 'IDs and role_id required'}), 400
    try:
        user_ids = [int(uid) for uid in user_ids]
        role_id = int(role_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid format'}), 400
    updated = _user_repo.bulk_update_role(user_ids, role_id)
    return jsonify({'success': True, 'updated': updated})


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
    """Get a specific user as employee.
    Users can view their own record; admin required for others.
    """
    if employee_id != current_user.id and not current_user.can_access_settings:
        return error_response('Permission denied', 403)
    user = _user_repo.get_by_id(employee_id)
    if user:
        user['departments'] = user.get('department')
        return jsonify(user)
    return error_response('Employee not found', 404)


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
        return error_response('Name is required')

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
    _event_repo.log_event('profile_updated', event_description=f'User updated their profile: name={name}')
    return jsonify({'success': True, 'message': 'Profile updated successfully', 'name': name})


@auth_bp.route('/api/users/<int:user_id>/set-password', methods=['POST'])
@login_required
def api_set_user_password(user_id):
    """Admin route to set a user's password."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    new_password = data.get('password', '')
    if not new_password or len(new_password) < 10:
        return jsonify({'success': False, 'error': 'Password must be at least 10 characters'}), 400

    user = _user_repo.get_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    _user_repo.update_password(user_id, new_password)
    _event_repo.log_event('admin_password_reset', event_description=f'Password reset for user {user["email"]}', entity_type='user', entity_id=user_id)
    return jsonify({'success': True, 'message': f'Password set for {user["name"]}'})


@auth_bp.route('/api/users/set-default-passwords', methods=['POST'])
@login_required
def api_set_default_passwords():
    """Set default password for all users without one."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json() or {}
    default_password = data.get('password')
    if not default_password or len(default_password) < 10:
        return jsonify({'success': False, 'error': 'Password is required and must be at least 10 characters'}), 400
    updated_count = _user_repo.set_default_passwords(default_password)
    _event_repo.log_event('bulk_password_set', event_description=f'Set default password for {updated_count} users')
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
