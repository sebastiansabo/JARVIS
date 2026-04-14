"""Mobile signature endpoint."""
from flask import jsonify, request

from ._shared import mobile_bp, jwt_required, _sig_repo, _current_mobile_user


# ============== MOBILE SIGNATURE ==============

@mobile_bp.route('/api/signatures/sign-mobile', methods=['POST'])
@jwt_required
def api_sign_mobile():
    """Sign a document from mobile — accepts base64 signature image."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    signature_id = data.get('signature_id')
    signature_image = data.get('signature_image')  # base64

    if not signature_id or not signature_image:
        return jsonify({'error': 'signature_id and signature_image are required'}), 400

    user = _current_mobile_user()
    sig = _sig_repo.get_for_user_verification(signature_id, user.id)
    if not sig:
        return jsonify({'error': 'Signature request not found'}), 404
    status = sig['status'] if isinstance(sig, dict) else sig[1]
    if status != 'pending':
        return jsonify({'error': f'Signature already {status}'}), 400

    _sig_repo.sign_mobile(signature_id, signature_image)
    return jsonify({'success': True, 'message': 'Document signed successfully'})
