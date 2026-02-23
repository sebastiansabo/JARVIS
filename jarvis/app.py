# Version: 2026-02-18-docker
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, redirect, send_from_directory

# Structured logging
from core.utils.logging_config import setup_logging, get_logger
logger = setup_logging(level=os.environ.get('LOG_LEVEL', 'INFO'))
app_logger = get_logger('jarvis.app')
app_logger.info('JARVIS app module loading...')
from flask_compress import Compress
from flask_login import LoginManager, login_required, current_user
from models import load_structure
from core.auth.models import User
from core.auth.repositories import UserRepository
from database import ping_db

_user_repo = UserRepository()

app = Flask(__name__)

# Secret key — prefer env var; fixed fallback ensures all workers share the same key
_secret_key = os.environ.get('FLASK_SECRET_KEY', os.environ.get('SECRET_KEY', ''))
if not _secret_key:
    _secret_key = 'dev-only-insecure-key-not-for-production'
    app_logger.warning('No FLASK_SECRET_KEY set — using insecure dev key. Set FLASK_SECRET_KEY env var for production!')
app.secret_key = _secret_key

# Flask-Compress for gzip/brotli compression (60-70% size reduction)
compress = Compress()
compress.init_app(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'

# Remember Me cookie configuration (30 days)
from datetime import timedelta
_is_production = os.environ.get('FLASK_ENV', '').lower() == 'production' or (
    'localhost' not in os.environ.get('DATABASE_URL', 'localhost')
    and '127.0.0.1' not in os.environ.get('DATABASE_URL', '127.0.0.1')
)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_SECURE'] = _is_production  # Only send over HTTPS in prod
app.config['REMEMBER_COOKIE_HTTPONLY'] = True  # Not accessible via JavaScript
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection

# Session cookie hardening
app.config['SESSION_COOKIE_SECURE'] = _is_production  # Only send over HTTPS in prod
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

from marketing import marketing_bp
app.register_blueprint(marketing_bp, url_prefix='/marketing')

from core.signatures import signatures_bp
app.register_blueprint(signatures_bp, url_prefix='/signatures')

# Register approval notification hooks
from core.approvals.handlers import register_approval_hooks
register_approval_hooks()

app_logger.info(f'JARVIS startup complete — {len(app.url_map._rules)} routes registered')

# ============== Global Error Handlers ==============

@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith(('/api/', '/assets/')) or request.method != 'GET':
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return redirect('/app/dashboard')

@app.errorhandler(405)
def handle_405(e):
    return jsonify({'success': False, 'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def handle_500(e):
    app_logger.exception('Unhandled 500 error')
    if '/api/' in request.path:
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500
    return redirect('/app/dashboard')

@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all for unhandled exceptions — never leak stack traces."""
    app_logger.exception(f'Unhandled exception: {type(e).__name__}')
    if '/api/' in request.path or request.content_type == 'application/json':
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


# ============== Request Timing ==============

import time as _time

@app.before_request
def _start_timer():
    request._start_time = _time.time()

@app.after_request
def _log_slow_requests(response):
    start = getattr(request, '_start_time', None)
    if start and request.path.startswith('/api/'):
        elapsed = _time.time() - start
        if elapsed > 1.0:
            app_logger.warning(f'Slow request: {request.method} {request.path} — {elapsed:.2f}s (status={response.status_code})')
    return response

# ============== After-Request Hook ==============

@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https:; "
        "frame-ancestors 'self'"
    )

    # HSTS — only in production (when SESSION_COOKIE_SECURE is set)
    if app.config.get('SESSION_COOKIE_SECURE'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    return response


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

    user_data = _user_repo.get_by_id(uid)
    if user_data:
        user = User(user_data)
        _user_cache[uid] = (user, now)
        return user
    _user_cache.pop(uid, None)
    return None


# ============== Health Check ==============

@app.route('/health')
def health_check():
    """Application health check endpoint for orchestrator probes."""
    checks = {}

    try:
        db_ok = ping_db()
        checks['database'] = db_ok
    except Exception as e:
        checks['database'] = False
        app_logger.error(f'Health check - database failed: {e}')

    # Scheduler status (non-critical)
    try:
        from tasks.cleanup import scheduler
        checks['scheduler'] = scheduler.running
    except Exception:
        checks['scheduler'] = False

    status = 'healthy' if checks.get('database') else 'unhealthy'
    http_code = 200 if status == 'healthy' else 503

    return jsonify({
        'status': status,
        'checks': checks,
        'service': 'jarvis',
        'version': '2026-02-18'
    }), http_code


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
        resp = send_from_directory(_react_dir, 'index.html')
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
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
