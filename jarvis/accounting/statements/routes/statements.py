"""Statement file routes (upload, list, detail, delete, filters)."""
from ._shared import *  # noqa: F401, F403


# ============== UPLOAD & PARSE ==============

@statements_bp.route('/api/upload', methods=['POST'])
@api_login_required
@statements_access_required
def upload_statements():
    """
    Upload and parse bank statement PDF(s).

    Accepts multipart/form-data with file(s) under 'files' key.
    """
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    # Validate file sizes using helper function
    is_valid, error_msg, _ = _validate_upload_files(files)
    if not is_valid:
        return jsonify({'success': False, 'error': error_msg}), 400

    results = []
    total_new = 0
    total_duplicates = 0
    user_id = current_user.id if current_user.is_authenticated else None

    for file in files:
        if not file.filename:
            continue

        if not file.filename.lower().endswith('.pdf'):
            logger.warning(f'Skipping non-PDF file: {file.filename}')
            continue

        try:
            pdf_bytes = file.read()

            # Process single statement using service
            result = statements_service.process_statement(pdf_bytes, file.filename, user_id)

            if result.success:
                data = result.data
                # Track totals (skipped files don't have these keys)
                if not data.get('skipped'):
                    total_new += data.get('new_transactions', 0)
                    total_duplicates += data.get('duplicate_transactions', 0)
                results.append(data)
            else:
                results.append({
                    'filename': file.filename,
                    'error': result.error
                })

        except Exception as e:
            logger.exception(f'Error parsing {file.filename}')
            results.append({
                'filename': file.filename,
                'error': str(e)
            })

    return jsonify({
        'success': True,
        'statements': results,
        'total_new': total_new,
        'total_duplicates': total_duplicates
    })


# ============== STATEMENT MANAGEMENT ==============

@statements_bp.route('/api/statements', methods=['GET'])
@api_login_required
@statements_access_required
def list_statements():
    """List all uploaded statements with pagination."""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    data = statements_service.get_all_statements(limit=limit, offset=offset)

    return jsonify({
        'success': True,
        **data
    })


@statements_bp.route('/api/statements/<int:statement_id>', methods=['GET'])
@api_login_required
@statements_access_required
def get_statement_detail(statement_id):
    """Get details for a single statement."""
    stmt = statements_service.get_statement(statement_id)
    if not stmt:
        return jsonify({'success': False, 'error': 'Statement not found'}), 404

    return jsonify({'success': True, 'statement': stmt})


@statements_bp.route('/api/statements/<int:statement_id>', methods=['DELETE'])
@api_login_required
@statements_access_required
def delete_statement_route(statement_id):
    """Delete a statement and all its transactions."""
    result = statements_service.delete_statement(statement_id)

    if result.success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': result.error}), 404 if result.error == 'Statement not found' else 500


# ============== FILTER OPTIONS ==============

@statements_bp.route('/api/filters', methods=['GET'])
@api_login_required
@statements_access_required
def get_filter_options():
    """Get available filter options for dropdowns."""
    options = statements_service.get_filter_options()

    return jsonify({
        'success': True,
        **options
    })
