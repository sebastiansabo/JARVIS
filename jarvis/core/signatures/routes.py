"""Signature API routes."""
import logging
from flask import jsonify, request
from flask_login import login_required, current_user
from . import signatures_bp
from .repositories import SignatureRepository
from .services import SignatureService

logger = logging.getLogger('jarvis.core.signatures.routes')

_repo = SignatureRepository()
_service = SignatureService()


@signatures_bp.route('/api/request', methods=['POST'])
@login_required
def api_request_signature():
    """Create a new signature request."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    document_type = data.get('document_type')
    document_id = data.get('document_id')
    if not document_type or not document_id:
        return jsonify({'success': False, 'error': 'document_type and document_id required'}), 400

    try:
        sig = _service.request_signature(
            document_type=document_type,
            document_id=int(document_id),
            signed_by=data.get('signed_by', current_user.id),
            original_pdf_path=data.get('original_pdf_path'),
            callback_url=data.get('callback_url'),
        )
        return jsonify({'success': True, 'signature': sig})
    except Exception as e:
        logger.error(f'Failed to create signature request: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@signatures_bp.route('/api/<int:sig_id>', methods=['GET'])
@login_required
def api_get_signature(sig_id):
    """Get signature status and metadata (no base64 image in response)."""
    sig = _repo.get_by_id(sig_id)
    if not sig:
        return jsonify({'success': False, 'error': 'Signature not found'}), 404

    # Strip base64 image from GET response for performance
    result = {k: v for k, v in sig.items() if k != 'signature_image'}
    result['has_signature_image'] = bool(sig.get('signature_image'))
    return jsonify({'success': True, 'signature': result})


@signatures_bp.route('/api/pending', methods=['GET'])
@login_required
def api_pending_signatures():
    """List current user's pending signature requests."""
    sigs = _repo.get_pending_for_user(current_user.id)
    return jsonify({'success': True, 'signatures': sigs})


@signatures_bp.route('/api/document/<document_type>/<int:document_id>', methods=['GET'])
@login_required
def api_document_signatures(document_type, document_id):
    """Get all signatures for a specific document."""
    sigs = _repo.get_for_document(document_type, document_id)
    # Strip base64 images for list response
    results = []
    for s in sigs:
        result = {k: v for k, v in s.items() if k != 'signature_image'}
        result['has_signature_image'] = bool(s.get('signature_image'))
        results.append(result)
    return jsonify({'success': True, 'signatures': results})


@signatures_bp.route('/api/<int:sig_id>/sign', methods=['POST'])
@login_required
def api_sign(sig_id):
    """Submit a signature for a pending request."""
    sig = _repo.get_by_id(sig_id)
    if not sig:
        return jsonify({'success': False, 'error': 'Signature not found'}), 404

    if sig['signed_by'] != current_user.id:
        return jsonify({'success': False, 'error': 'Not authorized to sign this document'}), 403

    data = request.get_json()
    if not data or not data.get('signature_image'):
        return jsonify({'success': False, 'error': 'signature_image required'}), 400

    try:
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        updated = _service.process_signature(sig_id, data['signature_image'], ip_address)
        result = {k: v for k, v in updated.items() if k != 'signature_image'}
        return jsonify({
            'success': True,
            'signature': result,
            'callback_url': updated.get('callback_url'),
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Failed to process signature {sig_id}: {e}')
        return jsonify({'success': False, 'error': 'Failed to process signature'}), 500


@signatures_bp.route('/api/<int:sig_id>/reject', methods=['POST'])
@login_required
def api_reject(sig_id):
    """Reject a signature request."""
    sig = _repo.get_by_id(sig_id)
    if not sig:
        return jsonify({'success': False, 'error': 'Signature not found'}), 404

    if sig['signed_by'] != current_user.id:
        return jsonify({'success': False, 'error': 'Not authorized to reject this document'}), 403

    if sig['status'] != 'pending':
        return jsonify({'success': False, 'error': f'Cannot reject: status is {sig["status"]}'}), 400

    try:
        _repo.update_status(sig_id, 'rejected')
        return jsonify({
            'success': True,
            'callback_url': sig.get('callback_url'),
        })
    except Exception as e:
        logger.error(f'Failed to reject signature {sig_id}: {e}')
        return jsonify({'success': False, 'error': 'Failed to reject signature'}), 500
