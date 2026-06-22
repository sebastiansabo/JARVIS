"""Accounting-specific voucher routes: tracking, redeem, export."""
import csv
import io
from ._shared import *  # noqa: F401, F403
from flask import Response
from pydantic import ValidationError


@vouchers_bp.route('/api/vouchers/accounting', methods=['GET'])
@login_required
@handle_api_errors
def accounting_list():
    """Full voucher list for accounting team with filters and summary."""
    if not _check_accounting_role():
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    status = request.args.get('status')
    voucher_type = request.args.get('voucher_type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    expiring_within = request.args.get('expiring_within_days', type=int)
    limit = int(request.args.get('limit', 200))
    offset = int(request.args.get('offset', 0))

    status_list = status.split(',') if status else None
    type_list = voucher_type.split(',') if voucher_type else None

    rows = _repo.get_all(
        company_id=current_user.company_id,
        status=status_list,
        voucher_type=type_list,
        date_from=date_from,
        date_to=date_to,
        expiring_within_days=expiring_within,
        limit=limit,
        offset=offset,
    )

    summary = _repo.get_summary_counts(current_user.company_id)

    return jsonify({
        'vouchers': rows,
        'summary': summary,
    })


@vouchers_bp.route('/api/vouchers/<int:voucher_id>/redeem', methods=['PATCH'])
@login_required
@handle_api_errors
def redeem_voucher(voucher_id):
    """Mark a voucher as redeemed (accounting/admin only)."""
    if not _check_accounting_role():
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}

    try:
        validated = VoucherRedeem(**data)
    except ValidationError as e:
        return jsonify({'success': False, 'errors': e.errors()}), 400

    try:
        result = _service.redeem_voucher(
            voucher_id=voucher_id,
            redeemed_by_user_id=current_user.id,
            notes=validated.redemption_notes,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result:
        return error_response('Voucher not found or cannot be redeemed', 404)

    return jsonify({'success': True, 'voucher': result})


@vouchers_bp.route('/api/vouchers/lookup/<code>', methods=['GET'])
@login_required
@handle_api_errors
def lookup_voucher_by_code(code):
    """Look up a voucher by its code (for scan/redeem flow)."""
    voucher = _repo.query_one('''
        SELECT v.*,
               u_issued.name AS issued_by_name,
               u_redeemed.name AS redeemed_by_name,
               CASE WHEN v.expires_at IS NOT NULL AND v.status = 'active'
                    THEN (v.expires_at - CURRENT_DATE) ELSE NULL END AS days_remaining
        FROM vouchers v
        LEFT JOIN users u_issued ON u_issued.id = v.issued_by_user_id
        LEFT JOIN users u_redeemed ON u_redeemed.id = v.redeemed_by_user_id
        WHERE v.voucher_code = %s
    ''', (code.upper(),))
    if not voucher:
        return error_response('Voucher not found', 404)
    return jsonify(voucher)


@vouchers_bp.route('/api/vouchers/redeem-by-code', methods=['POST'])
@login_required
@handle_api_errors
def redeem_by_code():
    """Redeem a voucher by its code (from QR scan)."""
    if not _check_accounting_role():
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}
    code = (data.get('voucher_code') or '').strip().upper()
    notes = data.get('redemption_notes', '')

    if not code:
        return jsonify({'success': False, 'error': 'voucher_code is required'}), 400

    voucher = _repo.query_one(
        'SELECT id, status FROM vouchers WHERE voucher_code = %s', (code,)
    )
    if not voucher:
        return jsonify({'success': False, 'error': f'Voucher {code} not found'}), 404

    try:
        result = _service.redeem_voucher(
            voucher_id=voucher['id'],
            redeemed_by_user_id=current_user.id,
            notes=notes,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result:
        return error_response('Voucher cannot be redeemed', 400)

    return jsonify({'success': True, 'voucher': result})


@vouchers_bp.route('/api/public/vouchers/lookup/<code>', methods=['GET'])
@handle_api_errors
def public_lookup_voucher(code):
    """Public: look up a voucher by code (no auth). Returns limited info."""
    voucher = _repo.query_one('''
        SELECT v.voucher_code, v.client_name, v.contract_number, v.car_vin,
               v.voucher_type, v.value_lei, v.discount_code, v.discount_percentage,
               v.service_items, v.validity_months, v.status,
               v.issued_at, v.expires_at,
               c.company AS company_name, c.vat AS company_vat,
               CASE WHEN v.expires_at IS NOT NULL AND v.status = 'active'
                    THEN (v.expires_at - CURRENT_DATE) ELSE NULL END AS days_remaining
        FROM vouchers v
        LEFT JOIN companies c ON c.id = v.company_id
        WHERE v.voucher_code = %s
    ''', (code.strip().upper(),))
    if not voucher:
        return error_response('Voucher not found', 404)
    return jsonify(voucher)


@vouchers_bp.route('/api/public/vouchers/redeem', methods=['POST'])
@handle_api_errors
def public_redeem_voucher():
    """Public: redeem a voucher by code (no auth). QR code acts as proof."""
    data = request.get_json(silent=True) or {}
    code = (data.get('voucher_code') or '').strip().upper()
    redeemer_name = (data.get('redeemer_name') or '').strip()

    if not code:
        return jsonify({'success': False, 'error': 'voucher_code is required'}), 400
    if not redeemer_name:
        return jsonify({'success': False, 'error': 'redeemer_name is required'}), 400

    voucher = _repo.query_one(
        'SELECT id, status, expires_at FROM vouchers WHERE voucher_code = %s', (code,)
    )
    if not voucher:
        return jsonify({'success': False, 'error': f'Voucher {code} not found'}), 404
    if voucher['status'] != 'active':
        return jsonify({'success': False, 'error': f"Voucher status is '{voucher['status']}', cannot redeem"}), 400

    from datetime import date
    expires = voucher.get('expires_at')
    if expires:
        if isinstance(expires, str):
            expires = date.fromisoformat(expires)
        if expires < date.today():
            return jsonify({'success': False, 'error': 'Voucher has expired'}), 400

    _repo.execute('''
        UPDATE vouchers
        SET status = 'redeemed', redeemed_at = CURRENT_TIMESTAMP,
            redemption_notes = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND status = 'active'
    ''', (f'Redeemed by: {redeemer_name}', voucher['id']))

    # Notify issuer
    try:
        updated = _repo.get_by_id(voucher['id'])
        if updated:
            _service._notify_issuer_redeemed(updated, updated.get('issued_by_user_id', 0))
    except Exception:
        pass

    return jsonify({'success': True, 'message': f'Voucher {code} redeemed successfully'})


@vouchers_bp.route('/api/vouchers/export', methods=['GET'])
@login_required
@handle_api_errors
def export_vouchers():
    """CSV export of vouchers for accounting."""
    if not _check_accounting_role():
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    status = request.args.get('status')
    voucher_type = request.args.get('voucher_type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    status_list = status.split(',') if status else None
    type_list = voucher_type.split(',') if voucher_type else None

    rows = _repo.get_all(
        company_id=current_user.company_id,
        status=status_list,
        voucher_type=type_list,
        date_from=date_from,
        date_to=date_to,
        limit=10000,
        offset=0,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Voucher Code', 'Client', 'Contract', 'VIN', 'Type',
        'Benefit', 'Issued', 'Expires', 'Status', 'Issued By',
    ])
    for r in rows:
        writer.writerow([
            r.get('voucher_code', ''),
            r.get('client_name', ''),
            r.get('contract_number', ''),
            r.get('car_vin', ''),
            r.get('voucher_type', ''),
            r.get('benefit_display', ''),
            r.get('issued_at', ''),
            r.get('expires_at', ''),
            r.get('status', ''),
            r.get('issued_by_name', ''),
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=vouchers.csv'},
    )
