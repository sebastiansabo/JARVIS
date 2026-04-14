from ._shared import *


# ════════════════════════════════════════════════════════════════
# Import
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/import', methods=['POST'])
@login_required
@crm_required
def api_import():
    """Upload and import an Excel/CSV file.
    Form data: file (multipart), source_type (deals|clients|nw|gw|crm_clients)
    """
    source_type = request.form.get('source_type')
    if source_type not in IMPORT_HANDLERS:
        return jsonify({'success': False,
                        'error': f'Invalid source_type. Use: {", ".join(IMPORT_HANDLERS.keys())}'}), 400

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.xlsx', '.xls', '.csv'):
        return jsonify({'success': False, 'error': 'Only .xlsx, .xls, .csv files supported'}), 400

    # Save to temp file (cleaned up by background thread)
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        file.save(tmp)
        tmp_path = tmp.name

    original_filename = file.filename
    user_id = current_user.id

    def _run():
        try:
            IMPORT_HANDLERS[source_type](tmp_path, user_id, original_filename=original_filename)
        except Exception:
            logger.exception('Background CRM import failed')
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'success': True, 'message': 'Import started'})


@crm_bp.route('/api/crm/import/template', methods=['GET'])
@login_required
@crm_required
def api_import_template():
    """Download the Samsaru import template (.xlsx)."""
    template_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'docs', 'import-templates', 'Samsaru_Import_Template.xlsx')
    template_path = os.path.abspath(template_path)
    if not os.path.exists(template_path):
        return jsonify({'success': False, 'error': 'Template file not found'}), 404
    return send_file(template_path, as_attachment=True, download_name='Samsaru_Import_Template.xlsx')


@crm_bp.route('/api/crm/import/batches', methods=['GET'])
@login_required
@crm_required
def api_import_batches():
    source_type = request.args.get('source_type')
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    batches = _import_repo.list_batches(source_type, limit, offset)
    return jsonify({'batches': batches})
