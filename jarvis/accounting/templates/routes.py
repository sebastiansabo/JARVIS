"""Invoice templates API routes."""
from flask import jsonify, request, redirect
from flask_login import login_required

from . import templates_bp
from .repositories import TemplateRepository
from core.utils.api_helpers import safe_error_response

_template_repo = TemplateRepository()


@templates_bp.route('/templates')
@login_required
def templates_page():
    """Redirect to React accounting page."""
    return redirect('/app/accounting')


@templates_bp.route('/api/templates')
@login_required
def api_get_templates():
    """Get all invoice templates."""
    return jsonify(_template_repo.get_all())


@templates_bp.route('/api/templates/<int:template_id>')
@login_required
def api_get_template(template_id):
    """Get a specific invoice template."""
    template = _template_repo.get(template_id)
    if template:
        return jsonify(template)
    return jsonify({'error': 'Template not found'}), 404


@templates_bp.route('/api/templates', methods=['POST'])
@login_required
def api_create_template():
    """Create a new invoice template."""
    data = request.get_json()

    try:
        template_id = _template_repo.save(
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
        return safe_error_response(e)


@templates_bp.route('/api/templates/<int:template_id>', methods=['PUT'])
@login_required
def api_update_template(template_id):
    """Update an invoice template."""
    data = request.get_json()

    try:
        updated = _template_repo.update(
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
        return safe_error_response(e)


@templates_bp.route('/api/templates/<int:template_id>', methods=['DELETE'])
@login_required
def api_delete_template(template_id):
    """Delete an invoice template."""
    if _template_repo.delete(template_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Template not found'}), 404


@templates_bp.route('/api/templates/generate', methods=['POST'])
@login_required
def api_generate_template():
    """Generate a template from a sample invoice using AI."""
    from accounting.bugetare.invoice_parser import generate_template_from_invoice

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    try:
        file_bytes = file.read()
        result = generate_template_from_invoice(file_bytes, file.filename)

        extracted_text = result.pop('_extracted_text', None)
        result.pop('_ai_generated', None)
        error = result.pop('_error', None)
        result.pop('_raw_response', None)

        response_data = {
            'success': True,
            'template': result,
            'extracted_text': extracted_text[:1000] if extracted_text else None
        }

        if error:
            response_data['warning'] = f'Partial result due to parsing error: {error}'

        return jsonify(response_data)

    except Exception as e:
        return safe_error_response(e)
