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
    get_summary_by_company, get_summary_by_department, delete_invoice, update_invoice,
    get_all_invoice_templates, get_invoice_template, save_invoice_template,
    update_invoice_template, delete_invoice_template
)

# Google Drive integration (optional)
try:
    from drive_service import upload_invoice_to_drive, check_drive_auth
    DRIVE_ENABLED = True
except ImportError:
    DRIVE_ENABLED = False

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
            distributions=data['distributions']
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


@app.route('/api/db/invoices')
def api_db_invoices():
    """Get all invoices from database with pagination."""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    invoices = get_all_invoices(limit=limit, offset=offset)
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
    """Delete an invoice."""
    if delete_invoice(invoice_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Invoice not found'}), 404


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
            invoice_value=float(data['invoice_value']) if data.get('invoice_value') is not None else None,
            currency=data.get('currency'),
            drive_link=data.get('drive_link'),
            comment=data.get('comment')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invoice not found'}), 404
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


@app.route('/api/db/summary/company')
def api_db_summary_company():
    """Get summary grouped by company."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    summary = get_summary_by_company(start_date, end_date)
    return jsonify(summary)


@app.route('/api/db/summary/department')
def api_db_summary_department():
    """Get summary grouped by department."""
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    summary = get_summary_by_department(company, start_date, end_date)
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
