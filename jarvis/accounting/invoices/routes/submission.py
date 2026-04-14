"""Parse and submit routes for invoices."""
from ._shared import *  # noqa: F401, F403


@invoices_bp.route('/api/submit', methods=['POST'])
@login_required
def submit_invoice():
    """Submit an invoice with its cost distribution."""
    if not _check_invoice_perm('add'):
        return jsonify({'success': False, 'error': 'You do not have permission to add invoices'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400

    result = _service.submit_invoice(data, _get_user_context())
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


@invoices_bp.route('/api/invoices/bulk-parse', methods=['POST'])
@login_required
def api_bulk_parse():
    """Parse multiple uploaded invoices using AI. Returns array of parse results."""
    if not _check_invoice_perm('add'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    files = request.files.getlist('files[]')
    if not files:
        return jsonify({'success': False, 'error': 'No files uploaded'}), 400
    if len(files) > 20:
        return jsonify({'success': False, 'error': 'Maximum 20 files per batch'}), 400

    allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif'}
    results = []
    for f in files:
        _, ext = os.path.splitext(f.filename.lower())
        if ext not in allowed_extensions:
            results.append({'filename': f.filename, 'success': False, 'error': f'File type {ext} not allowed'})
            continue
        file_data = f.read()
        if len(file_data) > 50 * 1024 * 1024:
            results.append({'filename': f.filename, 'success': False, 'error': 'File too large (max 50MB)'})
            continue
        result = _service.parse_invoice(file_data, f.filename)
        if result.success:
            inv_num = result.data.get('invoice_number', '')
            dup = _invoice_repo.check_number_exists(inv_num) if inv_num else {'exists': False}
            results.append({
                'filename': f.filename,
                'success': True,
                'data': result.data,
                'duplicate': dup.get('exists', False),
            })
        else:
            results.append({'filename': f.filename, 'success': False, 'error': result.error})

    return jsonify({'success': True, 'results': results})


@invoices_bp.route('/api/invoices/bulk-submit', methods=['POST'])
@login_required
def api_bulk_submit():
    """Submit multiple parsed invoices at once."""
    if not _check_invoice_perm('add'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    invoices = data.get('invoices', [])
    if not invoices:
        return jsonify({'success': False, 'error': 'No invoices provided'}), 400

    user_ctx = _get_user_context()
    results = []
    for inv in invoices:
        try:
            result = _service.submit_invoice(inv, user_ctx)
            if result.success:
                results.append({
                    'invoice_number': inv.get('invoice_number', ''),
                    'success': True,
                    'invoice_id': result.data.get('invoice_id'),
                })
            else:
                results.append({
                    'invoice_number': inv.get('invoice_number', ''),
                    'success': False,
                    'error': result.error,
                })
        except Exception as e:
            results.append({
                'invoice_number': inv.get('invoice_number', ''),
                'success': False,
                'error': str(e),
            })

    saved = sum(1 for r in results if r['success'])
    return jsonify({
        'success': True,
        'results': results,
        'saved_count': saved,
        'total': len(invoices),
    })


@invoices_bp.route('/api/parse-invoice', methods=['POST'])
@login_required
def api_parse_invoice():
    """Parse an uploaded invoice using AI or template (with auto-detection)."""
    if not _check_invoice_perm('add'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Validate file type
    allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif'}
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f'File type {ext} not allowed'}), 400

    # Validate file size (50MB max)
    file_data = file.read()
    if len(file_data) > 50 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File too large (max 50MB)'}), 413

    template_id = request.form.get('template_id')
    result = _service.parse_invoice(
        file_data, file.filename,
        template_id=int(template_id) if template_id else None,
    )
    if result.success:
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'error': result.error}), result.status_code


@invoices_bp.route('/api/parse-existing/<path:filepath>')
@login_required
@handle_api_errors
def api_parse_existing(filepath):
    """Parse an existing invoice from the Invoices folder."""
    from core.config import INVOICES_DIR
    from accounting.bugetare.invoice_parser import parse_invoice
    file_path = os.path.realpath(os.path.join(INVOICES_DIR, filepath))

    # Prevent path traversal — resolved path must stay within INVOICES_DIR
    if not file_path.startswith(os.path.realpath(INVOICES_DIR) + os.sep):
        return jsonify({'success': False, 'error': 'Invalid file path'}), 400

    if not os.path.exists(file_path):
        return jsonify({'success': False, 'error': 'File not found'}), 404

    result = parse_invoice(file_path)
    return jsonify({'success': True, 'data': result})


@invoices_bp.route('/api/suggest-department')
@login_required
@handle_api_errors
def api_suggest_department():
    """Suggest department based on historical allocations for the same supplier."""
    supplier = request.args.get('supplier', '').strip()
    if not supplier:
        return jsonify({'suggestions': []})

    rows = _invoice_repo.get_department_suggestions(supplier)
    suggestions = [
        {
            'company': r['company'],
            'brand': r['brand'],
            'department': r['department'],
            'subdepartment': r['subdepartment'],
            'frequency': r['frequency'],
        }
        for r in rows
    ]
    return jsonify({'suggestions': suggestions})


@invoices_bp.route('/api/invoices')
@login_required
def api_list_invoices():
    """List available invoices in the Invoices folder (including subfolders)."""
    from core.config import INVOICES_DIR
    if not os.path.exists(INVOICES_DIR):
        return jsonify([])

    files = []
    for root, dirs, filenames in os.walk(INVOICES_DIR):
        for f in filenames:
            if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                rel_path = os.path.relpath(os.path.join(root, f), INVOICES_DIR)
                files.append(rel_path)
    return jsonify(sorted(files))
