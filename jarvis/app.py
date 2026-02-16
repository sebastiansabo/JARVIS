# Version: 2026-02-08-docker
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory

# Structured logging
from core.utils.logging_config import setup_logging, get_logger
logger = setup_logging(level=os.environ.get('LOG_LEVEL', 'INFO'))
app_logger = get_logger('jarvis.app')
app_logger.info('JARVIS app module loading...')
from flask_compress import Compress
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import load_structure
from core.auth.models import User
from core.auth.repositories import UserRepository, EventRepository
from core.roles.repositories import PermissionRepository
from database import ping_db
from core.utils.api_helpers import RateLimiter

_auth_limiter = RateLimiter()

_user_repo = UserRepository()
_event_repo = EventRepository()
_perm_repo = PermissionRepository()

get_user = _user_repo.get_by_id
set_user_password = _user_repo.update_password
update_user_last_login = _user_repo.update_last_login
update_user_last_seen = _user_repo.update_last_seen
authenticate_user = _user_repo.authenticate
get_online_users_count = _user_repo.get_online_count
log_user_event = _event_repo.log_event
check_permission_v2 = _perm_repo.check_permission_v2


app = Flask(__name__)

# Secret key — required in production, dev fallback only when FLASK_DEBUG=true
_secret_key = os.environ.get('FLASK_SECRET_KEY', os.environ.get('SECRET_KEY'))
if not _secret_key:
    if os.environ.get('FLASK_DEBUG', 'false').lower() == 'true':
        _secret_key = 'dev-secret-key-for-local-only'
        app_logger.warning('Using development secret key — set FLASK_SECRET_KEY for production')
    else:
        raise RuntimeError('FLASK_SECRET_KEY environment variable is required')
app.secret_key = _secret_key

# Flask-Compress for gzip/brotli compression (60-70% size reduction)
compress = Compress()
compress.init_app(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Remember Me cookie configuration (30 days)
from datetime import timedelta
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_SECURE'] = True  # Only send over HTTPS
app.config['REMEMBER_COOKIE_HTTPONLY'] = True  # Not accessible via JavaScript
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection

# Session cookie hardening
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ============== Blueprint Registrations ==============

from hr import hr_bp
app.register_blueprint(hr_bp, url_prefix='/hr')

from accounting.statements import statements_bp
app.register_blueprint(statements_bp, url_prefix='/statements')

from ai_agent import ai_agent_bp
app.register_blueprint(ai_agent_bp)

from core.profile import profile_bp
app.register_blueprint(profile_bp)

from core.connectors.efactura import efactura_bp
app.register_blueprint(efactura_bp)

from core.settings import settings_bp
app.register_blueprint(settings_bp)

from core.tags import tags_bp
app.register_blueprint(tags_bp)

from core.presets import presets_bp
app.register_blueprint(presets_bp)

from core.notifications import notifications_bp
app.register_blueprint(notifications_bp)

from core.roles import roles_bp
app.register_blueprint(roles_bp)

from core.auth import auth_bp
app.register_blueprint(auth_bp)

from core.organization import org_bp
app.register_blueprint(org_bp)

from accounting.templates import templates_bp
app.register_blueprint(templates_bp)

from accounting.invoices import invoices_bp
app.register_blueprint(invoices_bp)

from accounting.bugetare import bugetare_bp
app.register_blueprint(bugetare_bp)

from core.drive import drive_bp
app.register_blueprint(drive_bp)

from core.connectors import connectors_bp
app.register_blueprint(connectors_bp)

from core.approvals import approvals_bp
app.register_blueprint(approvals_bp, url_prefix='/approvals')

app_logger.info(f'JARVIS startup complete — {len(app.url_map._rules)} routes registered')

# ============== Global Error Handlers ==============

@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return redirect('/app/dashboard')

@app.errorhandler(405)
def handle_405(e):
    return jsonify({'success': False, 'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def handle_500(e):
    app_logger.exception('Unhandled 500 error')
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500
    return redirect('/app/dashboard')

# ============== Background Scheduler ==============
# Start cleanup scheduler (only in main process or reloader child, not both)
if not os.environ.get('TESTING'):
    try:
        from tasks.cleanup import start_scheduler
        start_scheduler()
    except Exception as e:
        app_logger.warning(f'Failed to start background scheduler: {e}')


# ============== After-Request Hook ==============

@app.after_request
def add_cache_headers(response):
    """Add Cache-Control and ETag headers for better caching."""

    # Long-term cache for versioned static assets (Vite adds content hash to filenames)
    if request.path.startswith('/assets/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response

    # Cache legacy static files (CSS, JS, images) for 1 hour
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response

    # ETag for JSON responses — only hash if client sends If-None-Match
    if response.content_type and 'application/json' in response.content_type:
        if response.status_code == 200 and response.data:
            if_none_match = request.headers.get('If-None-Match')
            if if_none_match:
                import hashlib
                etag = hashlib.md5(response.data).hexdigest()
                response.headers['ETag'] = f'"{etag}"'
                if if_none_match == f'"{etag}"':
                    response.status_code = 304
                    response.data = b''

    if request.path == '/login' and response.status_code == 200:
        response.headers['Cache-Control'] = 'private, max-age=3600'

    if request.path == '/health' and response.status_code == 200:
        response.headers['Cache-Control'] = 'no-cache'

    if request.path == '/guide' and response.status_code == 200:
        response.headers['Cache-Control'] = 'private, max-age=3600'

    return response


# ============== Flask-Login ==============

_user_cache = {}
_USER_CACHE_TTL = 60  # seconds

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login (cached per-worker, 60s TTL)."""
    import time
    uid = int(user_id)
    now = time.time()
    cached = _user_cache.get(uid)
    if cached and (now - cached[1]) < _USER_CACHE_TTL:
        return cached[0]

    user_data = get_user(uid)
    if user_data:
        user = User(user_data)
        _user_cache[uid] = (user, now)
        return user
    _user_cache.pop(uid, None)
    return None


def log_event(event_type, description=None, entity_type=None, entity_id=None, details=None):
    """Helper to log user events with current user info."""
    user_id = current_user.id if current_user.is_authenticated else None
    user_email = current_user.email if current_user.is_authenticated else None
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent', '')[:500] if request else None

    log_user_event(
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


# ============== Authentication Routes ==============

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and form handler."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Rate limit: 10 attempts per 5 minutes per IP
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

        user_data = authenticate_user(email, password)
        if user_data:
            user = User(user_data)
            remember = request.form.get('remember') == 'on'
            login_user(user, remember=remember)
            update_user_last_login(user.id)
            log_event('login', f'User {email} logged in')

            next_page = request.args.get('next')
            if next_page and (not next_page.startswith('/') or next_page.startswith('//')):
                next_page = None
            return redirect(next_page or url_for('index'))
        else:
            log_event('login_failed', f'Failed login attempt for {email}')
            flash('Invalid email or password.', 'error')

    return render_template('core/login.html')


@app.route('/logout')
@login_required
def logout():
    """Logout current user."""
    log_event('logout', f'User {current_user.email} logged out')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# Password reset service (lazy-initialized)
_auth_service = None

def _get_auth_service():
    global _auth_service
    if _auth_service is None:
        from core.auth.services import AuthService
        _auth_service = AuthService()
    return _auth_service


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password page and form handler."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Rate limit: 5 attempts per 15 minutes per IP
        allowed, retry_after = _auth_limiter.is_allowed(
            f'forgot:{request.remote_addr}', max_requests=5, window_seconds=900)
        if not allowed:
            flash(f'Too many requests. Try again in {retry_after} seconds.', 'error')
            return redirect(url_for('forgot_password'))

        email = request.form.get('email', '').strip()
        base_url = request.host_url
        _get_auth_service().request_password_reset(email, base_url)

        log_event('password_reset_requested', f'Password reset requested for {email}')

        flash('If an account exists with that email, a reset link has been sent.', 'info')
        return redirect(url_for('forgot_password'))

    return render_template('core/forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password page and form handler."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    auth_svc = _get_auth_service()
    token_data = auth_svc.validate_reset_token(token)
    if not token_data:
        flash('This reset link is invalid or has expired.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('core/reset_password.html', token=token)

        result = auth_svc.reset_password(token, new_password)
        if result.success:
            log_event('password_reset_completed',
                      f'Password reset completed for {token_data["email"]}')
            flash('Your password has been reset. You can now sign in.', 'success')
            return redirect(url_for('login'))
        else:
            flash(result.error, 'error')
            return render_template('core/reset_password.html', token=token)

    return render_template('core/reset_password.html', token=token)


@app.route('/api/auth/current-user')
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


@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    """Change current user's password."""
    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'Both current and new passwords are required'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'New password must be at least 6 characters'}), 400

    user_data = authenticate_user(current_user.email, current_password)
    if not user_data:
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400

    set_user_password(current_user.id, new_password)
    log_event('password_changed', 'User changed their password')

    return jsonify({'success': True, 'message': 'Password changed successfully'})


# ============== Health Check ==============

@app.route('/health')
def health_check():
    """Application health check endpoint for orchestrator probes.

    Kept lightweight — runs every 10s per worker. Only checks DB connectivity.
    Cache cleanup runs on the scheduler instead.
    """
    checks = {}

    try:
        db_ok = ping_db()
        checks['database'] = db_ok
    except Exception as e:
        checks['database'] = False
        app_logger.error(f'Health check - database failed: {e}')

    status = 'healthy' if checks.get('database') else 'unhealthy'
    http_code = 200 if status == 'healthy' else 503

    return jsonify({
        'status': status,
        'checks': checks,
        'service': 'jarvis',
        'version': '2026-02-13'
    }), http_code


@app.route('/api/heartbeat', methods=['POST'])
@login_required
def api_heartbeat():
    """Update user's last_seen timestamp (called periodically by frontend)."""
    update_user_last_seen(current_user.id)
    return jsonify({'success': True})


@app.route('/api/online-users')
@login_required
def api_online_users():
    """Get count and list of currently online users (active in last 3 minutes)."""
    result = get_online_users_count(minutes=3)
    return jsonify(result)


# ============== Main Routes ==============

@app.route('/')
@login_required
def index():
    """Redirect to React dashboard."""
    return redirect('/app/dashboard')


@app.route('/apps')
@login_required
def apps_page():
    """Redirect to React dashboard."""
    return redirect('/app/dashboard')


@app.route('/guide')
@login_required
def user_guide():
    """Redirect to React dashboard."""
    return redirect('/app/dashboard')


@app.route('/api/structure')
@login_required
def get_structure():
    """Get the full organizational structure."""
    units = load_structure()
    return jsonify([{
        'id': u.id,
        'company_id': u.company_id,
        'company': u.company,
        'brand': u.brand,
        'department': u.department,
        'subdepartment': u.subdepartment,
        'manager': u.manager,
        'marketing': u.marketing,
        'display_name': u.display_name,
        'unique_key': u.unique_key
    } for u in units])


@app.route('/api/data')
@login_required
def get_data():
    """Get existing data (returns empty - legacy endpoint)."""
    return jsonify([])


@app.route('/settings')
@login_required
def settings():
    """Redirect to React settings."""
    return redirect('/app/settings')


# ============== React SPA Routes ==============

_react_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'react')

@app.route('/app/')
@app.route('/app/<path:path>')
@login_required
def react_app(path=''):
    """Serve the React SPA for all /app/* routes."""
    index_file = os.path.join(_react_dir, 'index.html')
    if os.path.exists(index_file):
        return send_from_directory(_react_dir, 'index.html')
    return redirect('/apps')


@app.route('/assets/<path:filename>')
def react_assets(filename):
    """Serve React build assets (JS, CSS, etc.)."""
    return send_from_directory(os.path.join(_react_dir, 'assets'), filename)


if __name__ == '__main__':
    import os
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=debug, host='0.0.0.0', port=port)
