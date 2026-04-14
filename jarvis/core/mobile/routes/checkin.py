"""Mobile NFC check-in endpoints."""
from flask import jsonify, request

from ._shared import mobile_bp, jwt_required, _checkin_repo, _current_mobile_user


# ============== NFC CHECK-IN ==============

@mobile_bp.route('/api/checkin/nfc-punch', methods=['POST'])
@jwt_required
def api_nfc_punch():
    """Check in/out via NFC tag — reuses existing CheckinService with QR token format."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    nfc_tag_id = data.get('nfc_tag_id') or ''
    if not nfc_tag_id:
        return jsonify({'error': 'nfc_tag_id is required'}), 400

    user = _current_mobile_user()
    tag = _checkin_repo.get_nfc_tag_by_tag_id(nfc_tag_id)
    if not tag:
        return jsonify({'error': 'Unknown NFC tag'}), 404

    location_id = tag['location_id'] if isinstance(tag, dict) else tag[0]

    # Reuse existing punch logic via QR token format "checkin:<location_id>"
    from core.checkin.service import CheckinService
    svc = CheckinService()
    qr_token = f'checkin:{location_id}'
    result = svc.punch(
        jarvis_user_id=user.id,
        qr_token=qr_token,
        direction=data.get('direction'),
    )
    return jsonify(result), 200 if result['success'] else 400


@mobile_bp.route('/api/checkin/nfc-tags')
@jwt_required
def api_nfc_tags():
    """List registered NFC tag-location mappings."""
    tags = _checkin_repo.get_all_nfc_tags()
    return jsonify({'success': True, 'tags': tags})
