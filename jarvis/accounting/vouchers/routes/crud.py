"""CRUD routes for vouchers."""
from ._shared import *  # noqa: F401, F403
from pydantic import ValidationError
import io
from accounting.vouchers.form_seed import VOUCHER_FORM_SLUG


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
