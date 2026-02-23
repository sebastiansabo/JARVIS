"""Bilant API routes — ~25 endpoints for templates, generations, metrics."""

import os
import logging
from flask import jsonify, request, send_file
from flask_login import login_required, current_user

from . import bilant_bp
from .repositories import BilantTemplateRepository, BilantGenerationRepository, ChartOfAccountsRepository
from .services.bilant_service import BilantService

logger = logging.getLogger('jarvis.bilant.routes')

_template_repo = BilantTemplateRepository()
_generation_repo = BilantGenerationRepository()
_coa_repo = ChartOfAccountsRepository()
_service = BilantService()


# ════════════════════════════════════════════════════════════════
# Templates
# ════════════════════════════════════════════════════════════════

@bilant_bp.route('/api/templates', methods=['GET'])
@login_required
def api_list_templates():
    company_id = request.args.get('company_id', type=int)
    templates = _template_repo.list_templates(company_id=company_id)
    return jsonify({'templates': templates})


@bilant_bp.route('/api/templates', methods=['POST'])
@login_required
def api_create_template():
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    template_id = _template_repo.create(
        name=name,
        created_by=current_user.id,
        company_id=data.get('company_id'),
        description=data.get('description'),
    )
    return jsonify({'success': True, 'id': template_id})


@bilant_bp.route('/api/templates/<int:template_id>', methods=['GET'])
@login_required
def api_get_template(template_id):
    template = _template_repo.get_by_id(template_id)
    if not template:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    rows = _template_repo.get_rows(template_id)
    metrics = _template_repo.get_metric_configs(template_id)
    return jsonify({'template': template, 'rows': rows, 'metrics': metrics})


@bilant_bp.route('/api/templates/<int:template_id>', methods=['PUT'])
@login_required
def api_update_template(template_id):
    data = request.get_json(silent=True) or {}
    _template_repo.update(template_id, **{k: v for k, v in data.items()
                                          if k in ('name', 'description', 'company_id', 'is_default')})
    return jsonify({'success': True})


@bilant_bp.route('/api/templates/<int:template_id>', methods=['DELETE'])
@login_required
def api_delete_template(template_id):
    _template_repo.soft_delete(template_id)
    return jsonify({'success': True})


@bilant_bp.route('/api/templates/<int:template_id>/duplicate', methods=['POST'])
@login_required
def api_duplicate_template(template_id):
    data = request.get_json(silent=True) or {}
    name = data.get('name', 'Copy')
    new_id = _template_repo.duplicate(template_id, name, current_user.id)
    return jsonify({'success': True, 'id': new_id})


@bilant_bp.route('/api/templates/import', methods=['POST'])
@login_required
def api_import_template():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    file = request.files['file']
    name = request.form.get('name', 'Imported Template')
    company_id = request.form.get('company_id', type=int)
    result = _service.import_template_from_excel(
        file.read(), name, company_id, current_user.id
    )
    return jsonify({'success': result.success, **(result.data or {}),
                    'error': result.error}), result.status_code


@bilant_bp.route('/api/templates/import-anaf', methods=['POST'])
@login_required
def api_import_anaf_template():
    """Upload ANAF PDF → parse XFA → create template with rows + metric configs."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename.endswith('.pdf'):
        return jsonify({'success': False, 'error': 'Please upload a PDF file'}), 400
    name = request.form.get('name', 'ANAF Template')
    company_id = request.form.get('company_id', type=int)
    result = _service.import_from_anaf_pdf(
        file.read(), name, company_id, current_user.id
    )
    status = result.status_code if not result.success else 200
    return jsonify({'success': result.success, **(result.data or {}),
                    'error': result.error}), status


# ════════════════════════════════════════════════════════════════
# Template Rows
# ════════════════════════════════════════════════════════════════

@bilant_bp.route('/api/templates/<int:template_id>/rows', methods=['GET'])
@login_required
def api_get_rows(template_id):
    rows = _template_repo.get_rows(template_id)
    return jsonify({'rows': rows})


@bilant_bp.route('/api/templates/<int:template_id>/rows', methods=['POST'])
@login_required
def api_add_row(template_id):
    data = request.get_json(silent=True) or {}
    row_id = _template_repo.add_row(
        template_id=template_id,
        description=data.get('description', ''),
        nr_rd=data.get('nr_rd'),
        formula_ct=data.get('formula_ct'),
        formula_rd=data.get('formula_rd'),
        row_type=data.get('row_type', 'data'),
        is_bold=data.get('is_bold', False),
        indent_level=data.get('indent_level', 0),
        sort_order=data.get('sort_order', 0),
    )
    return jsonify({'success': True, 'id': row_id})


@bilant_bp.route('/api/templates/rows/<int:row_id>', methods=['PUT'])
@login_required
def api_update_row(row_id):
    data = request.get_json(silent=True) or {}
    _template_repo.update_row(row_id, **{k: v for k, v in data.items()
                                         if k in ('description', 'nr_rd', 'formula_ct', 'formula_rd',
                                                   'row_type', 'is_bold', 'indent_level', 'sort_order')})
    return jsonify({'success': True})


@bilant_bp.route('/api/templates/rows/<int:row_id>', methods=['DELETE'])
@login_required
def api_delete_row(row_id):
    _template_repo.delete_row(row_id)
    return jsonify({'success': True})


@bilant_bp.route('/api/templates/<int:template_id>/rows/reorder', methods=['PUT'])
@login_required
def api_reorder_rows(template_id):
    data = request.get_json(silent=True) or {}
    row_ids = data.get('row_ids', [])
    if not row_ids:
        return jsonify({'success': False, 'error': 'row_ids required'}), 400
    _template_repo.reorder_rows(template_id, row_ids)
    return jsonify({'success': True})


# ════════════════════════════════════════════════════════════════
# Metric Configs
# ════════════════════════════════════════════════════════════════

@bilant_bp.route('/api/templates/<int:template_id>/metrics', methods=['GET'])
@login_required
def api_get_metric_configs(template_id):
    metrics = _template_repo.get_metric_configs(template_id)
    return jsonify({'metrics': metrics})


@bilant_bp.route('/api/templates/<int:template_id>/metrics', methods=['POST'])
@login_required
def api_set_metric_config(template_id):
    data = request.get_json(silent=True) or {}
    metric_key = data.get('metric_key')
    if not metric_key:
        return jsonify({'success': False, 'error': 'metric_key required'}), 400
    group = data.get('metric_group', 'summary')
    # Validate: ratios/derived need formula_expr, structure needs structure_side
    if group in ('ratio', 'derived') and not data.get('formula_expr'):
        return jsonify({'success': False, 'error': f'{group} metrics require formula_expr'}), 400
    if group == 'structure' and not data.get('structure_side'):
        return jsonify({'success': False, 'error': 'structure metrics require structure_side'}), 400
    config_id = _template_repo.set_metric_config(
        template_id=template_id,
        metric_key=metric_key,
        metric_label=data.get('metric_label', metric_key),
        nr_rd=data.get('nr_rd'),
        metric_group=group,
        sort_order=data.get('sort_order', 0),
        formula_expr=data.get('formula_expr'),
        display_format=data.get('display_format', 'currency'),
        interpretation=data.get('interpretation'),
        threshold_good=data.get('threshold_good'),
        threshold_warning=data.get('threshold_warning'),
        structure_side=data.get('structure_side'),
    )
    return jsonify({'success': True, 'id': config_id})


@bilant_bp.route('/api/templates/metrics/<int:config_id>', methods=['DELETE'])
@login_required
def api_delete_metric_config(config_id):
    _template_repo.delete_metric_config(config_id)
    return jsonify({'success': True})


# ════════════════════════════════════════════════════════════════
# Generations
# ════════════════════════════════════════════════════════════════

@bilant_bp.route('/api/generations', methods=['GET'])
@login_required
def api_list_generations():
    company_id = request.args.get('company_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    rows, total = _generation_repo.list_generations(company_id=company_id, limit=limit, offset=offset)
    return jsonify({'generations': rows, 'total': total})


@bilant_bp.route('/api/generations', methods=['POST'])
@login_required
def api_create_generation():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Invalid file type. Upload .xlsx'}), 400

    template_id = request.form.get('template_id', type=int)
    company_id = request.form.get('company_id', type=int)
    if not template_id or not company_id:
        return jsonify({'success': False, 'error': 'template_id and company_id required'}), 400

    result = _service.process_upload(
        file_bytes=file.read(),
        filename=file.filename,
        template_id=template_id,
        company_id=company_id,
        period_label=request.form.get('period_label'),
        period_date=request.form.get('period_date') or None,
        user_id=current_user.id,
    )
    status = result.status_code if not result.success else 200
    return jsonify({'success': result.success, **(result.data or {}),
                    'error': result.error}), status


@bilant_bp.route('/api/generations/<int:generation_id>', methods=['GET'])
@login_required
def api_get_generation(generation_id):
    result = _service.get_generation_detail(generation_id)
    if not result.success:
        return jsonify({'success': False, 'error': result.error}), result.status_code
    return jsonify(result.data)


@bilant_bp.route('/api/generations/<int:generation_id>', methods=['DELETE'])
@login_required
def api_delete_generation(generation_id):
    _generation_repo.delete_generation(generation_id)
    return jsonify({'success': True})


@bilant_bp.route('/api/generations/<int:generation_id>/notes', methods=['PUT'])
@login_required
def api_update_notes(generation_id):
    data = request.get_json(silent=True) or {}
    _generation_repo.update_notes(generation_id, data.get('notes', ''))
    return jsonify({'success': True})


@bilant_bp.route('/api/generations/<int:generation_id>/download', methods=['GET'])
@login_required
def api_download_generation(generation_id):
    result = _service.generate_excel(generation_id)
    if not result.success:
        return jsonify({'success': False, 'error': result.error}), result.status_code
    gen = _generation_repo.get_by_id(generation_id)
    name = f"Bilant_{gen['company_name']}_{gen.get('period_label', generation_id)}.xlsx" if gen else f"Bilant_{generation_id}.xlsx"
    name = name.replace(' ', '_')
    return send_file(
        result.data,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=name,
    )


@bilant_bp.route('/api/generations/<int:generation_id>/download-pdf', methods=['GET'])
@login_required
def api_download_generation_pdf(generation_id):
    """Download bilant as ANAF-styled PDF."""
    result = _service.generate_pdf(generation_id)
    if not result.success:
        return jsonify({'success': False, 'error': result.error}), result.status_code
    gen = _generation_repo.get_by_id(generation_id)
    name = f"Bilant_{gen['company_name']}_{gen.get('period_label', generation_id)}.pdf" if gen else f"Bilant_{generation_id}.pdf"
    name = name.replace(' ', '_')
    return send_file(
        result.data,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=name,
    )


@bilant_bp.route('/api/generations/<int:generation_id>/download-filled-pdf', methods=['GET'])
@login_required
def api_download_generation_filled_pdf(generation_id):
    """Download bilant as filled ANAF XFA PDF (original template with values)."""
    result = _service.generate_filled_pdf(generation_id)
    if not result.success:
        return jsonify({'success': False, 'error': result.error}), result.status_code
    gen = _generation_repo.get_by_id(generation_id)
    name = f"Bilant_ANAF_{gen['company_name']}_{gen.get('period_label', generation_id)}.pdf" if gen else f"Bilant_ANAF_{generation_id}.pdf"
    name = name.replace(' ', '_')
    return send_file(
        result.data,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=name,
    )


@bilant_bp.route('/api/generations/<int:generation_id>/download-anaf', methods=['GET'])
@login_required
def api_download_generation_anaf(generation_id):
    """Download bilant as ANAF-format Excel with F10 field codes."""
    result = _service.generate_anaf_excel(generation_id)
    if not result.success:
        return jsonify({'success': False, 'error': result.error}), result.status_code
    gen = _generation_repo.get_by_id(generation_id)
    name = f"Bilant_ANAF_{gen['company_name']}_{gen.get('period_label', generation_id)}.xlsx" if gen else f"Bilant_ANAF_{generation_id}.xlsx"
    name = name.replace(' ', '_')
    return send_file(
        result.data,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=name,
    )


# ════════════════════════════════════════════════════════════════
# Comparison
# ════════════════════════════════════════════════════════════════

@bilant_bp.route('/api/compare', methods=['POST'])
@login_required
def api_compare_generations():
    data = request.get_json(silent=True) or {}
    ids = data.get('generation_ids', [])
    result = _service.compare_generations(ids)
    if not result.success:
        return jsonify({'success': False, 'error': result.error}), result.status_code
    return jsonify(result.data)


# ════════════════════════════════════════════════════════════════
# Chart of Accounts (Plan de Conturi)
# ════════════════════════════════════════════════════════════════

@bilant_bp.route('/api/chart-of-accounts', methods=['GET'])
@login_required
def api_list_accounts():
    company_id = request.args.get('company_id', type=int)
    account_class = request.args.get('account_class', type=int)
    account_type = request.args.get('account_type')
    search = request.args.get('search')
    accounts = _coa_repo.list_all(
        company_id=company_id, account_class=account_class,
        account_type=account_type, search=search)
    return jsonify({'accounts': accounts})


@bilant_bp.route('/api/chart-of-accounts', methods=['POST'])
@login_required
def api_create_account():
    data = request.get_json(silent=True) or {}
    code = data.get('code', '').strip()
    name = data.get('name', '').strip()
    account_class = data.get('account_class')
    if not code or not name or not account_class:
        return jsonify({'success': False, 'error': 'code, name, account_class required'}), 400
    account_id = _coa_repo.create(
        code=code, name=name, account_class=account_class,
        account_type=data.get('account_type', 'synthetic'),
        parent_code=data.get('parent_code'),
        company_id=data.get('company_id'))
    return jsonify({'success': True, 'id': account_id})


@bilant_bp.route('/api/chart-of-accounts/<int:account_id>', methods=['PUT'])
@login_required
def api_update_account(account_id):
    data = request.get_json(silent=True) or {}
    _coa_repo.update(account_id, **{k: v for k, v in data.items()
                     if k in ('code', 'name', 'account_class', 'account_type', 'parent_code', 'is_active')})
    return jsonify({'success': True})


@bilant_bp.route('/api/chart-of-accounts/<int:account_id>', methods=['DELETE'])
@login_required
def api_delete_account(account_id):
    _coa_repo.delete(account_id)
    return jsonify({'success': True})


@bilant_bp.route('/api/chart-of-accounts/autocomplete', methods=['GET'])
@login_required
def api_autocomplete_accounts():
    prefix = request.args.get('prefix', '')
    company_id = request.args.get('company_id', type=int)
    if len(prefix) < 1:
        return jsonify({'accounts': []})
    results = _coa_repo.search_for_autocomplete(prefix, company_id=company_id)
    return jsonify({'accounts': results})


# ════════════════════════════════════════════════════════════════
# Template Download
# ════════════════════════════════════════════════════════════════

@bilant_bp.route('/api/template-download', methods=['GET'])
@login_required
def api_download_template():
    """Download the Balanta/Bilant template Excel file."""
    template_path = os.path.join(os.path.dirname(__file__), 'static', 'template_balanta.xlsx')
    if not os.path.exists(template_path):
        return jsonify({'success': False, 'error': 'Template file not found'}), 404
    return send_file(
        template_path,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='Jarvis_Bilant_template.xlsx',
    )
