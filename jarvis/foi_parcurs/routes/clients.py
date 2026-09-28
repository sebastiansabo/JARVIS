"""Routes for CRM client management (search, create for foi de parcurs dropdown)."""

import re
from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required, current_user,
    logger, _client_repo, _fp_repo,
)


# ════════════════════════════════════════════════════════════════
# Search clients
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/clients/search', methods=['GET'])
@login_required
def api_search_clients():
    """Search clients by name, phone, or ID document number."""
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'success': False, 'error': 'Search query (q) is required'}), 400

    limit = request.args.get('limit', 20, type=int)
    limit = min(limit, 50)  # cap

    clients = _client_repo.search_clients(q, limit=limit)
    return jsonify({'success': True, 'clients': clients})


# ════════════════════════════════════════════════════════════════
# Client's last captured driving licence (activate-form prefill)
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/clients/<int:client_id>/last-license', methods=['GET'])
@login_required
def api_client_last_license(client_id):
    """Whether this client already has a driving licence on file (from a prior
    session), plus its serie/number/expiry — so the activate form can skip forcing
    a re-scan for a returning person-client and prefill those fields.

    Deliberately does NOT return the licence *photo*: the image is sensitive PII
    and this endpoint is org-wide login-gated with an enumerable client id, so
    exposing the photo would be a harvesting vector. The activate endpoint reuses
    the actual photo server-side (see get_latest_license_for_client), so the client
    never needs the bytes. Returns {success, has_license, driver_license_number,
    driver_license_expiry}."""
    lic = _fp_repo.get_latest_license_for_client(client_id) or {}
    return jsonify({
        'success': True,
        'has_license': bool((lic.get('driver_license_photo') or '').strip()),
        'driver_license_number': lic.get('driver_license_number'),
        'driver_license_expiry': lic.get('driver_license_expiry'),
    })


# ════════════════════════════════════════════════════════════════
# Create new client
# ════════════════════════════════════════════════════════════════

# International E.164 (+ and 7–15 digits) plus legacy RO national formats so
# existing stored numbers still validate.
_PHONE_RE = re.compile(r'^(\+\d{7,15}|07\d{8}|004\d{10})$')


@foi_parcurs_bp.route('/api/foi-parcurs/clients', methods=['POST'])
@login_required
def api_create_client():
    """Create a new individual person client for foi de parcurs."""
    data = request.get_json(silent=True) or {}

    # Validate required fields
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400

    phone = (data.get('phone') or '').strip()
    if not phone:
        return jsonify({'success': False, 'error': 'phone is required'}), 400

    # Validate phone format: international E.164 (+…) or legacy RO national.
    phone_clean = phone.replace(' ', '').replace('-', '')
    if not _PHONE_RE.match(phone_clean):
        return jsonify({
            'success': False,
            'error': 'Invalid phone. Use international format, e.g. +40721234567',
        }), 400

    id_document_no = (data.get('id_document_no') or '').strip()
    if not id_document_no:
        return jsonify({'success': False, 'error': 'id_document_no is required'}), 400

    id_document_type = (data.get('id_document_type') or 'ID_CARD').strip()
    if id_document_type not in ('ID_CARD', 'PASSPORT', 'DRIVER_LICENSE'):
        return jsonify({'success': False, 'error': 'Invalid id_document_type'}), 400

    if id_document_type == 'DRIVER_LICENSE' and not (data.get('driver_license_combined') or '').strip():
        return jsonify({'success': False, 'error': 'driver_license_combined is required for DRIVER_LICENSE'}), 400

    client_data = {
        'name': name,
        'phone': phone_clean,
        'id_document_type': id_document_type,
        'id_document_no': id_document_no,
    }

    # Optional fields
    if data.get('email'):
        client_data['email'] = data['email'].strip()
    if data.get('date_of_birth'):
        client_data['date_of_birth'] = data['date_of_birth']
    if data.get('driver_license_combined'):
        client_data['driver_license_combined'] = data['driver_license_combined'].strip()
    if data.get('address'):
        client_data['address'] = data['address'].strip()

    try:
        client = _client_repo.create_client(client_data)
        return jsonify({'success': True, 'client': client})
    except Exception as e:
        logger.exception('Failed to create client')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500
