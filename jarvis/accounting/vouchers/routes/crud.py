"""CRUD routes for vouchers."""
from ._shared import *  # noqa: F401, F403
from pydantic import ValidationError
import io
from accounting.vouchers.form_seed import VOUCHER_FORM_SLUG
from core.base_repository import BaseRepository

_base = BaseRepository()


@vouchers_bp.route('/api/vouchers/signature-status', methods=['GET'])
@login_required
@handle_api_errors
def get_signature_status():
    """Check if current user has a saved signature."""
    from core.base_repository import BaseRepository
    row = BaseRepository().query_one(
        'SELECT signature FROM users WHERE id = %s', (current_user.id,)
    )
    has_sig = bool(row and row.get('signature'))
    return jsonify({'has_signature': has_sig})


@vouchers_bp.route('/api/vouchers/form-id', methods=['GET'])
@login_required
@handle_api_errors
def get_voucher_form_id():
    """Return the ID of the Voucher Issuance form."""
    from core.base_repository import BaseRepository
    row = BaseRepository().query_one(
        "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL",
        (VOUCHER_FORM_SLUG,)
    )
    if not row:
        return error_response('Voucher form not configured', 404)
    return jsonify({'form_id': row['id']})


@vouchers_bp.route('/api/vouchers', methods=['POST'])
@login_required
@handle_api_errors
def create_voucher():
    """Create a new voucher and submit for approval."""
    data = request.get_json(silent=True) or {}

    try:
        validated = VoucherCreate(**data)
    except ValidationError as e:
        return jsonify({'success': False, 'errors': e.errors()}), 400

    try:
        voucher = _service.create_voucher(
            data=validated.model_dump(),
            user_id=current_user.id,
            company_id=current_user.company_id,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({
        'success': True,
        'voucher': {
            'id': voucher['id'],
            'voucher_code': voucher['voucher_code'],
            'status': voucher['status'],
            'approver_name': voucher.get('approver_name', ''),
        },
    }), 201


@vouchers_bp.route('/api/vouchers', methods=['GET'])
@login_required
@handle_api_errors
def list_vouchers():
    """List vouchers (company-scoped)."""
    status = request.args.get('status')
    voucher_type = request.args.get('voucher_type')
    expiring_soon = request.args.get('expiring_soon', '').lower() == 'true'
    limit = int(request.args.get('limit', 200))
    offset = int(request.args.get('offset', 0))

    status_list = status.split(',') if status else None

    rows = _repo.get_all(
        company_id=current_user.company_id,
        status=status_list,
        voucher_type=voucher_type,
        expiring_soon=expiring_soon,
        limit=limit,
        offset=offset,
    )
    return jsonify(rows)


@vouchers_bp.route('/api/vouchers/my', methods=['GET'])
@login_required
@handle_api_errors
def my_vouchers():
    """List current user's issued vouchers."""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    rows = _repo.get_by_user(current_user.id, limit=limit, offset=offset)
    return jsonify(rows)


@vouchers_bp.route('/api/vouchers/<int:voucher_id>', methods=['GET'])
@login_required
@handle_api_errors
def get_voucher(voucher_id):
    """Get a single voucher by ID."""
    voucher = _repo.get_by_id(voucher_id)
    if not voucher:
        return error_response('Voucher not found', 404)
    return jsonify(voucher)


@vouchers_bp.route('/api/vouchers/<int:voucher_id>/pdf', methods=['GET'])
@login_required
@handle_api_errors
def voucher_pdf(voucher_id):
    """Generate and return a printable voucher PDF."""
    voucher = _repo.get_by_id(voucher_id)
    if not voucher:
        return error_response('Voucher not found', 404)

    from accounting.vouchers.pdf_generator import generate_voucher_pdf
    pdf_bytes = generate_voucher_pdf(voucher)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"voucher-{voucher['voucher_code']}.pdf",
    )


@vouchers_bp.route('/api/vouchers/<int:voucher_id>/send', methods=['POST'])
@login_required
@handle_api_errors
def send_voucher_to_client(voucher_id):
    """Send voucher PDF to client via email."""
    voucher = _repo.get_by_id(voucher_id)
    if not voucher:
        return error_response('Voucher not found', 404)

    data = request.get_json(silent=True) or {}
    to_email = (data.get('email') or '').strip()
    if not to_email or '@' not in to_email:
        return jsonify({'success': False, 'error': 'Valid email address is required'}), 400

    from accounting.vouchers.pdf_generator import generate_voucher_pdf
    from core.services.notification_service import send_email

    pdf_bytes = generate_voucher_pdf(voucher)

    success, err = send_email(
        to_email=to_email,
        subject=f"Your Voucher {voucher['voucher_code']} — AUTOWORLD",
        html_body=f"""
        <p>Dear {voucher.get('client_name', 'Client')},</p>
        <p>Please find attached your voucher <strong>{voucher['voucher_code']}</strong>.</p>
        <ul>
            <li><strong>Type:</strong> {voucher.get('voucher_type', '').replace('_', ' ').title()}</li>
            <li><strong>Validity:</strong> {voucher.get('validity_months', '')} months</li>
            <li><strong>Expires:</strong> {voucher.get('expires_at', 'N/A')}</li>
        </ul>
        <p>Please present this voucher (printed or on screen) at your next visit.</p>
        <p>Best regards,<br>AUTOWORLD Group</p>
        """,
        attachments=[(f"voucher-{voucher['voucher_code']}.pdf", pdf_bytes)],
        from_name='AUTOWORLD Vouchers',
    )

    if not success:
        return jsonify({'success': False, 'error': f'Email failed: {err}'}), 500

    return jsonify({'success': True, 'message': f'Voucher sent to {to_email}'})


# ── Service Catalog CRUD ──────────────────────────────

@vouchers_bp.route('/api/vouchers/service-catalog', methods=['GET'])
@login_required
@handle_api_errors
def list_service_catalog():
    """List active service catalog items for the current user's company."""
    rows = _base.query_all(
        '''SELECT id, service_code, name, price, currency, category, is_active
           FROM voucher_service_catalog
           WHERE company_id = %s AND is_active = TRUE
           ORDER BY sort_order, name''',
        (current_user.company_id,)
    )
    return jsonify(rows)


@vouchers_bp.route('/api/vouchers/service-catalog', methods=['POST'])
@login_required
@handle_api_errors
def create_service_catalog_item():
    """Add a new service catalog item (accounting role required)."""
    if not _check_accounting_role():
        return error_response('Forbidden', 403)

    data = request.get_json(silent=True) or {}
    service_code = (data.get('service_code') or '').strip() or None
    name = (data.get('name') or '').strip()
    price = data.get('price')
    currency = (data.get('currency') or 'LEI').strip().upper()
    category = (data.get('category') or '').strip() or None
    sort_order = int(data.get('sort_order', 0))

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    if price is None or float(price) < 0:
        return jsonify({'success': False, 'error': 'Valid price is required'}), 400

    row = _base.execute(
        '''INSERT INTO voucher_service_catalog
               (company_id, service_code, name, price, currency, category, sort_order)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id, service_code, name, price, currency, category, is_active''',
        (current_user.company_id, service_code, name, float(price), currency, category, sort_order),
        returning=True,
    )
    return jsonify({'success': True, 'item': row}), 201


@vouchers_bp.route('/api/vouchers/service-catalog/<int:item_id>', methods=['PUT'])
@login_required
@handle_api_errors
def update_service_catalog_item(item_id):
    """Update a service catalog item (accounting role required)."""
    if not _check_accounting_role():
        return error_response('Forbidden', 403)

    existing = _base.query_one(
        'SELECT id FROM voucher_service_catalog WHERE id = %s AND company_id = %s',
        (item_id, current_user.company_id),
    )
    if not existing:
        return error_response('Service not found', 404)

    data = request.get_json(silent=True) or {}
    sets, params = [], []
    if 'service_code' in data:
        sets.append('service_code = %s')
        params.append((data['service_code'] or '').strip() or None)
    if 'name' in data:
        sets.append('name = %s')
        params.append(data['name'].strip())
    if 'price' in data:
        sets.append('price = %s')
        params.append(float(data['price']))
    if 'currency' in data:
        sets.append('currency = %s')
        params.append(data['currency'].strip().upper())
    if 'category' in data:
        sets.append('category = %s')
        params.append(data['category'].strip() or None)
    if 'sort_order' in data:
        sets.append('sort_order = %s')
        params.append(int(data['sort_order']))

    if not sets:
        return jsonify({'success': False, 'error': 'No fields to update'}), 400

    sets.append('updated_at = CURRENT_TIMESTAMP')
    params.append(item_id)

    _base.execute(
        f"UPDATE voucher_service_catalog SET {', '.join(sets)} WHERE id = %s",
        tuple(params),
    )
    updated = _base.query_one(
        'SELECT id, name, price, currency, category, is_active FROM voucher_service_catalog WHERE id = %s',
        (item_id,),
    )
    return jsonify({'success': True, 'item': updated})


@vouchers_bp.route('/api/vouchers/service-catalog/<int:item_id>', methods=['DELETE'])
@login_required
@handle_api_errors
def delete_service_catalog_item(item_id):
    """Soft-delete a service catalog item (set is_active=false)."""
    if not _check_accounting_role():
        return error_response('Forbidden', 403)

    existing = _base.query_one(
        'SELECT id FROM voucher_service_catalog WHERE id = %s AND company_id = %s',
        (item_id, current_user.company_id),
    )
    if not existing:
        return error_response('Service not found', 404)

    _base.execute(
        'UPDATE voucher_service_catalog SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
        (item_id,),
    )
    return jsonify({'success': True})
