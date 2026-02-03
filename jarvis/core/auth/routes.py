"""JARVIS Core Auth Routes.

Authentication routes: login, logout, password management.
Follows layered architecture: Routes -> Services -> Repositories -> Database
"""
from flask import render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from . import auth_bp
from .models import User
from .services import AuthService

# Initialize service layer
auth_service = AuthService()


def log_event(event_type, description=None, entity_type=None, entity_id=None, details=None):
    """Helper to log user events with current user info."""
    user_id = current_user.id if current_user.is_authenticated else None
    user_email = current_user.email if current_user.is_authenticated else None
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent', '')[:500] if request else None

    auth_service.log_event(
        event_type=event_type,
        description=description,
        user_id=user_id,
        user_email=user_email,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details
    )


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and form handler."""
    if current_user.is_authenticated:
        # Redirect based on user permissions
        if current_user.can_access_main_apps():
            return redirect(url_for('apps_page'))
        return redirect(url_for('profile.profile_page'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('core/login.html')

        result = auth_service.authenticate(email, password)
        if result.success:
            user = User(result.user_data)
            remember = request.form.get('remember') == 'on'
            login_user(user, remember=remember)
            auth_service.update_last_login(user.id)
            log_event('login', f'User {email} logged in')

            # Redirect based on user permissions
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            if user.can_access_main_apps():
                return redirect(url_for('apps_page'))
            return redirect(url_for('profile.profile_page'))
        else:
            log_event('login_failed', f'Failed login attempt for {email}')
            flash('Invalid email or password.', 'error')

    return render_template('core/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout current user."""
    log_event('logout', f'User {current_user.email} logged out')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/api/auth/current-user')
@login_required
def get_current_user():
    """Get current user details including role permissions."""
    return jsonify({
        'id': current_user.id,
        'email': current_user.email,
        'name': current_user.name,
        'role_id': current_user.role_id,
        'role_name': current_user.role_name,
        'permissions': {
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
        }
    })


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """Change current user's password."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    current_password = data.get('current_password')
    new_password = data.get('new_password')

    result = auth_service.change_password(
        user_id=current_user.id,
        user_email=current_user.email,
        current_password=current_password,
        new_password=new_password
    )

    if result.success:
        log_event('password_changed', f'User {current_user.email} changed their password')
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result.error}), 400


@auth_bp.route('/api/heartbeat', methods=['POST'])
@login_required
def heartbeat():
    """Update user's last seen timestamp for online status tracking."""
    auth_service.update_last_seen(current_user.id)
    return jsonify({'success': True})


@auth_bp.route('/api/online-users')
@login_required
def online_users():
    """Get count and list of currently online users."""
    result = auth_service.get_online_users(minutes=5)
    return jsonify(result)
