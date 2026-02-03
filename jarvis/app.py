# Version: 2025-12-18-role-fix
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response

# Structured logging
from core.utils.logging_config import setup_logging, get_logger
logger = setup_logging(level=os.environ.get('LOG_LEVEL', 'INFO'))
app_logger = get_logger('jarvis.app')
from flask_compress import Compress
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from models import load_structure, get_companies, get_brands_for_company, get_departments_for_company, get_subdepartments, get_manager
from services import (
    get_companies_with_vat, match_company_by_vat, add_company_with_vat, update_company_vat, delete_company
)
from accounting.bugetare.invoice_parser import parse_invoice, parse_invoice_with_template_from_bytes, auto_detect_and_parse, generate_template_from_invoice, match_campaigns_with_ai
from database import (
    get_all_invoices, get_invoice_with_allocations, get_invoices_with_allocations, search_invoices,
    get_summary_by_company, get_summary_by_department, get_summary_by_brand, get_summary_by_supplier, delete_invoice, update_invoice, save_invoice,
    update_invoice_allocations,
    get_all_invoice_templates, get_invoice_template, save_invoice_template,
    update_invoice_template, delete_invoice_template,
    check_invoice_number_exists,
    restore_invoice, bulk_soft_delete_invoices, bulk_restore_invoices,
    permanently_delete_invoice, bulk_permanently_delete_invoices,
    get_invoice_drive_link, get_invoice_drive_links,
    get_all_users, get_user, get_user_by_email, save_user, update_user, delete_user, delete_users_bulk,
    get_all_roles, get_role, save_role, update_role, delete_role,
    get_notification_settings, save_notification_settings_bulk, save_notification_setting, get_notification_logs,
    get_all_companies, get_company, save_company, update_company, delete_company as delete_company_db,
    get_all_department_structures, get_department_structure, save_department_structure,
    update_department_structure, delete_department_structure, get_unique_departments, get_unique_brands,
    authenticate_user, set_user_password, update_user_last_login, update_user_last_seen, get_online_users_count, set_default_password_for_users,
    log_user_event, get_user_events, get_event_types,
    update_allocation_comment,
    get_vat_rates, add_vat_rate, update_vat_rate, delete_vat_rate,
    get_dropdown_options, get_dropdown_option, add_dropdown_option, update_dropdown_option, delete_dropdown_option,
    refresh_connection_pool, ping_db, cleanup_expired_caches,
    get_all_permissions, get_permissions_flat, get_role_permissions, get_role_permissions_list, set_role_permissions
)

# Google Drive integration (optional)
try:
    from core.services.drive_service import (
        upload_invoice_to_drive, check_drive_auth, delete_file_from_drive, delete_files_from_drive,
        get_folder_id_from_file_link, get_folder_link_from_file, upload_attachment_to_folder
    )
    DRIVE_ENABLED = True
except ImportError:
    DRIVE_ENABLED = False
    delete_file_from_drive = None
    delete_files_from_drive = None
    get_folder_id_from_file_link = None
    get_folder_link_from_file = None
    upload_attachment_to_folder = None

# Currency conversion (BNR rates)
try:
    from core.services.currency_converter import get_eur_ron_conversion
    CURRENCY_CONVERSION_ENABLED = True
except ImportError:
    CURRENCY_CONVERSION_ENABLED = False

# Email notifications
try:
    from core.services.notification_service import (
        notify_invoice_allocations,
        send_test_email,
        is_smtp_configured
    )
    NOTIFICATIONS_ENABLED = True
except ImportError:
    NOTIFICATIONS_ENABLED = False

# Image compression (TinyPNG)
try:
    from core.services.image_compressor import compress_if_image
    IMAGE_COMPRESSION_ENABLED = True
except ImportError:
    IMAGE_COMPRESSION_ENABLED = False
    compress_if_image = None

# Role hierarchy for status permissions (higher index = more permissions)
ROLE_HIERARCHY = ['Viewer', 'Manager', 'Admin']


def user_can_set_status(user_role_name: str, status_value: str, dropdown_type: str = 'invoice_status') -> bool:
    """
    Check if a user's role meets the min_role requirement for a specific status.

    Args:
        user_role_name: The user's role name (e.g., 'Viewer', 'Manager', 'Admin')
        status_value: The status value to check (e.g., 'new', 'processed')
        dropdown_type: The dropdown type ('invoice_status' or 'payment_status')

    Returns:
        True if the user can set this status, False otherwise
    """
    options = get_dropdown_options(dropdown_type, active_only=True)
    status_option = next((opt for opt in options if opt['value'] == status_value), None)

    if not status_option:
        return False  # Status doesn't exist

    min_role = status_option.get('min_role')
    if not min_role:
        return True  # No restriction

    user_level = ROLE_HIERARCHY.index(user_role_name) if user_role_name in ROLE_HIERARCHY else -1
    min_level = ROLE_HIERARCHY.index(min_role) if min_role in ROLE_HIERARCHY else 0

    return user_level >= min_level


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

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

# Register HR Module Blueprint (section-level, includes /events sub-routes)
from hr import hr_bp
app.register_blueprint(hr_bp, url_prefix='/hr')

# Register Statements Module Blueprint (bank statement parsing)
from accounting.statements import statements_bp
app.register_blueprint(statements_bp, url_prefix='/statements')

# Register AI Agent Module Blueprint
from ai_agent import ai_agent_bp
app.register_blueprint(ai_agent_bp)

# Register Profile Module Blueprint
from core.profile import profile_bp
app.register_blueprint(profile_bp)

# Register e-Factura Module Blueprint (ANAF e-Invoicing connector)
from core.connectors.efactura import efactura_bp
app.register_blueprint(efactura_bp)

# Register Accounting e-Factura Blueprint (unallocated invoices management)
from accounting.efactura import accounting_efactura_bp
app.register_blueprint(accounting_efactura_bp)

# Cache-Control headers for API responses
# NOTE: Browser caching disabled for all Settings-related endpoints to avoid stale data
# after edits. Performance impact is minimal (<50ms per request for these simple queries).
CACHEABLE_API_ENDPOINTS = {
    # All reference data endpoints removed - fresh data is more valuable than caching
}

@app.after_request
def add_cache_headers(response):
    """Add Cache-Control and ETag headers for better caching."""
    import hashlib

    # Add ETag for JSON responses to enable conditional requests
    if response.content_type and 'application/json' in response.content_type:
        if response.status_code == 200 and response.data:
            # Generate ETag from response content
            etag = hashlib.md5(response.data).hexdigest()
            response.headers['ETag'] = f'"{etag}"'

            # Check if client sent If-None-Match header
            if_none_match = request.headers.get('If-None-Match')
            if if_none_match and if_none_match == f'"{etag}"':
                # Content hasn't changed, return 304 Not Modified
                response.status_code = 304
                response.data = b''

    # Add Cache-Control for cacheable API endpoints
    if request.path in CACHEABLE_API_ENDPOINTS and response.status_code in (200, 304):
        max_age = CACHEABLE_API_ENDPOINTS[request.path]
        response.headers['Cache-Control'] = f'private, max-age={max_age}'

    # Add cache headers for static-like HTML pages (login page)
    if request.path == '/login' and response.status_code == 200:
        response.headers['Cache-Control'] = 'private, max-age=3600'  # 1 hour

    # Add long cache for health endpoint (used by uptime monitors)
    if request.path == '/health' and response.status_code == 200:
        response.headers['Cache-Control'] = 'no-cache'  # Always check, but allow conditional

    # Add cache headers for user guide (static content)
    if request.path == '/guide' and response.status_code == 200:
        response.headers['Cache-Control'] = 'private, max-age=3600'  # 1 hour

    return response


class User(UserMixin):
    """User class for Flask-Login."""

    def __init__(self, user_data):
        self.id = user_data['id']
        self.email = user_data['email']
        self.name = user_data['name']
        self.role_id = user_data.get('role_id')
        self.role_name = user_data.get('role_name')
        self.is_active_user = user_data.get('is_active', True)
        # Role permissions (backward compatible boolean properties)
        self.can_add_invoices = user_data.get('can_add_invoices', False)
        self.can_edit_invoices = user_data.get('can_edit_invoices', False)
        self.can_delete_invoices = user_data.get('can_delete_invoices', False)
        self.can_view_invoices = user_data.get('can_view_invoices', False)
        self.can_access_accounting = user_data.get('can_access_accounting', False)
        self.can_access_settings = user_data.get('can_access_settings', False)
        self.can_access_connectors = user_data.get('can_access_connectors', False)
        self.can_access_templates = user_data.get('can_access_templates', False)
        self.can_access_hr = user_data.get('can_access_hr', False)
        self.is_hr_manager = user_data.get('is_hr_manager', False)

        # Permission mapping for has_permission method
        self._permission_map = {
            'system.settings': self.can_access_settings,
            'invoices.view': self.can_view_invoices,
            'invoices.add': self.can_add_invoices,
            'invoices.edit': self.can_edit_invoices,
            'invoices.delete': self.can_delete_invoices,
            'accounting.dashboard': self.can_access_accounting,
            'accounting.templates': self.can_access_templates,
            'accounting.connectors': self.can_access_connectors,
            'hr.access': self.can_access_hr,
            'hr.manager': self.is_hr_manager,
        }

    @property
    def is_active(self):
        return self.is_active_user

    def has_permission(self, module: str, permission: str = None) -> bool:
        """
        Check if user has a specific permission.
        Usage:
            user.has_permission('invoices', 'add')  # Check invoices.add
            user.has_permission('invoices.add')     # Also works
        """
        if permission is None and '.' in module:
            # Allow 'module.permission' format
            module, permission = module.split('.', 1)

        perm_key = f"{module}.{permission}"
        return self._permission_map.get(perm_key, False)

    def can_access_main_apps(self) -> bool:
        """Check if user can access main application modules (accounting, invoices, HR).

        Users without access to any main module should be redirected to their profile.
        """
        return (
            self.can_access_accounting or
            self.can_view_invoices or
            self.can_add_invoices or
            self.can_access_hr
        )


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    user_data = get_user(int(user_id))
    if user_data:
        return User(user_data)
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


@app.route('/api/auth/current-user')
def api_current_user():
    """Get current user info for UI."""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'id': current_user.id,
            'name': current_user.name,
            'email': current_user.email,
            'role': current_user.role_name,
            'permissions': {
                'can_add_invoices': current_user.can_add_invoices,
                'can_edit_invoices': current_user.can_edit_invoices,
                'can_delete_invoices': current_user.can_delete_invoices,
                'can_view_invoices': current_user.can_view_invoices,
                'can_access_accounting': current_user.can_access_accounting,
                'can_access_settings': current_user.can_access_settings,
                'can_access_connectors': current_user.can_access_connectors,
                'can_access_templates': current_user.can_access_templates
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

    # Verify current password
    user_data = authenticate_user(current_user.email, current_password)
    if not user_data:
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400

    # Set new password
    set_user_password(current_user.id, new_password)
    log_event('password_changed', 'User changed their password')

    return jsonify({'success': True, 'message': 'Password changed successfully'})


@app.route('/api/auth/update-profile', methods=['POST'])
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

    # Update user profile
    update_user(current_user.id, name=name, phone=phone)
    log_event('profile_updated', f'User updated their profile: name={name}')

    return jsonify({'success': True, 'message': 'Profile updated successfully', 'name': name})


@app.route('/api/users/<int:user_id>/set-password', methods=['POST'])
@login_required
def api_set_user_password(user_id):
    """Admin route to set a user's password."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    new_password = data.get('password', '')

    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

    user = get_user(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    set_user_password(user_id, new_password)
    log_event('admin_password_reset', f'Password reset for user {user["email"]}', 'user', user_id)

    return jsonify({'success': True, 'message': f'Password set for {user["name"]}'})


@app.route('/api/users/set-default-passwords', methods=['POST'])
@login_required
def api_set_default_passwords():
    """Set default password for all users without one."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json() or {}
    default_password = data.get('password', 'changeme123')

    updated_count = set_default_password_for_users(default_password)
    log_event('bulk_password_set', f'Set default password for {updated_count} users')

    return jsonify({
        'success': True,
        'message': f'Default password set for {updated_count} users',
        'updated_count': updated_count
    })


# ============== Event Log Routes ==============

@app.route('/api/events', methods=['GET'])
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

    events = get_user_events(
        limit=limit,
        offset=offset,
        user_id=user_id if user_id else None,
        event_type=event_type if event_type else None,
        entity_type=entity_type if entity_type else None
    )

    return jsonify(events)


@app.route('/api/events/types', methods=['GET'])
@login_required
def api_get_event_types():
    """Get distinct event types for filtering."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    return jsonify(get_event_types())


# ============== Health Check ==============

@app.route('/health')
def health_check():
    """Application health check endpoint for orchestrator probes.

    Returns 200 if all checks pass, 503 if any critical check fails.
    Does not require authentication. Also performs cache cleanup.
    """
    cleanup_expired_caches()
    checks = {}

    # Database check
    try:
        db_ok = ping_db()
        checks['database'] = db_ok
    except Exception as e:
        checks['database'] = False
        app_logger.error(f'Health check - database failed: {e}')

    # Google Drive check (if enabled)
    if DRIVE_ENABLED:
        try:
            drive_ok = check_drive_auth()
            checks['drive'] = drive_ok
        except Exception:
            checks['drive'] = False
    else:
        checks['drive'] = None  # Not configured

    # Determine overall status
    critical_checks = [checks.get('database', False)]
    status = 'healthy' if all(critical_checks) else 'unhealthy'
    http_code = 200 if status == 'healthy' else 503

    return jsonify({
        'status': status,
        'checks': checks,
        'service': 'bugetare',
        'version': '2025-01-16'
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
    """Redirect based on user permissions.

    Users with main app access go to /apps, others go to profile.
    """
    if current_user.can_access_main_apps():
        return redirect(url_for('apps_page'))
    return redirect(url_for('profile.profile_page'))


@app.route('/apps')
@login_required
def apps_page():
    """Show applications landing page (requires main app access)."""
    if not current_user.can_access_main_apps():
        flash('You do not have access to the Applications page.', 'warning')
        return redirect(url_for('profile.profile_page'))
    return render_template('core/apps.html')


@app.route('/add-invoice')
@login_required
def add_invoice():
    """Invoice distribution form page."""
    if not current_user.can_add_invoices:
        flash('You do not have permission to add invoices.', 'warning')
        return redirect(url_for('profile.profile_page'))
    return render_template('accounting/bugetare/index.html')


@app.route('/guide')
@login_required
def user_guide():
    """User guide and documentation page."""
    return render_template('core/guide.html')


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


@app.route('/api/companies')
@login_required
def api_companies():
    """Get list of companies."""
    return jsonify(get_companies())


@app.route('/api/brands/<company>')
@login_required
def api_brands(company):
    """Get brands for a company."""
    return jsonify(get_brands_for_company(company))


@app.route('/api/departments/<company>')
@login_required
def api_departments(company):
    """Get departments for a company."""
    return jsonify(get_departments_for_company(company))


@app.route('/api/subdepartments/<company>/<department>')
@login_required
def api_subdepartments(company, department):
    """Get subdepartments for a company and department."""
    return jsonify(get_subdepartments(company, department))


@app.route('/api/manager')
@login_required
def api_manager():
    """Get manager for a department, optionally filtered by brand."""
    company = request.args.get('company')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    return jsonify({'manager': get_manager(company, department, subdepartment, brand)})


@app.route('/api/submit', methods=['POST'])
@login_required
def submit_invoice():
    """Submit an invoice with its cost distribution."""
    if not current_user.can_add_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to add invoices'}), 403

    data = request.json

    try:
        # Save to database
        invoice_id = save_invoice(
            supplier=data['supplier'],
            invoice_template=data.get('invoice_template', ''),
            invoice_number=data['invoice_number'],
            invoice_date=data['invoice_date'],
            invoice_value=float(data['invoice_value']),
            currency=data.get('currency', 'RON'),
            drive_link=data.get('drive_link', ''),
            distributions=data['distributions'],
            value_ron=data.get('value_ron'),
            value_eur=data.get('value_eur'),
            exchange_rate=data.get('exchange_rate'),
            comment=data.get('comment', ''),
            payment_status=data.get('payment_status', 'not_paid'),
            subtract_vat=data.get('subtract_vat', False),
            vat_rate=data.get('vat_rate'),
            net_value=data.get('net_value')
        )

        # Send email notifications to responsables
        notifications_sent = 0
        if NOTIFICATIONS_ENABLED and is_smtp_configured():
            invoice_data = {
                'id': invoice_id,
                'invoice_number': data['invoice_number'],
                'supplier': data['supplier'],
                'invoice_date': data['invoice_date'],
                'invoice_value': float(data['invoice_value']),
                'currency': data.get('currency', 'RON'),
            }
            results = notify_invoice_allocations(invoice_data, data['distributions'])
            notifications_sent = sum(1 for r in results if r.get('success'))

        # Log the invoice creation
        log_event('invoice_created',
                  f'Created invoice {data["invoice_number"]} from {data["supplier"]}',
                  entity_type='invoice', entity_id=invoice_id)

        # Refresh connection pool after heavy operation to keep connections fresh
        refresh_connection_pool()

        return jsonify({
            'success': True,
            'message': f'Successfully saved {len(data["distributions"])} allocation(s)',
            'allocations': len(data['distributions']),
            'invoice_id': invoice_id,
            'notifications_sent': notifications_sent
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/data')
@login_required
def get_data():
    """Get existing data (returns empty - legacy endpoint)."""
    return jsonify([])


@app.route('/api/parse-invoice', methods=['POST'])
@login_required
def api_parse_invoice():
    """Parse an uploaded invoice using AI or template (with auto-detection)."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Check if a template ID was provided
    template_id = request.form.get('template_id')

    try:
        file_bytes = file.read()

        if template_id:
            # Use specific template-based parsing
            template = get_invoice_template(int(template_id))
            if not template:
                return jsonify({'success': False, 'error': 'Template not found'}), 404
            result = parse_invoice_with_template_from_bytes(file_bytes, file.filename, template)
            result['auto_detected_template'] = None
            result['auto_detected_template_id'] = None
        else:
            # Auto-detect template based on supplier VAT, fall back to AI parsing
            templates = get_all_invoice_templates()
            result = auto_detect_and_parse(file_bytes, file.filename, templates)

        # Drive upload is handled separately when user confirms allocation
        # via /api/drive/upload endpoint called from frontend during submission
        result['drive_link'] = None

        # Add currency conversion if we have invoice_value, currency, and invoice_date
        if CURRENCY_CONVERSION_ENABLED and result.get('invoice_value') and result.get('currency') and result.get('invoice_date'):
            try:
                conversion = get_eur_ron_conversion(
                    float(result['invoice_value']),
                    result['currency'],
                    result['invoice_date']
                )
                result['value_ron'] = conversion.get('value_ron')
                result['value_eur'] = conversion.get('value_eur')
                result['exchange_rate'] = conversion.get('exchange_rate')
            except Exception as conv_error:
                # Conversion failed, but don't fail the whole parsing
                print(f"Currency conversion failed: {conv_error}")
                result['value_ron'] = None
                result['value_eur'] = None
                result['exchange_rate'] = None
        else:
            result['value_ron'] = None
            result['value_eur'] = None
            result['exchange_rate'] = None

        # Refresh connection pool after parsing operation
        refresh_connection_pool()
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/parse-existing/<path:filepath>')
@login_required
def api_parse_existing(filepath):
    """Parse an existing invoice from the Invoices folder."""
    from config import INVOICES_DIR
    file_path = os.path.join(INVOICES_DIR, filepath)

    if not os.path.exists(file_path):
        return jsonify({'success': False, 'error': 'File not found'}), 404

    try:
        result = parse_invoice(file_path)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/invoices')
@login_required
def api_list_invoices():
    """List available invoices in the Invoices folder (including subfolders)."""
    from config import INVOICES_DIR
    if not os.path.exists(INVOICES_DIR):
        return jsonify([])

    files = []
    for root, dirs, filenames in os.walk(INVOICES_DIR):
        for f in filenames:
            if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                # Get relative path from INVOICES_DIR
                rel_path = os.path.relpath(os.path.join(root, f), INVOICES_DIR)
                files.append(rel_path)
    return jsonify(sorted(files))


# ============== GOOGLE DRIVE ENDPOINTS ==============

@app.route('/api/drive/status')
@login_required
def api_drive_status():
    """Check if Google Drive is configured and authenticated."""
    if not DRIVE_ENABLED:
        return jsonify({'enabled': False, 'error': 'Google Drive packages not installed'})
    try:
        authenticated = check_drive_auth()
        return jsonify({'enabled': True, 'authenticated': authenticated})
    except Exception as e:
        return jsonify({'enabled': True, 'authenticated': False, 'error': str(e)})


@app.route('/api/drive/upload', methods=['POST'])
@login_required
def api_drive_upload():
    """Upload invoice to Google Drive organized by Year/Month/Company/InvoiceNo."""
    if not DRIVE_ENABLED:
        return jsonify({'success': False, 'error': 'Google Drive not configured'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    invoice_date = request.form.get('invoice_date', '')
    company = request.form.get('company', 'Unknown Company')
    invoice_number = request.form.get('invoice_number', 'Unknown Invoice')

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    try:
        file_bytes = file.read()

        # Determine MIME type
        ext = os.path.splitext(file.filename)[1].lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png'
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')

        drive_link = upload_invoice_to_drive(
            file_bytes=file_bytes,
            filename=file.filename,
            invoice_date=invoice_date,
            company=company,
            invoice_number=invoice_number,
            mime_type=mime_type
        )

        # Refresh connection pool after Drive upload
        refresh_connection_pool()
        return jsonify({'success': True, 'drive_link': drive_link})
    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e), 'need_auth': True}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/drive/upload-attachment', methods=['POST'])
@login_required
def api_drive_upload_attachment():
    """Upload an attachment to the same Drive folder as an existing invoice file."""
    if not DRIVE_ENABLED:
        return jsonify({'success': False, 'error': 'Google Drive not configured'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    drive_link = request.form.get('drive_link', '')

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    if not drive_link:
        return jsonify({'success': False, 'error': 'drive_link is required'}), 400

    # Check file size (5MB limit)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    if file_size > 5 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File size exceeds 5MB limit'}), 400

    try:
        # Get the folder ID from the invoice's drive link
        folder_id = get_folder_id_from_file_link(drive_link)
        if not folder_id:
            return jsonify({'success': False, 'error': 'Could not determine folder from drive link'}), 400

        file_bytes = file.read()
        mime_type = file.content_type or 'application/octet-stream'
        compression_stats = None

        # Compress images using TinyPNG if enabled
        if IMAGE_COMPRESSION_ENABLED and compress_if_image:
            file_bytes, compression_stats = compress_if_image(file_bytes, file.filename, mime_type)

        # Upload attachment to the same folder
        attachment_link = upload_attachment_to_folder(
            file_bytes=file_bytes,
            filename=file.filename,
            folder_id=folder_id,
            mime_type=mime_type
        )

        if attachment_link:
            # Refresh connection pool after attachment upload
            refresh_connection_pool()
            result = {'success': True, 'attachment_link': attachment_link}
            if compression_stats:
                result['compression'] = compression_stats
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': 'Failed to upload attachment'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/drive/folder-link', methods=['GET'])
@login_required
def api_drive_folder_link():
    """Get the Google Drive folder link from a file's drive link."""
    if not DRIVE_ENABLED:
        return jsonify({'success': False, 'error': 'Google Drive not configured'}), 400

    drive_link = request.args.get('drive_link', '')
    if not drive_link:
        return jsonify({'success': False, 'error': 'drive_link is required'}), 400

    try:
        folder_link = get_folder_link_from_file(drive_link)
        if folder_link:
            return jsonify({'success': True, 'folder_link': folder_link})
        else:
            return jsonify({'success': False, 'error': 'Could not determine folder'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== ACCOUNTING INTERFACE ENDPOINTS ==============

@app.route('/accounting')
@login_required
def accounting():
    """Accounting dashboard for viewing all allocations."""
    if not current_user.can_access_accounting:
        flash('You do not have permission to access the accounting dashboard.', 'error')
        return redirect(url_for('add_invoice'))
    return render_template('accounting/bugetare/accounting.html')


# ============== CONNECTORS INTERFACE ENDPOINTS ==============
# NOTE: Connectors feature is disabled/under development
# Connector files (google_ads_connector.py, anthropic_connector.py) removed as dead code

@app.route('/buffer')
@login_required
def buffer():
    """Buffer page - currently disabled."""
    flash('Connectors feature is coming soon.', 'info')
    return redirect(url_for('accounting'))


@app.route('/connectors')
@login_required
def connectors():
    """Connectors page - currently disabled, shows coming soon message."""
    if not current_user.can_access_connectors:
        flash('You do not have permission to access connectors.', 'error')
        return redirect(url_for('accounting'))

    # Return a simple coming soon page
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connectors - Coming Soon</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-5">
            <div class="text-center">
                <i class="bi bi-plug display-1 text-muted mb-4 d-block"></i>
                <h2>Connectors - Coming Soon</h2>
                <p class="text-muted mb-4">
                    Automatic invoice import from Google Ads, Meta, and other platforms is under development.
                </p>
                <a href="/accounting" class="btn btn-primary">
                    <i class="bi bi-arrow-left"></i> Back to Accounting
                </a>
            </div>
        </div>
    </body>
    </html>
    '''


# Connector API endpoints - disabled for now
# Uncomment when connectors feature is ready

@app.route('/api/connectors', methods=['GET'])
@login_required
def api_get_connectors():
    """Get all connectors - DISABLED."""
    return jsonify({'error': 'Connectors feature is coming soon'}), 503


@app.route('/api/connectors/<int:connector_id>', methods=['GET'])
@login_required
def api_get_connector(connector_id):
    """Get a specific connector - DISABLED."""
    return jsonify({'error': 'Connectors feature is coming soon'}), 503


@app.route('/api/connectors', methods=['POST'])
@login_required
def api_create_connector():
    """Create a new connector - DISABLED."""
    return jsonify({'error': 'Connectors feature is coming soon'}), 503


@app.route('/api/connectors/<int:connector_id>', methods=['PUT'])
@login_required
def api_update_connector(connector_id):
    """Update a connector - DISABLED."""
    return jsonify({'error': 'Connectors feature is coming soon'}), 503


@app.route('/api/connectors/<int:connector_id>', methods=['DELETE'])
@login_required
def api_delete_connector(connector_id):
    """Delete a connector - DISABLED."""
    return jsonify({'error': 'Connectors feature is coming soon'}), 503


@app.route('/api/connectors/<int:connector_id>/sync', methods=['POST'])
@login_required
def api_sync_connector(connector_id):
    """Trigger a sync for a connector - DISABLED."""
    return jsonify({'error': 'Connectors feature is coming soon'}), 503


# ============== BUFFER API ENDPOINTS ==============
# Disabled - part of connectors feature

@app.route('/api/buffer/fetch/<source>', methods=['POST'])
@login_required
def api_buffer_fetch(source):
    """Fetch invoices from a connector source - DISABLED."""
    return jsonify({'error': 'Connectors feature is coming soon'}), 503


@app.route('/api/db/invoices')
@login_required
def api_db_invoices():
    """Get all invoices from database with pagination and optional filters.

    Query parameters:
    - limit: Max invoices to return (default 100)
    - offset: Pagination offset
    - company, department, subdepartment, brand: Filter by allocation fields
    - status, payment_status: Filter by invoice status
    - start_date, end_date: Filter by invoice date range
    - include_allocations: If "true", returns invoices with allocations embedded (optimized single query)
    """
    if not current_user.can_view_invoices:
        return jsonify({'error': 'You do not have permission to view invoices'}), 403

    limit = request.args.get('limit', 10000, type=int)  # High default to return all invoices
    offset = request.args.get('offset', 0, type=int)
    company = request.args.get('company')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    status = request.args.get('status')
    payment_status = request.args.get('payment_status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    include_allocations = request.args.get('include_allocations', 'false').lower() == 'true'

    if include_allocations:
        # Use optimized query that fetches invoices with allocations in single query
        invoices = get_invoices_with_allocations(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status
        )
    else:
        # Original behavior - invoices only, allocations fetched separately
        invoices = get_all_invoices(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status
        )
    return jsonify(invoices)


@app.route('/api/db/invoices/<int:invoice_id>')
@login_required
def api_db_invoice_detail(invoice_id):
    """Get invoice with all allocations."""
    if not current_user.can_view_invoices:
        return jsonify({'error': 'You do not have permission to view invoices'}), 403

    invoice = get_invoice_with_allocations(invoice_id)
    if invoice:
        return jsonify(invoice)
    return jsonify({'error': 'Invoice not found'}), 404


@app.route('/api/db/invoices/<int:invoice_id>', methods=['DELETE'])
@login_required
def api_db_delete_invoice(invoice_id):
    """Soft delete an invoice (move to bin)."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    if delete_invoice(invoice_id):
        log_event('invoice_deleted', f'Moved invoice ID {invoice_id} to bin',
                  entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True})
    return jsonify({'error': 'Invoice not found'}), 404


@app.route('/api/db/invoices/<int:invoice_id>/restore', methods=['POST'])
@login_required
def api_db_restore_invoice(invoice_id):
    """Restore a soft-deleted invoice from the bin."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to restore invoices'}), 403
    if restore_invoice(invoice_id):
        log_event('invoice_restored', f'Restored invoice ID {invoice_id} from bin',
                  entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True})
    return jsonify({'error': 'Invoice not found in bin'}), 404


@app.route('/api/db/invoices/<int:invoice_id>/permanent', methods=['DELETE'])
@login_required
def api_db_permanently_delete_invoice(invoice_id):
    """Permanently delete an invoice (cannot be restored). Also deletes from Google Drive."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    # Get drive_link before deleting the invoice
    drive_link = get_invoice_drive_link(invoice_id)

    if permanently_delete_invoice(invoice_id):
        # Delete from Google Drive if link exists and Drive is enabled
        drive_deleted = False
        if drive_link and DRIVE_ENABLED and delete_file_from_drive:
            drive_deleted = delete_file_from_drive(drive_link)
        log_event('invoice_permanently_deleted', f'Permanently deleted invoice ID {invoice_id}',
                  entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True, 'drive_deleted': drive_deleted})
    return jsonify({'error': 'Invoice not found'}), 404


@app.route('/api/db/invoices/bulk-delete', methods=['POST'])
@login_required
def api_db_bulk_delete_invoices():
    """Soft delete multiple invoices."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    data = request.json
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'error': 'No invoice IDs provided'}), 400
    count = bulk_soft_delete_invoices(invoice_ids)
    return jsonify({'success': True, 'deleted_count': count})


@app.route('/api/db/invoices/bulk-restore', methods=['POST'])
@login_required
def api_db_bulk_restore_invoices():
    """Restore multiple soft-deleted invoices."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to restore invoices'}), 403
    data = request.json
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'error': 'No invoice IDs provided'}), 400
    count = bulk_restore_invoices(invoice_ids)
    return jsonify({'success': True, 'restored_count': count})


@app.route('/api/db/invoices/bulk-permanent-delete', methods=['POST'])
@login_required
def api_db_bulk_permanently_delete_invoices():
    """Permanently delete multiple invoices (cannot be restored). Also deletes from Google Drive."""
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    data = request.json
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'error': 'No invoice IDs provided'}), 400

    # Get drive_links before deleting the invoices
    drive_links = get_invoice_drive_links(invoice_ids)

    count = bulk_permanently_delete_invoices(invoice_ids)

    # Delete from Google Drive if links exist and Drive is enabled
    drive_deleted_count = 0
    if drive_links and DRIVE_ENABLED and delete_files_from_drive:
        drive_deleted_count = delete_files_from_drive(drive_links)

    return jsonify({'success': True, 'deleted_count': count, 'drive_deleted_count': drive_deleted_count})


@app.route('/api/db/invoices/bin', methods=['GET'])
@login_required
def api_db_get_deleted_invoices():
    """Get all soft-deleted invoices (bin)."""
    if not current_user.can_view_invoices:
        return jsonify({'error': 'You do not have permission to view invoices'}), 403

    invoices = get_all_invoices(include_deleted=True, limit=500)
    return jsonify(invoices)


@app.route('/api/db/invoices/<int:invoice_id>', methods=['PUT'])
@login_required
def api_db_update_invoice(invoice_id):
    """Update an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.json

    try:
        # Get current invoice data to track status changes
        current_invoice = get_invoice_with_allocations(invoice_id)
        old_status = current_invoice.get('status') if current_invoice else None
        old_payment_status = current_invoice.get('payment_status') if current_invoice else None
        new_status = data.get('status')
        new_payment_status = data.get('payment_status')

        # Validate status change permissions based on min_role
        if new_status and new_status != old_status:
            if not user_can_set_status(current_user.role_name, new_status, 'invoice_status'):
                return jsonify({'success': False, 'error': f'Permission denied: Your role cannot set status to "{new_status}"'}), 403

        if new_payment_status and new_payment_status != old_payment_status:
            if not user_can_set_status(current_user.role_name, new_payment_status, 'payment_status'):
                return jsonify({'success': False, 'error': f'Permission denied: Your role cannot set payment status to "{new_payment_status}"'}), 403

        updated = update_invoice(
            invoice_id=invoice_id,
            supplier=data.get('supplier'),
            invoice_number=data.get('invoice_number'),
            invoice_date=data.get('invoice_date'),
            invoice_value=float(data['invoice_value']) if data.get('invoice_value') else None,
            currency=data.get('currency'),
            drive_link=data.get('drive_link'),
            comment=data.get('comment'),
            status=new_status,
            payment_status=new_payment_status,
            subtract_vat=data.get('subtract_vat'),
            vat_rate=float(data['vat_rate']) if data.get('vat_rate') else None,
            net_value=float(data['net_value']) if data.get('net_value') else None
        )
        if updated:
            # Log status change if it occurred
            if new_status is not None and old_status != new_status:
                log_event('status_changed',
                          f'Invoice #{current_invoice.get("invoice_number", invoice_id)} status changed from "{old_status}" to "{new_status}"',
                          entity_type='invoice', entity_id=invoice_id,
                          details={'old_status': old_status, 'new_status': new_status})
            # Log payment status change if it occurred
            if new_payment_status is not None and old_payment_status != new_payment_status:
                log_event('payment_status_changed',
                          f'Invoice #{current_invoice.get("invoice_number", invoice_id)} payment status changed from "{old_payment_status}" to "{new_payment_status}"',
                          entity_type='invoice', entity_id=invoice_id,
                          details={'old_payment_status': old_payment_status, 'new_payment_status': new_payment_status})
            # Log general update
            log_event('invoice_updated', f'Updated invoice ID {invoice_id}',
                      entity_type='invoice', entity_id=invoice_id)
            return jsonify({'success': True})
        return jsonify({'error': 'Invoice not found or no changes made'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/db/invoices/<int:invoice_id>/allocations', methods=['PUT'])
@login_required
def api_db_update_allocations(invoice_id):
    """Update all allocations for an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.json
    allocations = data.get('allocations', [])
    send_notification = data.get('send_notification', False)

    if not allocations:
        return jsonify({'success': False, 'error': 'At least one allocation is required'}), 400

    # Validate allocations sum to 100% (allow 0.1% tolerance for floating-point errors)
    total_percent = sum(float(a.get('allocation_percent', 0)) for a in allocations)
    if abs(total_percent - 100) > 0.1:
        return jsonify({'success': False, 'error': f'Allocations must sum to 100%, got {round(total_percent, 2)}%'}), 400

    try:
        update_invoice_allocations(invoice_id, allocations)

        # Send email notifications to responsables only if explicitly requested
        notifications_sent = 0
        if send_notification and NOTIFICATIONS_ENABLED and is_smtp_configured():
            invoice = get_invoice_with_allocations(invoice_id)
            if invoice:
                invoice_data = {
                    'id': invoice_id,
                    'invoice_number': invoice.get('invoice_number'),
                    'supplier': invoice.get('supplier'),
                    'invoice_date': invoice.get('invoice_date'),
                    'invoice_value': invoice.get('invoice_value'),
                    'currency': invoice.get('currency', 'RON'),
                }
                results = notify_invoice_allocations(invoice_data, allocations)
                notifications_sent = sum(1 for r in results if r.get('success'))

        log_event('allocations_updated', f'Updated allocations for invoice ID {invoice_id}',
                  entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True, 'notifications_sent': notifications_sent})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/allocations/<int:allocation_id>/comment', methods=['PUT'])
@login_required
def api_update_allocation_comment(allocation_id):
    """Update the comment for a specific allocation."""
    data = request.json
    comment = data.get('comment', '')

    try:
        updated = update_allocation_comment(allocation_id, comment)
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Allocation not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/invoices/<int:invoice_id>/drive-link', methods=['PUT'])
@login_required
def api_update_invoice_drive_link(invoice_id):
    """Update only the drive_link for an invoice (used after successful Drive upload)."""
    data = request.json
    drive_link = data.get('drive_link')

    if not drive_link:
        return jsonify({'success': False, 'error': 'drive_link is required'}), 400

    try:
        updated = update_invoice(invoice_id=invoice_id, drive_link=drive_link)
        if updated:
            return jsonify({'success': True})
        return jsonify({'error': 'Invoice not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/db/search')
@login_required
def api_db_search():
    """Search invoices by supplier or invoice number, respecting active filters."""
    if not current_user.can_view_invoices:
        return jsonify({'error': 'You do not have permission to view invoices'}), 403

    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])

    # Get filter parameters
    filters = {
        'company': request.args.get('company'),
        'department': request.args.get('department'),
        'subdepartment': request.args.get('subdepartment'),
        'brand': request.args.get('brand'),
        'status': request.args.get('status'),
        'payment_status': request.args.get('payment_status'),
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date'),
    }
    # Remove None values
    filters = {k: v for k, v in filters.items() if v}

    results = search_invoices(query, filters)
    return jsonify(results)


@app.route('/api/invoices/search')
@login_required
def api_invoices_search():
    """Search invoices by supplier, invoice number, or ID. Returns structured response."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)  # Max 50 results

    if len(query) < 2:
        return jsonify({'success': True, 'invoices': [], 'message': 'Query too short'})

    # Check if query is a numeric ID
    if query.isdigit():
        invoice = get_invoice_with_allocations(int(query))
        if invoice:
            return jsonify({'success': True, 'invoices': [invoice]})
        # Fall through to text search if not found by ID

    results = search_invoices(query)[:limit]
    return jsonify({'success': True, 'invoices': results})


@app.route('/api/db/check-invoice-number')
@login_required
def api_check_invoice_number():
    """Check if an invoice number already exists in the database."""
    invoice_number = request.args.get('invoice_number', '').strip()
    exclude_id = request.args.get('exclude_id', type=int)

    if not invoice_number:
        return jsonify({'exists': False, 'invoice': None})

    result = check_invoice_number_exists(invoice_number, exclude_id)
    return jsonify(result)


@app.route('/api/db/summary/company')
@login_required
def api_db_summary_company():
    """Get summary grouped by company."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = get_summary_by_company(start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@app.route('/api/db/summary/department')
@login_required
def api_db_summary_department():
    """Get summary grouped by department."""
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = get_summary_by_department(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@app.route('/api/db/summary/brand')
@login_required
def api_db_summary_brand():
    """Get summary grouped by brand (Linie de business)."""
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = get_summary_by_brand(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@app.route('/api/db/summary/supplier')
@login_required
def api_db_summary_supplier():
    """Get summary grouped by supplier."""
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = get_summary_by_supplier(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


# ============== COMPANY VAT MANAGEMENT ENDPOINTS ==============

@app.route('/api/companies-vat')
@login_required
def api_companies_vat():
    """Get all companies with their VAT numbers."""
    companies = get_companies_with_vat()
    return jsonify(companies)


@app.route('/api/companies-vat', methods=['POST'])
@login_required
def api_add_company_vat():
    """Add a new company with VAT."""
    data = request.json
    company = data.get('company', '').strip()
    vat = data.get('vat', '').strip()

    if not company or not vat:
        return jsonify({'success': False, 'error': 'Company and VAT are required'}), 400

    try:
        add_company_with_vat(company, vat)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/companies-vat/<company>', methods=['PUT'])
@login_required
def api_update_company_vat(company):
    """Update company VAT."""
    data = request.json
    vat = data.get('vat', '').strip()

    if not vat:
        return jsonify({'success': False, 'error': 'VAT is required'}), 400

    if update_company_vat(company, vat):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Company not found'}), 404


@app.route('/api/companies-vat/<company>', methods=['DELETE'])
@login_required
def api_delete_company_vat(company):
    """Delete a company."""
    if delete_company(company):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Company not found'}), 404


@app.route('/api/match-vat/<vat>')
@login_required
def api_match_vat(vat):
    """Match a VAT number to a company."""
    company = match_company_by_vat(vat)
    if company:
        return jsonify({'success': True, 'company': company})
    return jsonify({'success': False, 'company': None})


# ============== INVOICE TEMPLATES ENDPOINTS ==============

@app.route('/templates')
@login_required
def templates_page():
    """Invoice templates management page."""
    if not current_user.can_access_templates:
        flash('You do not have permission to access invoice templates.', 'error')
        return redirect(url_for('accounting'))
    return render_template('accounting/bugetare/templates.html')


@app.route('/api/templates')
@login_required
def api_get_templates():
    """Get all invoice templates."""
    templates = get_all_invoice_templates()
    return jsonify(templates)


@app.route('/api/templates/<int:template_id>')
@login_required
def api_get_template(template_id):
    """Get a specific invoice template."""
    template = get_invoice_template(template_id)
    if template:
        return jsonify(template)
    return jsonify({'error': 'Template not found'}), 404


@app.route('/api/templates', methods=['POST'])
@login_required
def api_create_template():
    """Create a new invoice template."""
    data = request.json

    try:
        template_id = save_invoice_template(
            name=data.get('name'),
            template_type=data.get('template_type', 'fixed'),
            supplier=data.get('supplier'),
            supplier_vat=data.get('supplier_vat'),
            customer_vat=data.get('customer_vat'),
            currency=data.get('currency', 'RON'),
            description=data.get('description'),
            invoice_number_regex=data.get('invoice_number_regex'),
            invoice_date_regex=data.get('invoice_date_regex'),
            invoice_value_regex=data.get('invoice_value_regex'),
            date_format=data.get('date_format', '%Y-%m-%d'),
            sample_invoice_path=data.get('sample_invoice_path'),
            supplier_regex=data.get('supplier_regex'),
            supplier_vat_regex=data.get('supplier_vat_regex'),
            customer_vat_regex=data.get('customer_vat_regex'),
            currency_regex=data.get('currency_regex')
        )
        return jsonify({'success': True, 'id': template_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates/<int:template_id>', methods=['PUT'])
@login_required
def api_update_template(template_id):
    """Update an invoice template."""
    data = request.json

    try:
        updated = update_invoice_template(
            template_id=template_id,
            name=data.get('name'),
            template_type=data.get('template_type'),
            supplier=data.get('supplier'),
            supplier_vat=data.get('supplier_vat'),
            customer_vat=data.get('customer_vat'),
            currency=data.get('currency'),
            description=data.get('description'),
            invoice_number_regex=data.get('invoice_number_regex'),
            invoice_date_regex=data.get('invoice_date_regex'),
            invoice_value_regex=data.get('invoice_value_regex'),
            date_format=data.get('date_format'),
            sample_invoice_path=data.get('sample_invoice_path'),
            supplier_regex=data.get('supplier_regex'),
            supplier_vat_regex=data.get('supplier_vat_regex'),
            customer_vat_regex=data.get('customer_vat_regex'),
            currency_regex=data.get('currency_regex')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
@login_required
def api_delete_template(template_id):
    """Delete an invoice template."""
    if delete_invoice_template(template_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Template not found'}), 404


@app.route('/api/templates/generate', methods=['POST'])
@login_required
def api_generate_template():
    """
    Generate a template from a sample invoice using AI.
    Upload a sample invoice and the AI will analyze it to generate:
    - Template name, supplier info, VAT numbers
    - Regex patterns for invoice number, date, and value extraction
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    try:
        file_bytes = file.read()
        result = generate_template_from_invoice(file_bytes, file.filename)

        # Remove internal fields before returning
        extracted_text = result.pop('_extracted_text', None)
        ai_generated = result.pop('_ai_generated', None)
        error = result.pop('_error', None)
        raw_response = result.pop('_raw_response', None)

        response_data = {
            'success': True,
            'template': result,
            'extracted_text': extracted_text[:1000] if extracted_text else None
        }

        if error:
            response_data['warning'] = f'Partial result due to parsing error: {error}'

        return jsonify(response_data)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== SETTINGS INTERFACE ENDPOINTS ==============

@app.route('/settings')
@login_required
def settings():
    """Settings page for managing users and permissions."""
    if not current_user.can_access_settings:
        flash('You do not have permission to access settings.', 'error')
        return redirect(url_for('index'))
    return render_template('core/settings.html')


# ============== ROLE MANAGEMENT ENDPOINTS ==============

@app.route('/api/roles', methods=['GET'])
@login_required
def api_get_roles():
    """Get all roles with their permissions."""
    roles = get_all_roles()
    # Add permissions list to each role
    for role in roles:
        role['permissions'] = get_role_permissions_list(role['id'])
    return jsonify(roles)


@app.route('/api/roles/<int:role_id>', methods=['GET'])
@login_required
def api_get_role(role_id):
    """Get a specific role."""
    role = get_role(role_id)
    if role:
        return jsonify(role)
    return jsonify({'error': 'Role not found'}), 404


@app.route('/api/roles', methods=['POST'])
@login_required
def api_create_role():
    """Create a new role."""
    data = request.get_json()

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    try:
        role_id = save_role(
            name=name,
            description=data.get('description'),
            can_add_invoices=data.get('can_add_invoices', False),
            can_edit_invoices=data.get('can_edit_invoices', False),
            can_delete_invoices=data.get('can_delete_invoices', False),
            can_view_invoices=data.get('can_view_invoices', False),
            can_access_accounting=data.get('can_access_accounting', False),
            can_access_settings=data.get('can_access_settings', False),
            can_access_connectors=data.get('can_access_connectors', False),
            can_access_templates=data.get('can_access_templates', False),
            can_access_hr=data.get('can_access_hr', False),
            is_hr_manager=data.get('is_hr_manager', False)
        )
        return jsonify({'success': True, 'id': role_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/roles/<int:role_id>', methods=['PUT'])
def api_update_role(role_id):
    """Update a role."""
    data = request.get_json()

    try:
        updated = update_role(
            role_id=role_id,
            name=data.get('name'),
            description=data.get('description'),
            can_add_invoices=data.get('can_add_invoices'),
            can_edit_invoices=data.get('can_edit_invoices'),
            can_delete_invoices=data.get('can_delete_invoices'),
            can_view_invoices=data.get('can_view_invoices'),
            can_access_accounting=data.get('can_access_accounting'),
            can_access_settings=data.get('can_access_settings'),
            can_access_connectors=data.get('can_access_connectors'),
            can_access_templates=data.get('can_access_templates'),
            can_access_hr=data.get('can_access_hr'),
            is_hr_manager=data.get('is_hr_manager')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Role not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/roles/<int:role_id>', methods=['DELETE'])
def api_delete_role(role_id):
    """Delete a role."""
    try:
        if delete_role(role_id):
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Role not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============== PERMISSIONS ENDPOINTS ==============

@app.route('/api/permissions', methods=['GET'])
@login_required
def api_get_permissions():
    """Get all permissions grouped by module."""
    modules = get_all_permissions()
    return jsonify({'modules': modules})


@app.route('/api/permissions/flat', methods=['GET'])
@login_required
def api_get_permissions_flat():
    """Get all permissions as flat list."""
    permissions = get_permissions_flat()
    return jsonify({'permissions': permissions})


@app.route('/api/roles/<int:role_id>/permissions', methods=['GET'])
@login_required
def api_get_role_perms(role_id):
    """Get permissions for a specific role."""
    perms = get_role_permissions_list(role_id)
    return jsonify({'permissions': perms})


@app.route('/api/roles/<int:role_id>/permissions', methods=['PUT'])
@login_required
def api_set_role_perms(role_id):
    """Set permissions for a role. Body: {permissions: ['module.permission', ...]}"""
    data = request.get_json()
    permissions = data.get('permissions', [])

    try:
        set_role_permissions(role_id, permissions)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== PERMISSION MATRIX (v2) ENDPOINTS ==============

@app.route('/api/permissions/matrix', methods=['GET'])
@login_required
def api_get_permission_matrix():
    """Get permission matrix structure with modules, entities, actions and roles."""
    from database import get_permission_matrix, get_all_role_permissions_v2
    matrix = get_permission_matrix()
    role_perms = get_all_role_permissions_v2()
    return jsonify({
        'modules': matrix['modules'],
        'roles': matrix['roles'],
        'role_permissions': role_perms
    })


@app.route('/api/roles/<int:role_id>/permissions/v2', methods=['GET'])
@login_required
def api_get_role_perms_v2(role_id):
    """Get v2 permissions for a specific role."""
    from database import get_role_permissions_v2
    perms = get_role_permissions_v2(role_id)
    return jsonify({'permissions': perms})


@app.route('/api/roles/<int:role_id>/permissions/v2', methods=['PUT'])
@login_required
def api_set_role_perms_v2(role_id):
    """
    Set v2 permissions for a role.
    Body: {permissions: {permission_id: {scope: 'all'} or {granted: true}}}
    """
    from database import set_role_permissions_v2_bulk
    data = request.get_json()
    permissions = data.get('permissions', {})

    try:
        set_role_permissions_v2_bulk(role_id, permissions)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/permissions/v2/<int:permission_id>/role/<int:role_id>', methods=['PUT'])
@login_required
def api_set_single_permission_v2(permission_id, role_id):
    """
    Set a single permission for a role.
    Body: {scope: 'all'} or {granted: true}
    """
    from database import set_role_permission_v2
    data = request.get_json()

    try:
        set_role_permission_v2(
            role_id=role_id,
            permission_id=permission_id,
            scope=data.get('scope'),
            granted=data.get('granted')
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== THEME SETTINGS ENDPOINTS ==============

@app.route('/api/themes', methods=['GET'])
@login_required
def api_get_themes():
    """Get all themes."""
    from database import get_all_themes
    themes = get_all_themes()
    return jsonify({'themes': themes})


@app.route('/api/themes/active', methods=['GET'])
def api_get_active_theme():
    """Get the active theme (public endpoint for CSS loading)."""
    from database import get_active_theme
    theme = get_active_theme()
    return jsonify({'theme': theme})


@app.route('/api/themes/<int:theme_id>', methods=['GET'])
@login_required
def api_get_theme(theme_id):
    """Get a specific theme."""
    from database import get_theme_by_id
    theme = get_theme_by_id(theme_id)
    if theme:
        return jsonify({'theme': theme})
    return jsonify({'error': 'Theme not found'}), 404


@app.route('/api/themes', methods=['POST'])
@login_required
def api_create_theme():
    """Create a new theme."""
    data = request.get_json()
    theme_name = data.get('theme_name', '').strip()
    settings = data.get('settings', {})
    is_active = data.get('is_active', False)

    if not theme_name:
        return jsonify({'error': 'Theme name is required'}), 400

    from database import save_theme
    theme = save_theme(None, theme_name, settings, is_active)
    return jsonify({'success': True, 'theme': theme})


@app.route('/api/themes/<int:theme_id>', methods=['PUT'])
@login_required
def api_update_theme(theme_id):
    """Update a theme."""
    data = request.get_json()
    theme_name = data.get('theme_name', '').strip()
    settings = data.get('settings', {})
    is_active = data.get('is_active')

    if not theme_name:
        return jsonify({'error': 'Theme name is required'}), 400

    from database import save_theme
    theme = save_theme(theme_id, theme_name, settings, is_active)
    if theme:
        return jsonify({'success': True, 'theme': theme})
    return jsonify({'error': 'Theme not found'}), 404


@app.route('/api/themes/<int:theme_id>', methods=['DELETE'])
@login_required
def api_delete_theme(theme_id):
    """Delete a theme."""
    from database import delete_theme
    if delete_theme(theme_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Cannot delete active or only theme'}), 400


@app.route('/api/themes/<int:theme_id>/activate', methods=['POST'])
@login_required
def api_activate_theme(theme_id):
    """Activate a theme."""
    from database import activate_theme
    if activate_theme(theme_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to activate theme'}), 500


# ============== MODULE MENU ENDPOINTS ==============

@app.route('/api/module-menu', methods=['GET'])
@login_required
def api_get_module_menu():
    """Get module menu items filtered by user permissions."""
    from database import get_module_menu_items
    items = get_module_menu_items(include_hidden=False)

    # Filter modules based on user permissions
    # Map module_key to permission check
    permission_map = {
        'accounting': lambda u: u.can_access_accounting or u.can_view_invoices or u.can_add_invoices,
        'hr': lambda u: u.can_access_hr,
        'settings': lambda u: u.can_access_settings,
    }

    def user_can_access_module(module_key):
        """Check if current user can access the module."""
        check = permission_map.get(module_key)
        if check:
            return check(current_user)
        # For modules not in the map (e.g., coming_soon), show them
        return True

    # Filter active modules by permission, keep coming_soon modules
    filtered_items = []
    for item in items:
        if item.get('status') == 'coming_soon':
            # Always show coming soon modules
            filtered_items.append(item)
        elif user_can_access_module(item.get('module_key', '')):
            filtered_items.append(item)

    return jsonify({'items': filtered_items})


@app.route('/api/module-menu/all', methods=['GET'])
@login_required
def api_get_all_module_menu():
    """Get all module menu items including hidden (admin endpoint)."""
    from database import get_all_module_menu_items_flat
    items = get_all_module_menu_items_flat()
    return jsonify({'items': items})


@app.route('/api/module-menu/<int:item_id>', methods=['GET'])
@login_required
def api_get_module_menu_item(item_id):
    """Get a specific module menu item."""
    from database import get_module_menu_item_by_id
    item = get_module_menu_item_by_id(item_id)
    if item:
        return jsonify({'item': item})
    return jsonify({'error': 'Item not found'}), 404


@app.route('/api/module-menu', methods=['POST'])
@login_required
def api_create_module_menu_item():
    """Create a new module menu item."""
    data = request.get_json()

    if not data.get('name') or not data.get('module_key'):
        return jsonify({'error': 'Name and module_key are required'}), 400

    from database import save_module_menu_item
    item = save_module_menu_item(None, data)
    return jsonify({'success': True, 'item': item})


@app.route('/api/module-menu/<int:item_id>', methods=['PUT'])
@login_required
def api_update_module_menu_item(item_id):
    """Update a module menu item."""
    data = request.get_json()

    if not data.get('name') or not data.get('module_key'):
        return jsonify({'error': 'Name and module_key are required'}), 400

    from database import save_module_menu_item
    item = save_module_menu_item(item_id, data)
    if item:
        return jsonify({'success': True, 'item': item})
    return jsonify({'error': 'Item not found'}), 404


@app.route('/api/module-menu/<int:item_id>', methods=['DELETE'])
@login_required
def api_delete_module_menu_item(item_id):
    """Delete a module menu item."""
    from database import delete_module_menu_item
    if delete_module_menu_item(item_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to delete item'}), 400


@app.route('/api/module-menu/reorder', methods=['POST'])
@login_required
def api_reorder_module_menu():
    """Reorder module menu items."""
    data = request.get_json()
    items = data.get('items', [])

    if not items:
        return jsonify({'error': 'Items array is required'}), 400

    from database import update_module_menu_order
    if update_module_menu_order(items):
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to reorder items'}), 500


# ============== USER MANAGEMENT ENDPOINTS ==============

@app.route('/api/users', methods=['GET'])
def api_get_users():
    """Get all users with role information."""
    users = get_all_users()
    return jsonify(users)


@app.route('/api/users/<int:user_id>', methods=['GET'])
def api_get_user(user_id):
    """Get a specific user with role information."""
    user = get_user(user_id)
    if user:
        return jsonify(user)
    return jsonify({'error': 'User not found'}), 404


@app.route('/api/users', methods=['POST'])
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
        user_id = save_user(
            name=name,
            email=email,
            phone=phone if phone else None,
            role_id=data.get('role_id'),
            is_active=data.get('is_active', True)
        )
        # Set password if provided
        if password:
            from database import set_user_password
            set_user_password(user_id, password)
        return jsonify({'success': True, 'id': user_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/users/<int:user_id>', methods=['PUT'])
def api_update_user(user_id):
    """Update a user."""
    data = request.get_json()

    try:
        updated = update_user(
            user_id=user_id,
            name=data.get('name'),
            email=data.get('email'),
            phone=data.get('phone'),
            role_id=data.get('role_id'),
            is_active=data.get('is_active'),
            notify_on_allocation=data.get('notify_on_allocation')
        )
        if updated:
            # Update password if provided
            password = data.get('password', '').strip() if data.get('password') else ''
            if password:
                from database import set_user_password
                set_user_password(user_id, password)
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'User not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    """Delete a user."""
    if delete_user(user_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'User not found'}), 404


@app.route('/api/users/bulk-delete', methods=['POST'])
@login_required
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

    deleted_count = delete_users_bulk(user_ids)
    return jsonify({'success': True, 'deleted': deleted_count})


# Employees API endpoints (uses users table)
@app.route('/api/employees', methods=['GET'])
def api_get_employees():
    """Get all users as employees."""
    users = get_all_users()
    # Map department field to departments for backwards compatibility
    for user in users:
        user['departments'] = user.get('department')
    return jsonify(users)


@app.route('/api/employees/<int:employee_id>', methods=['GET'])
def api_get_employee(employee_id):
    """Get a specific user as employee."""
    user = get_user(employee_id)
    if user:
        user['departments'] = user.get('department')
        return jsonify(user)
    return jsonify({'error': 'Employee not found'}), 404


@app.route('/api/employees', methods=['POST'])
def api_create_employee():
    """Create a new user/employee."""
    data = request.get_json()

    name = data.get('name', '').strip()
    email = data.get('email', '').strip() if data.get('email') else None
    phone = data.get('phone', '').strip() if data.get('phone') else None
    # Support both 'departments' (legacy) and 'department' field names
    department = data.get('department') or data.get('departments')
    department = department.strip() if department else None
    subdepartment = data.get('subdepartment', '').strip() if data.get('subdepartment') else None
    company = data.get('company', '').strip() if data.get('company') else None
    brand = data.get('brand', '').strip() if data.get('brand') else None

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    try:
        user_id = save_user(
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
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/employees/<int:employee_id>', methods=['PUT'])
def api_update_employee(employee_id):
    """Update a user/employee."""
    data = request.get_json()

    # Support both 'departments' (legacy) and 'department' field names
    department = data.get('department') if data.get('department') is not None else data.get('departments')

    try:
        updated = update_user(
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
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/employees/<int:employee_id>', methods=['DELETE'])
def api_delete_employee(employee_id):
    """Delete a user/employee."""
    if delete_user(employee_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Employee not found'}), 404


# VAT Rates API endpoints
@app.route('/api/vat-rates', methods=['GET'])
def api_get_vat_rates():
    """Get all VAT rates."""
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    rates = get_vat_rates(active_only=active_only)
    return jsonify(rates)


@app.route('/api/vat-rates', methods=['POST'])
def api_create_vat_rate():
    """Create a new VAT rate."""
    data = request.get_json()

    name = data.get('name', '').strip()
    rate = data.get('rate')

    if not name or rate is None:
        return jsonify({'error': 'Name and rate are required'}), 400

    try:
        rate_id = add_vat_rate(
            name=name,
            rate=float(rate),
            is_default=data.get('is_default', False),
            is_active=data.get('is_active', True)
        )
        return jsonify({'success': True, 'id': rate_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/vat-rates/<int:rate_id>', methods=['PUT'])
def api_update_vat_rate(rate_id):
    """Update a VAT rate."""
    data = request.get_json()

    try:
        updated = update_vat_rate(
            rate_id=rate_id,
            name=data.get('name'),
            rate=float(data['rate']) if data.get('rate') is not None else None,
            is_default=data.get('is_default'),
            is_active=data.get('is_active')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'VAT rate not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/vat-rates/<int:rate_id>', methods=['DELETE'])
def api_delete_vat_rate(rate_id):
    """Delete a VAT rate."""
    if delete_vat_rate(rate_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'VAT rate not found'}), 404


# Dropdown Options API endpoints
@app.route('/api/dropdown-options', methods=['GET'])
@login_required
def api_get_dropdown_options():
    """Get dropdown options, optionally filtered by type."""
    dropdown_type = request.args.get('type')
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    options = get_dropdown_options(dropdown_type, active_only)
    return jsonify(options)


@app.route('/api/dropdown-options', methods=['POST'])
@login_required
def api_add_dropdown_option():
    """Add a new dropdown option."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    try:
        option_id = add_dropdown_option(
            dropdown_type=data['dropdown_type'],
            value=data['value'],
            label=data['label'],
            color=data.get('color'),
            opacity=data.get('opacity', 0.7),
            sort_order=data.get('sort_order', 0),
            is_active=data.get('is_active', True)
        )
        return jsonify({'success': True, 'id': option_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/dropdown-options/<int:option_id>', methods=['PUT'])
@login_required
def api_update_dropdown_option(option_id):
    """Update a dropdown option."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    try:
        success = update_dropdown_option(
            option_id=option_id,
            value=data.get('value'),
            label=data.get('label'),
            color=data.get('color'),
            opacity=data.get('opacity'),
            sort_order=data.get('sort_order'),
            is_active=data.get('is_active')
        )
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Option not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/dropdown-options/<int:option_id>', methods=['DELETE'])
@login_required
def api_delete_dropdown_option(option_id):
    """Delete a dropdown option."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    if delete_dropdown_option(option_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Option not found'}), 404


# Notification Settings API endpoints
@app.route('/api/notification-settings', methods=['GET'])
def api_get_notification_settings():
    """Get all notification settings."""
    settings = get_notification_settings()
    return jsonify(settings)


@app.route('/api/notification-settings', methods=['POST'])
def api_save_notification_settings():
    """Save notification settings."""
    data = request.get_json()

    try:
        save_notification_settings_bulk(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/notification-logs', methods=['GET'])
def api_get_notification_logs():
    """Get notification logs with optional filters."""
    responsable_id = request.args.get('responsable_id', type=int)
    status = request.args.get('status')
    limit = request.args.get('limit', 100, type=int)

    logs = get_notification_logs(
        responsable_id=responsable_id,
        status=status,
        limit=limit
    )
    return jsonify(logs)


@app.route('/api/notification-settings/test', methods=['POST'])
def api_test_email():
    """Send a test email to verify SMTP configuration."""
    if not NOTIFICATIONS_ENABLED:
        return jsonify({'success': False, 'error': 'Notifications module not available'}), 500

    data = request.get_json()
    to_email = data.get('email')

    if not to_email:
        return jsonify({'success': False, 'error': 'Email address is required'}), 400

    success, error_message = send_test_email(to_email)

    if success:
        return jsonify({'success': True, 'message': f'Test email sent to {to_email}'})
    else:
        return jsonify({'success': False, 'error': error_message}), 500


# ============== Default Column Configuration API ==============

@app.route('/api/default-columns', methods=['GET'])
@login_required
def api_get_default_columns():
    """Get default column configurations for all tabs."""
    settings = get_notification_settings()
    return jsonify({
        'accounting': settings.get('default_columns_accounting'),
        'company': settings.get('default_columns_company'),
        'department': settings.get('default_columns_department'),
        'brand': settings.get('default_columns_brand')
    })


@app.route('/api/default-columns', methods=['POST'])
@login_required
def api_set_default_columns():
    """Set default column configuration (admin only)."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    tab = data.get('tab')  # 'accounting', 'company', 'department', 'brand'
    config = data.get('config')  # JSON string of column config

    if not tab or not config:
        return jsonify({'success': False, 'error': 'Tab and config are required'}), 400

    valid_tabs = ['accounting', 'company', 'department', 'brand']
    if tab not in valid_tabs:
        return jsonify({'success': False, 'error': f'Invalid tab. Must be one of: {valid_tabs}'}), 400

    try:
        setting_key = f'default_columns_{tab}'
        save_notification_setting(setting_key, config)
        log_event('default_columns_set', f'Set default column config for {tab} tab')
        return jsonify({'success': True, 'message': f'Default columns set for {tab} tab'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




# ============================================================================
# Companies Configuration API
# ============================================================================

@app.route('/api/companies-config', methods=['GET'])
def api_get_companies_config():
    """Get all companies for configuration."""
    companies = get_all_companies()
    return jsonify(companies)


@app.route('/api/companies-config', methods=['POST'])
def api_create_company_config():
    """Create a new company."""
    data = request.get_json()
    if not data or not data.get('company'):
        return jsonify({'success': False, 'error': 'Company name is required'}), 400

    try:
        company_id = save_company(
            company=data.get('company'),
            vat=data.get('vat')
        )
        return jsonify({'success': True, 'id': company_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/companies-config/<int:company_id>', methods=['GET'])
def api_get_company_config(company_id):
    """Get a specific company."""
    company = get_company(company_id)
    if not company:
        return jsonify({'success': False, 'error': 'Company not found'}), 404
    return jsonify(company)


@app.route('/api/companies-config/<int:company_id>', methods=['PUT'])
def api_update_company_config(company_id):
    """Update a company."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    try:
        success = update_company(
            company_id=company_id,
            company=data.get('company'),
            vat=data.get('vat')
        )
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Company not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/companies-config/<int:company_id>', methods=['DELETE'])
def api_delete_company_config(company_id):
    """Delete a company."""
    success = delete_company_db(company_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Company not found'}), 404


# ============================================================================
# Department Structure API
# ============================================================================

@app.route('/api/department-structures', methods=['GET'])
def api_get_department_structures():
    """Get all department structures."""
    structures = get_all_department_structures()
    return jsonify(structures)


@app.route('/api/department-structures', methods=['POST'])
def api_create_department_structure():
    """Create a new department structure."""
    data = request.get_json()
    if not data or not data.get('company') or not data.get('department'):
        return jsonify({'success': False, 'error': 'Company and department are required'}), 400

    structure_id = save_department_structure(
        company=data.get('company'),
        department=data.get('department'),
        brand=data.get('brand'),
        subdepartment=data.get('subdepartment'),
        manager=data.get('manager'),
        marketing=data.get('marketing'),
        responsable_id=data.get('responsable_id'),
        manager_ids=data.get('manager_ids'),
        marketing_ids=data.get('marketing_ids'),
        cc_email=data.get('cc_email')
    )
    return jsonify({'success': True, 'id': structure_id})


@app.route('/api/department-structures/<int:structure_id>', methods=['GET'])
def api_get_department_structure(structure_id):
    """Get a specific department structure."""
    structure = get_department_structure(structure_id)
    if not structure:
        return jsonify({'success': False, 'error': 'Department structure not found'}), 404
    return jsonify(structure)


@app.route('/api/department-structures/<int:structure_id>', methods=['PUT'])
def api_update_department_structure(structure_id):
    """Update a department structure."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    success = update_department_structure(
        structure_id=structure_id,
        company=data.get('company'),
        department=data.get('department'),
        brand=data.get('brand'),
        subdepartment=data.get('subdepartment'),
        manager=data.get('manager'),
        marketing=data.get('marketing'),
        responsable_id=data.get('responsable_id'),
        manager_ids=data.get('manager_ids'),
        marketing_ids=data.get('marketing_ids'),
        cc_email=data.get('cc_email')
    )
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Department structure not found'}), 404


@app.route('/api/department-structures/<int:structure_id>', methods=['DELETE'])
def api_delete_department_structure(structure_id):
    """Delete a department structure."""
    success = delete_department_structure(structure_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Department structure not found'}), 404


@app.route('/api/department-structures/unique-departments', methods=['GET'])
def api_get_unique_departments():
    """Get unique departments for a company."""
    company = request.args.get('company', '')
    departments = get_unique_departments(company)
    return jsonify(departments)


@app.route('/api/department-structures/unique-brands', methods=['GET'])
def api_get_unique_brands():
    """Get unique brands for a company."""
    company = request.args.get('company', '')
    brands = get_unique_brands(company)
    return jsonify(brands)


# ============================================================================
# Bulk Invoice Processor
# ============================================================================

@app.route('/bulk')
@login_required
def bulk_processor():
    """Bulk invoice processor page for uploading and analyzing multiple invoices."""
    if not current_user.can_view_invoices:
        flash('You do not have permission to access the bulk processor.', 'error')
        return redirect(url_for('add_invoice'))
    return render_template('accounting/bugetare/bulk.html')


@app.route('/api/bulk/process', methods=['POST'])
@login_required
def api_bulk_process():
    """Process multiple uploaded invoices and return summary."""
    from accounting.bugetare.bulk_processor import process_bulk_invoices

    if 'files[]' not in request.files:
        return jsonify({'success': False, 'error': 'No files uploaded'}), 400

    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'success': False, 'error': 'No files selected'}), 400

    # Collect file data
    file_data = []
    for f in files:
        if f.filename and f.filename.lower().endswith('.pdf'):
            file_bytes = f.read()
            file_data.append((file_bytes, f.filename))

    if not file_data:
        return jsonify({'success': False, 'error': 'No valid PDF files found'}), 400

    try:
        report = process_bulk_invoices(file_data)
        # Refresh connection pool after bulk processing
        refresh_connection_pool()
        return jsonify({
            'success': True,
            'report': {
                'invoices': [{
                    'filename': inv.get('filename'),
                    'invoice_number': inv.get('invoice_number'),
                    'invoice_date': inv.get('invoice_date'),
                    'invoice_value': inv.get('invoice_value'),
                    'currency': inv.get('currency'),
                    'supplier': inv.get('supplier'),
                    'customer_vat': inv.get('customer_vat'),
                    'customer_name': inv.get('customer_name'),
                    'invoice_type': inv.get('invoice_type'),
                    'campaigns': inv.get('campaigns', {})
                } for inv in report.get('invoices', [])],
                'total': report.get('total', 0),
                'count': report.get('count', 0),
                'currency': report.get('currency', 'RON'),
                'by_month': report.get('by_month', {}),
                'by_campaign': report.get('by_campaign', {}),
                'by_supplier': report.get('by_supplier', {})
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bulk/export', methods=['POST'])
@login_required
def api_bulk_export():
    """Export bulk processing results to Excel."""
    from accounting.bugetare.bulk_processor import generate_excel_report, process_bulk_invoices

    if 'files[]' not in request.files:
        return jsonify({'success': False, 'error': 'No files uploaded'}), 400

    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'success': False, 'error': 'No files selected'}), 400

    # Collect file data
    file_data = []
    for f in files:
        if f.filename and f.filename.lower().endswith('.pdf'):
            file_bytes = f.read()
            file_data.append((file_bytes, f.filename))

    if not file_data:
        return jsonify({'success': False, 'error': 'No valid PDF files found'}), 400

    try:
        report = process_bulk_invoices(file_data)
        excel_bytes = generate_excel_report(report)

        # Generate filename with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'Invoice_Report_{timestamp}.xlsx'

        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bulk/export-json', methods=['POST'])
@login_required
def api_bulk_export_json():
    """Export bulk processing results from JSON data to Excel."""
    from accounting.bugetare.bulk_processor import generate_excel_report
    from datetime import datetime as dt

    data = request.get_json()
    if not data or 'report' not in data:
        return jsonify({'success': False, 'error': 'No report data provided'}), 400

    try:
        # Reconstruct report data with date objects for Excel
        report = data['report']

        # Parse date strings back to datetime objects for invoices
        for inv in report.get('invoices', []):
            if inv.get('invoice_date'):
                try:
                    inv['date_parsed'] = dt.strptime(inv['invoice_date'].split('T')[0], '%Y-%m-%d')
                except:
                    inv['date_parsed'] = None

        excel_bytes = generate_excel_report(report)

        timestamp = dt.now().strftime('%Y%m%d_%H%M%S')
        filename = f'Invoice_Report_{timestamp}.xlsx'

        return Response(
            excel_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bulk/match-campaigns', methods=['POST'])
@login_required
def api_bulk_match_campaigns():
    """Use AI to match campaign names between source and target invoices."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    source_campaigns = data.get('source_campaigns', [])
    target_campaigns = data.get('target_campaigns', [])

    if not source_campaigns or not target_campaigns:
        return jsonify({'success': False, 'error': 'Both source and target campaigns are required'}), 400

    try:
        # Use AI to match campaigns
        mapping = match_campaigns_with_ai(source_campaigns, target_campaigns)
        return jsonify({
            'success': True,
            'mapping': mapping  # {target_index: source_index}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bulk/group-similar-items', methods=['POST'])
@login_required
def api_bulk_group_similar_items():
    """Use AI to group similar items that should be merged together.

    Groups items by same item type (Leads, Traffic, etc.) AND same brand/product.
    Items from different invoice positions can be grouped if they represent the same campaign type.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    items = data.get('items', [])
    if len(items) < 2:
        return jsonify({'success': True, 'groups': []})

    try:
        import anthropic
        client = anthropic.Anthropic()

        # Create numbered list of items for AI
        items_list = "\n".join([f"{i}: {item}" for i, item in enumerate(items)])

        prompt = f"""Analyze these campaign/item names and group together items that should be merged because they represent the SAME type of campaign/service for the SAME brand/product.

Items to analyze:
{items_list}

GROUPING RULES:
1. Group items that have the SAME item type (e.g., "Traffic", "Leads", "Conversions", "Brand", etc.) AND the SAME brand/product (e.g., "Mazda", "Volvo", "MG", etc.)
2. Items from different invoice line positions CAN be grouped together if they represent the same campaign type
3. Examples of items that SHOULD be grouped together:
   - "[CA] Traffic - Mazda CX60" and "[CA] Traffic - Mazda CX80" (same type: Traffic, same brand: Mazda)
   - "[CA] Leads - Modele Volvo 0 km" and "[CA] Leads - Volvo EX30" (same type: Leads, same brand: Volvo)
4. Examples of items that should NOT be grouped:
   - "[CA] Leads - Mazda CX80" and "[CA] Traffic - Mazda CX60" (different types: Leads vs Traffic)
   - "[CA] Leads - Mazda CX80" and "[CA] Leads - Volvo EX30" (different brands: Mazda vs Volvo)
5. If an item has no clear brand/product match with others, leave it ungrouped
6. Be conservative - only group items you are confident should be merged

Return ONLY a JSON array of groups, where each group is an array of item indices that should be merged.
Only include groups with 2+ items. Items that don't belong to any group should be omitted.

Example response format:
[[0, 3], [1, 4, 7]]

This means: items 0 and 3 should be merged together, items 1, 4, and 7 should be merged together."""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text.strip()

        # Parse the JSON response
        import json
        import re

        # Extract JSON array from response (handle markdown code blocks)
        json_match = re.search(r'\[[\s\S]*\]', result_text)
        if json_match:
            groups = json.loads(json_match.group())
            # Filter to only include valid groups (2+ items, valid indices)
            valid_groups = []
            for group in groups:
                if isinstance(group, list) and len(group) >= 2:
                    # Validate all indices are within range
                    if all(isinstance(idx, int) and 0 <= idx < len(items) for idx in group):
                        valid_groups.append(group)

            return jsonify({
                'success': True,
                'groups': valid_groups
            })
        else:
            return jsonify({'success': True, 'groups': []})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    import os
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=debug, host='0.0.0.0', port=port)
