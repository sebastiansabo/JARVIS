import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify
from models import load_structure, get_companies, get_brands_for_company, get_departments_for_company, get_subdepartments, get_manager
from services import (
    save_invoice_to_db,
    get_companies_with_vat, match_company_by_vat, add_company_with_vat, update_company_vat, delete_company
)
from invoice_parser import parse_invoice, parse_invoice_with_template_from_bytes, auto_detect_and_parse, generate_template_from_invoice
from database import (
    get_all_invoices, get_invoice_with_allocations, search_invoices,
    get_summary_by_company, get_summary_by_department, get_summary_by_brand, delete_invoice, update_invoice,
    update_invoice_allocations,
    get_all_invoice_templates, get_invoice_template, save_invoice_template,
    update_invoice_template, delete_invoice_template,
    check_invoice_number_exists,
    restore_invoice, bulk_soft_delete_invoices, bulk_restore_invoices,
    permanently_delete_invoice, bulk_permanently_delete_invoices,
    get_invoice_drive_link, get_invoice_drive_links
)

# Google Drive integration (optional)
try:
    from drive_service import upload_invoice_to_drive, check_drive_auth, delete_file_from_drive, delete_files_from_drive
    DRIVE_ENABLED = True
except ImportError:
    DRIVE_ENABLED = False
    delete_file_from_drive = None
    delete_files_from_drive = None

# Currency conversion (BNR rates)
try:
    from currency_converter import get_eur_ron_conversion
    CURRENCY_CONVERSION_ENABLED = True
except ImportError:
    CURRENCY_CONVERSION_ENABLED = False

app = Flask(__name__)


@app.route('/')
def index():
    """Main page with invoice distribution form."""
    return render_template('index.html')


@app.route('/api/structure')
def get_structure():
    """Get the full organizational structure."""
    units = load_structure()
    return jsonify([{
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
def api_companies():
    """Get list of companies."""
    return jsonify(get_companies())


@app.route('/api/brands/<company>')
def api_brands(company):
    """Get brands for a company."""
    return jsonify(get_brands_for_company(company))


@app.route('/api/departments/<company>')
def api_departments(company):
    """Get departments for a company."""
    return jsonify(get_departments_for_company(company))


@app.route('/api/subdepartments/<company>/<department>')
def api_subdepartments(company, department):
    """Get subdepartments for a company and department."""
    return jsonify(get_subdepartments(company, department))


@app.route('/api/manager')
def api_manager():
    """Get manager for a department."""
    company = request.args.get('company')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    return jsonify({'manager': get_manager(company, department, subdepartment)})


@app.route('/api/submit', methods=['POST'])
def submit_invoice():
    """Submit an invoice with its cost distribution."""
    data = request.json

    try:
        # Save to database
        invoice_id = save_invoice_to_db(
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
            exchange_rate=data.get('exchange_rate')
        )

        return jsonify({
            'success': True,
            'message': f'Successfully saved {len(data["distributions"])} allocation(s)',
            'allocations': len(data['distributions']),
            'invoice_id': invoice_id
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/data')
def get_data():
    """Get existing data (returns empty - legacy endpoint)."""
    return jsonify([])


@app.route('/api/parse-invoice', methods=['POST'])
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

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/parse-existing/<path:filepath>')
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
def api_drive_upload():
    """Upload invoice to Google Drive organized by Year/Supplier."""
    if not DRIVE_ENABLED:
        return jsonify({'success': False, 'error': 'Google Drive not configured'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    supplier = request.form.get('supplier', 'Unknown')
    invoice_date = request.form.get('invoice_date', '')

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
            supplier=supplier,
            invoice_date=invoice_date,
            mime_type=mime_type
        )

        return jsonify({'success': True, 'drive_link': drive_link})
    except FileNotFoundError as e:
        return jsonify({'success': False, 'error': str(e), 'need_auth': True}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== ACCOUNTING INTERFACE ENDPOINTS ==============

@app.route('/accounting')
def accounting():
    """Accounting dashboard for viewing all allocations."""
    return render_template('accounting.html')


# ============== CONNECTORS INTERFACE ENDPOINTS ==============

@app.route('/connectors')
def connectors():
    """Connectors page for managing external integrations."""
    from database import get_all_connectors, get_connector_by_type, get_connector_sync_logs

    all_connectors = get_all_connectors()

    # Add sync logs to each connector
    for connector in all_connectors:
        connector['sync_logs'] = get_connector_sync_logs(connector['id'], limit=10)

    # Get specific connectors for the template
    google_ads_connector = get_connector_by_type('google_ads')
    if google_ads_connector:
        google_ads_connector['sync_logs'] = get_connector_sync_logs(google_ads_connector['id'], limit=10)

    return render_template('connectors.html',
                           connectors=all_connectors,
                           google_ads_connector=google_ads_connector)


@app.route('/api/connectors', methods=['GET'])
def api_get_connectors():
    """Get all connectors."""
    from database import get_all_connectors
    return jsonify(get_all_connectors())


@app.route('/api/connectors/<int:connector_id>', methods=['GET'])
def api_get_connector(connector_id):
    """Get a specific connector."""
    from database import get_connector
    connector = get_connector(connector_id)
    if connector:
        return jsonify(connector)
    return jsonify({'error': 'Connector not found'}), 404


@app.route('/api/connectors', methods=['POST'])
def api_create_connector():
    """Create a new connector."""
    from database import save_connector, get_connector_by_type

    data = request.get_json()
    connector_type = data.get('connector_type')
    name = data.get('name')

    if not connector_type or not name:
        return jsonify({'error': 'connector_type and name are required'}), 400

    # Check if connector of this type already exists
    existing = get_connector_by_type(connector_type)
    if existing:
        return jsonify({'error': f'A {connector_type} connector already exists'}), 400

    # Build config and credentials based on connector type
    config = {}
    credentials = {}

    if connector_type == 'google_ads':
        config['customer_id'] = data.get('customer_id', '').replace('-', '')
        credentials['developer_token'] = data.get('developer_token', '')
        credentials['oauth_client_id'] = data.get('oauth_client_id', '')
        credentials['oauth_client_secret'] = data.get('oauth_client_secret', '')
        credentials['refresh_token'] = data.get('refresh_token', '')

    connector_id = save_connector(
        connector_type=connector_type,
        name=name,
        status='connected',
        config=config,
        credentials=credentials
    )

    return jsonify({'success': True, 'id': connector_id})


@app.route('/api/connectors/<int:connector_id>', methods=['PUT'])
def api_update_connector(connector_id):
    """Update a connector."""
    from database import update_connector, get_connector

    connector = get_connector(connector_id)
    if not connector:
        return jsonify({'error': 'Connector not found'}), 404

    data = request.get_json()

    # Update name if provided
    name = data.get('name')

    # Update config
    config = connector.get('config', {})
    if data.get('customer_id'):
        config['customer_id'] = data.get('customer_id', '').replace('-', '')

    # Update credentials only if new values provided
    credentials = connector.get('credentials', {})
    if data.get('developer_token'):
        credentials['developer_token'] = data['developer_token']
    if data.get('oauth_client_id'):
        credentials['oauth_client_id'] = data['oauth_client_id']
    if data.get('oauth_client_secret'):
        credentials['oauth_client_secret'] = data['oauth_client_secret']
    if data.get('refresh_token'):
        credentials['refresh_token'] = data['refresh_token']

    success = update_connector(
        connector_id,
        name=name,
        config=config,
        credentials=credentials
    )

    return jsonify({'success': success})


@app.route('/api/connectors/<int:connector_id>', methods=['DELETE'])
def api_delete_connector(connector_id):
    """Delete a connector."""
    from database import delete_connector

    success = delete_connector(connector_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Connector not found'}), 404


@app.route('/api/connectors/<int:connector_id>/sync', methods=['POST'])
def api_sync_connector(connector_id):
    """Trigger a sync for a connector."""
    from database import get_connector, update_connector, add_connector_sync_log
    from datetime import datetime

    connector = get_connector(connector_id)
    if not connector:
        return jsonify({'error': 'Connector not found'}), 404

    # For now, just log a placeholder sync
    # Real implementation would call the appropriate connector service
    try:
        if connector['connector_type'] == 'google_ads':
            # TODO: Implement actual Google Ads invoice sync
            # from google_ads_connector import sync_google_ads_invoices
            # result = sync_google_ads_invoices(connector)

            # Placeholder response
            log_id = add_connector_sync_log(
                connector_id=connector_id,
                sync_type='manual',
                status='success',
                invoices_found=0,
                invoices_imported=0,
                details={'message': 'Google Ads connector not yet implemented'}
            )

            update_connector(connector_id, last_sync=datetime.now(), status='connected')

            return jsonify({
                'success': True,
                'invoices_found': 0,
                'invoices_imported': 0,
                'message': 'Google Ads API integration not yet implemented'
            })
        else:
            return jsonify({'error': f'Unknown connector type: {connector["connector_type"]}'}), 400

    except Exception as e:
        add_connector_sync_log(
            connector_id=connector_id,
            sync_type='manual',
            status='error',
            error_message=str(e)
        )
        update_connector(connector_id, last_error=str(e), status='error')
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/invoices')
def api_db_invoices():
    """Get all invoices from database with pagination and optional filters."""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    company = request.args.get('company')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    invoices = get_all_invoices(
        limit=limit, offset=offset, company=company,
        start_date=start_date, end_date=end_date,
        department=department, subdepartment=subdepartment, brand=brand
    )
    return jsonify(invoices)


@app.route('/api/db/invoices/<int:invoice_id>')
def api_db_invoice_detail(invoice_id):
    """Get invoice with all allocations."""
    invoice = get_invoice_with_allocations(invoice_id)
    if invoice:
        return jsonify(invoice)
    return jsonify({'error': 'Invoice not found'}), 404


@app.route('/api/db/invoices/<int:invoice_id>', methods=['DELETE'])
def api_db_delete_invoice(invoice_id):
    """Soft delete an invoice (move to bin)."""
    if delete_invoice(invoice_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Invoice not found'}), 404


@app.route('/api/db/invoices/<int:invoice_id>/restore', methods=['POST'])
def api_db_restore_invoice(invoice_id):
    """Restore a soft-deleted invoice from the bin."""
    if restore_invoice(invoice_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Invoice not found in bin'}), 404


@app.route('/api/db/invoices/<int:invoice_id>/permanent', methods=['DELETE'])
def api_db_permanently_delete_invoice(invoice_id):
    """Permanently delete an invoice (cannot be restored). Also deletes from Google Drive."""
    # Get drive_link before deleting the invoice
    drive_link = get_invoice_drive_link(invoice_id)

    if permanently_delete_invoice(invoice_id):
        # Delete from Google Drive if link exists and Drive is enabled
        drive_deleted = False
        if drive_link and DRIVE_ENABLED and delete_file_from_drive:
            drive_deleted = delete_file_from_drive(drive_link)
        return jsonify({'success': True, 'drive_deleted': drive_deleted})
    return jsonify({'error': 'Invoice not found'}), 404


@app.route('/api/db/invoices/bulk-delete', methods=['POST'])
def api_db_bulk_delete_invoices():
    """Soft delete multiple invoices."""
    data = request.json
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'error': 'No invoice IDs provided'}), 400
    count = bulk_soft_delete_invoices(invoice_ids)
    return jsonify({'success': True, 'deleted_count': count})


@app.route('/api/db/invoices/bulk-restore', methods=['POST'])
def api_db_bulk_restore_invoices():
    """Restore multiple soft-deleted invoices."""
    data = request.json
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'error': 'No invoice IDs provided'}), 400
    count = bulk_restore_invoices(invoice_ids)
    return jsonify({'success': True, 'restored_count': count})


@app.route('/api/db/invoices/bulk-permanent-delete', methods=['POST'])
def api_db_bulk_permanently_delete_invoices():
    """Permanently delete multiple invoices (cannot be restored). Also deletes from Google Drive."""
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
def api_db_get_deleted_invoices():
    """Get all soft-deleted invoices (bin)."""
    invoices = get_all_invoices(include_deleted=True, limit=500)
    return jsonify(invoices)


@app.route('/api/db/invoices/<int:invoice_id>', methods=['PUT'])
def api_db_update_invoice(invoice_id):
    """Update an invoice."""
    data = request.json

    try:
        updated = update_invoice(
            invoice_id=invoice_id,
            supplier=data.get('supplier'),
            invoice_number=data.get('invoice_number'),
            invoice_date=data.get('invoice_date'),
            invoice_value=float(data['invoice_value']) if data.get('invoice_value') else None,
            currency=data.get('currency'),
            drive_link=data.get('drive_link'),
            comment=data.get('comment')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'error': 'Invoice not found or no changes made'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/db/invoices/<int:invoice_id>/allocations', methods=['PUT'])
def api_db_update_allocations(invoice_id):
    """Update all allocations for an invoice."""
    data = request.json
    allocations = data.get('allocations', [])

    if not allocations:
        return jsonify({'success': False, 'error': 'At least one allocation is required'}), 400

    # Validate allocations sum to 100%
    total_percent = sum(float(a.get('allocation_percent', 0)) for a in allocations)
    if abs(total_percent - 100) > 0.01:
        return jsonify({'success': False, 'error': f'Allocations must sum to 100%, got {total_percent}%'}), 400

    try:
        update_invoice_allocations(invoice_id, allocations)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/invoices/<int:invoice_id>/drive-link', methods=['PUT'])
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
def api_db_search():
    """Search invoices by supplier or invoice number."""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    results = search_invoices(query)
    return jsonify(results)


@app.route('/api/db/check-invoice-number')
def api_check_invoice_number():
    """Check if an invoice number already exists in the database."""
    invoice_number = request.args.get('invoice_number', '').strip()
    exclude_id = request.args.get('exclude_id', type=int)

    if not invoice_number:
        return jsonify({'exists': False, 'invoice': None})

    result = check_invoice_number_exists(invoice_number, exclude_id)
    return jsonify(result)


@app.route('/api/db/summary/company')
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


# ============== COMPANY VAT MANAGEMENT ENDPOINTS ==============

@app.route('/api/companies-vat')
def api_companies_vat():
    """Get all companies with their VAT numbers."""
    companies = get_companies_with_vat()
    return jsonify(companies)


@app.route('/api/companies-vat', methods=['POST'])
def api_add_company_vat():
    """Add a new company with VAT."""
    data = request.json
    company = data.get('company', '').strip()
    vat = data.get('vat', '').strip()
    brands = data.get('brands', '').strip()

    if not company or not vat:
        return jsonify({'success': False, 'error': 'Company and VAT are required'}), 400

    try:
        add_company_with_vat(company, vat, brands)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/companies-vat/<company>', methods=['PUT'])
def api_update_company_vat(company):
    """Update company VAT."""
    data = request.json
    vat = data.get('vat', '').strip()
    brands = data.get('brands')

    if not vat:
        return jsonify({'success': False, 'error': 'VAT is required'}), 400

    if update_company_vat(company, vat, brands):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Company not found'}), 404


@app.route('/api/companies-vat/<company>', methods=['DELETE'])
def api_delete_company_vat(company):
    """Delete a company."""
    if delete_company(company):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Company not found'}), 404


@app.route('/api/match-vat/<vat>')
def api_match_vat(vat):
    """Match a VAT number to a company."""
    company = match_company_by_vat(vat)
    if company:
        return jsonify({'success': True, 'company': company})
    return jsonify({'success': False, 'company': None})


# ============== INVOICE TEMPLATES ENDPOINTS ==============

@app.route('/templates')
def templates_page():
    """Invoice templates management page."""
    return render_template('templates.html')


@app.route('/api/templates')
def api_get_templates():
    """Get all invoice templates."""
    templates = get_all_invoice_templates()
    return jsonify(templates)


@app.route('/api/templates/<int:template_id>')
def api_get_template(template_id):
    """Get a specific invoice template."""
    template = get_invoice_template(template_id)
    if template:
        return jsonify(template)
    return jsonify({'error': 'Template not found'}), 404


@app.route('/api/templates', methods=['POST'])
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
def api_delete_template(template_id):
    """Delete an invoice template."""
    if delete_invoice_template(template_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Template not found'}), 404


@app.route('/api/templates/generate', methods=['POST'])
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


if __name__ == '__main__':
    import os
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=debug, host='0.0.0.0', port=port)
