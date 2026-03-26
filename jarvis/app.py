# Version: 2026-02-18-docker
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, redirect, send_from_directory

# Structured logging (module-level — needed before app creation)
from core.utils.logging_config import setup_logging, get_logger
from core.config import AppConfig

_startup_log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = setup_logging(level=_startup_log_level)
app_logger = get_logger('jarvis.app')
app_logger.info('JARVIS app module loading...')

from flask_compress import Compress
from flask_login import LoginManager, login_required, current_user
from models import load_structure
from core.auth.models import User
from core.auth.repositories import UserRepository
from database import ping_db

_user_repo = UserRepository()


# ============== App Factory ==============

def create_app(config: AppConfig = None) -> Flask:
    if config is None:
        config = AppConfig.from_env()

    flask_app = Flask(__name__)

    _configure_app(flask_app, config)
    _setup_login_manager(flask_app)
    _register_blueprints(flask_app)
    _register_hooks(flask_app)
    _register_error_handlers(flask_app)
    _register_routes(flask_app)

    # Background scheduler (skip during tests)
    if not os.environ.get('TESTING'):
        try:
            from tasks.cleanup import start_scheduler
            start_scheduler()
        except Exception as e:
            app_logger.warning(f'Failed to start background scheduler: {e}')

    app_logger.info(f'JARVIS startup complete — {len(flask_app.url_map._rules)} routes registered')
    return flask_app


def _configure_app(flask_app: Flask, config: AppConfig):
    """Apply configuration to Flask app instance."""
    from datetime import timedelta

    # Secret key
    secret_key = config.secret_key
    if not secret_key:
        secret_key = 'dev-only-insecure-key-not-for-production'
        app_logger.warning('No FLASK_SECRET_KEY set — using insecure dev key. Set FLASK_SECRET_KEY env var for production!')
    flask_app.secret_key = secret_key

    # Compression
    compress = Compress()
    compress.init_app(flask_app)

    # Detect production
    is_production = config.flask_env.lower() == 'production' or (
        'localhost' not in config.database_url
        and '127.0.0.1' not in config.database_url
    )

    # Remember Me cookie (30 days)
    flask_app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
    flask_app.config['REMEMBER_COOKIE_SECURE'] = is_production
    flask_app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    flask_app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'

    # Session cookie hardening
    flask_app.config['SESSION_COOKIE_SECURE'] = is_production
    flask_app.config['SESSION_COOKIE_HTTPONLY'] = True
    flask_app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Store config for use in hooks
    flask_app.jarvis_config = config


def _setup_login_manager(flask_app: Flask):
    """Configure Flask-Login."""
    import time

    login_manager = LoginManager()
    login_manager.init_app(flask_app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'

    _user_cache = {}
    _USER_CACHE_TTL = 60

    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login (cached per-worker, 60s TTL)."""
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


def _register_blueprints(flask_app: Flask):
    """Register all application blueprints."""
    from admin_routes import admin_bp
    flask_app.register_blueprint(admin_bp)

    from hr import hr_bp
    flask_app.register_blueprint(hr_bp, url_prefix='/hr')

    from accounting.statements import statements_bp
    flask_app.register_blueprint(statements_bp, url_prefix='/statements')

    from ai_agent import ai_agent_bp
    flask_app.register_blueprint(ai_agent_bp)

    from core.profile import profile_bp
    flask_app.register_blueprint(profile_bp)

    from core.connectors.efactura import efactura_bp
    flask_app.register_blueprint(efactura_bp)

    from core.connectors.biostar import biostar_bp
    flask_app.register_blueprint(biostar_bp)

    from core.checkin import checkin_bp
    flask_app.register_blueprint(checkin_bp)

    from core.settings import settings_bp
    flask_app.register_blueprint(settings_bp)

    from core.tags import tags_bp
    flask_app.register_blueprint(tags_bp)

    from core.presets import presets_bp
    flask_app.register_blueprint(presets_bp)

    from core.notifications import notifications_bp
    flask_app.register_blueprint(notifications_bp)

    from core.roles import roles_bp
    flask_app.register_blueprint(roles_bp)

    from core.auth import auth_bp
    flask_app.register_blueprint(auth_bp)

    from core.organization import org_bp
    flask_app.register_blueprint(org_bp)

    from accounting.templates import templates_bp
    flask_app.register_blueprint(templates_bp)

    from accounting.invoices import invoices_bp
    flask_app.register_blueprint(invoices_bp)

    from accounting.bugetare import bugetare_bp
    flask_app.register_blueprint(bugetare_bp)

    from accounting.bilant import bilant_bp
    flask_app.register_blueprint(bilant_bp, url_prefix='/bilant')

    from core.drive import drive_bp
    flask_app.register_blueprint(drive_bp)

    from core.connectors import connectors_bp
    flask_app.register_blueprint(connectors_bp)

    from core.approvals import approvals_bp
    flask_app.register_blueprint(approvals_bp, url_prefix='/approvals')

    from marketing import marketing_bp
    flask_app.register_blueprint(marketing_bp, url_prefix='/marketing')

    from core.signatures import signatures_bp
    flask_app.register_blueprint(signatures_bp, url_prefix='/signatures')

    from crm import crm_bp
    flask_app.register_blueprint(crm_bp)

    from dms import dms_bp
    flask_app.register_blueprint(dms_bp, url_prefix='/dms')

    from forms import forms_bp
    flask_app.register_blueprint(forms_bp, url_prefix='/forms')

    from core.mobile import mobile_bp
    flask_app.register_blueprint(mobile_bp)


def _register_hooks(flask_app: Flask):
    """Register before/after request hooks and approval notification handlers."""
    import time as _time
    from core.mobile.routes import _decode_token, _JWT_SECRET
    from flask_login import login_user as _fl_login

    @flask_app.before_request
    def _jwt_session_bridge():
        """If request has a valid JWT Bearer token and no active session, log the user in."""
        if current_user.is_authenticated:
            return
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return
        token = auth_header[7:]
        payload = _decode_token(token, _JWT_SECRET)
        if not payload or payload.get('type') != 'access':
            return
        user_id = payload.get('sub')
        if not user_id:
            return
        user_data = _user_repo.get_by_id(user_id)
        if user_data:
            _fl_login(User(user_data))

    @flask_app.after_request
    def _mobile_cors(response):
        origin = request.headers.get('Origin', '')
        if origin.startswith(('capacitor://', 'http://localhost', 'https://localhost', 'http://127.0.0.1')):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Max-Age'] = '86400'
            if request.method == 'OPTIONS':
                response.status_code = 204
        return response

    @flask_app.before_request
    def _start_timer():
        request._start_time = _time.time()

    @flask_app.after_request
    def _log_slow_requests(response):
        start = getattr(request, '_start_time', None)
        if start and request.path.startswith('/api/'):
            elapsed = _time.time() - start
            if elapsed > 1.0:
                app_logger.warning(f'Slow request: {request.method} {request.path} — {elapsed:.2f}s (status={response.status_code})')
        return response

    @flask_app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(self)'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'self'"
        )
        if flask_app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @flask_app.after_request
    def add_cache_headers(response):
        if request.path.startswith('/assets/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            return response
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=3600'
            return response
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

    # Approval notification hooks
    from core.approvals.handlers import register_approval_hooks
    register_approval_hooks()


def _register_error_handlers(flask_app: Flask):
    """Register global error handlers."""
    @flask_app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith(('/api/', '/assets/')) or request.method != 'GET':
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return redirect('/app/dashboard')

    @flask_app.errorhandler(405)
    def handle_405(e):
        return jsonify({'success': False, 'error': 'Method not allowed'}), 405

    @flask_app.errorhandler(500)
    def handle_500(e):
        app_logger.exception('Unhandled 500 error')
        if '/api/' in request.path:
            return jsonify({'success': False, 'error': 'An internal error occurred'}), 500
        return redirect('/app/dashboard')

    @flask_app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            if '/api/' in request.path or request.content_type == 'application/json':
                return jsonify({'success': False, 'error': e.description or str(e)}), e.code
            return e.get_response()
        app_logger.exception(f'Unhandled exception: {type(e).__name__}')
        if '/api/' in request.path or request.content_type == 'application/json':
            return jsonify({'success': False, 'error': 'An internal error occurred'}), 500
        return redirect('/app/dashboard')


def _register_routes(flask_app: Flask):
    """Register main application routes."""
    _react_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'react')

    @flask_app.route('/health')
    def health_check():
        checks = {}
        try:
            db_ok = ping_db()
            checks['database'] = db_ok
        except Exception as e:
            checks['database'] = False
            app_logger.error(f'Health check - database failed: {e}')
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

    @flask_app.route('/')
    @login_required
    def index():
        return redirect('/app/dashboard')

    @flask_app.route('/apps')
    @login_required
    def apps_page():
        return redirect('/app/dashboard')

    @flask_app.route('/guide')
    @login_required
    def user_guide():
        return redirect('/app/dashboard')

    @flask_app.route('/api/structure')
    @login_required
    def get_structure():
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

    @flask_app.route('/api/data')
    @login_required
    def get_data():
        return jsonify([])

    @flask_app.route('/settings')
    @login_required
    def settings():
        return redirect('/app/settings')

    @flask_app.route('/app/')
    @flask_app.route('/app/<path:path>')
    @login_required
    def react_app(path=''):
        index_file = os.path.join(_react_dir, 'index.html')
        if os.path.exists(index_file):
            resp = send_from_directory(_react_dir, 'index.html')
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return resp
        return redirect('/apps')

    @flask_app.route('/f/<path:slug>')
    def public_form_page(slug):
        """Serve React SPA for public form pages — NO auth required."""
        index_file = os.path.join(_react_dir, 'index.html')
        if os.path.exists(index_file):
            resp = send_from_directory(_react_dir, 'index.html')
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return resp
        return 'Not found', 404

    @flask_app.route('/assets/<path:filename>')
    def react_assets(filename):
        return send_from_directory(os.path.join(_react_dir, 'assets'), filename)

    # ── Public APK download ──────────────────────────────────────────
    @flask_app.route('/download/jarvis.apk')
    def download_apk():
        downloads_dir = os.path.join(flask_app.static_folder, 'downloads')
        return send_from_directory(downloads_dir, 'jarvis.apk',
                                   as_attachment=True,
                                   mimetype='application/vnd.android.package-archive')

    @flask_app.route('/download')
    def download_page():
        base_url = request.host_url.rstrip('/')
        apk_url = f'{base_url}/download/jarvis.apk'
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JARVIS Mobile - Download</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 20px;
    padding: 48px 40px;
    max-width: 420px;
    width: 90%;
    text-align: center;
    box-shadow: 0 25px 50px rgba(0,0,0,0.4);
  }}
  .logo {{
    width: 80px; height: 80px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border-radius: 20px;
    display: flex; align-items: center; justify-content: center;
    margin: 0 auto 24px;
    font-size: 36px; font-weight: 700; color: white;
  }}
  h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
  .subtitle {{ color: #94a3b8; font-size: 15px; margin-bottom: 32px; }}
  .qr-container {{
    background: white;
    border-radius: 16px;
    padding: 20px;
    display: inline-block;
    margin-bottom: 24px;
  }}
  .qr-container img {{ display: block; }}
  .download-btn {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: white;
    text-decoration: none;
    padding: 14px 32px;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 600;
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  .download-btn:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(59,130,246,0.4);
  }}
  .download-btn svg {{ width: 20px; height: 20px; }}
  .instructions {{
    margin-top: 28px;
    padding-top: 24px;
    border-top: 1px solid #334155;
    text-align: left;
  }}
  .instructions h3 {{
    font-size: 14px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
  }}
  .instructions ol {{
    padding-left: 20px;
    color: #cbd5e1;
    font-size: 14px;
    line-height: 1.8;
  }}
  .version {{
    margin-top: 20px;
    font-size: 12px;
    color: #64748b;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">J</div>
  <h1>JARVIS Mobile</h1>
  <p class="subtitle">Scan the QR code or tap the button to download</p>

  <div class="qr-container">
    <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={apk_url}&format=png"
         alt="QR Code" width="200" height="200" />
  </div>

  <br/>
  <a href="{apk_url}" class="download-btn">
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
      <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V3"/>
    </svg>
    Download APK
  </a>

  <div class="instructions">
    <h3>Installation</h3>
    <ol>
      <li>Download the APK file</li>
      <li>Open the file on your Android device</li>
      <li>Allow "Install from unknown sources" if prompted</li>
      <li>Tap Install and open JARVIS</li>
    </ol>
  </div>

  <p class="version">Android &bull; v1.0.0</p>
</div>
</body>
</html>'''
        return html, 200, {{'Content-Type': 'text/html'}}


# Module-level instance for gunicorn + `flask run`
app = create_app()


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=debug, host='0.0.0.0', port=port)
