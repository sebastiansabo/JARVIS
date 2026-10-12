"""CarBackground.ai connector routes — admin config + backgrounds/credits/logs
+ per-vehicle enhance / publish / delete-enhanced.

Session-authenticated admin config + read-only lookups:
    GET  /carbackground/api/config       status + whether the API key is set
    POST /carbackground/api/config       set api_key / background_id (admin only)
    GET  /carbackground/api/backgrounds  list available backgrounds from the API
    GET  /carbackground/api/credits      remaining credit balance
    GET  /carbackground/api/logs         recent sync-log entries

CarPark-edit-gated enhance/publish/delete (mirrors carpark/routes/photos.py's
decorator stack + ownership pattern exactly — see module docstring there):
    POST   /carbackground/api/vehicles/<vid>/enhance   {photo_ids:[int]}
    PUT    /carbackground/api/photos/<pid>/publish      {published:bool}
    DELETE /carbackground/api/photos/<pid>/enhanced
"""
import json
import logging

from flask import request, jsonify
from flask_login import login_required

from . import carbackground_bp
from .service import CONNECTOR_TYPE, CarBackgroundError, CarBackgroundEnhanceService
from .client import CarBackgroundClient
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.services import spaces_service
from core.utils.api_helpers import admin_required
from carpark.repositories.photo_repository import PhotoRepository
from carpark.routes.vehicles import carpark_required, carpark_edit_required, _verify_vehicle_ownership

logger = logging.getLogger('jarvis.carbackground.routes')

_repo = ConnectorRepository()
_client = CarBackgroundClient()
_service = CarBackgroundEnhanceService()
_photos = PhotoRepository()


def _json(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return {}
    return v or {}


def _safe(c):
    creds = _json(c.get('credentials'))
    cfg = _json(c.get('config'))
    return {'id': c['id'], 'status': c.get('status'),
            'has_api_key': bool(creds.get('api_key')),
            'background_id': cfg.get('background_id') or '',
            'api_base_url': cfg.get('api_base_url') or '',
            'last_error': c.get('last_error')}


@carbackground_bp.route('/api/config', methods=['GET'])
@carpark_required
def get_config():
    c = _repo.get_by_type(CONNECTOR_TYPE)
    if not c:
        return jsonify({'success': True, 'configured': False})
    return jsonify({'success': True, 'configured': True, 'connector': _safe(c)})


@carbackground_bp.route('/api/config', methods=['POST'])
@admin_required
def save_config():
    data = request.get_json(silent=True) or {}
    api_key = (data.get('api_key') or '').strip()
    background_id = (data.get('background_id') or '').strip()
    c = _repo.get_by_type(CONNECTOR_TYPE)
    if not c:
        creds = {'api_key': api_key} if api_key else {}
        cfg = {k: v for k, v in (('background_id', background_id),) if v}
        cid = _repo.save(CONNECTOR_TYPE, 'carbackground',
                         status='connected' if api_key else 'disconnected', config=cfg, credentials=creds)
        c = _repo.get(cid)
    else:
        creds = _json(c.get('credentials'))
        cfg = _json(c.get('config'))
        if api_key:
            creds['api_key'] = api_key
        if 'background_id' in data:
            cfg['background_id'] = background_id
        _repo.update(c['id'], config=cfg, credentials=creds,
                     status='connected' if creds.get('api_key') else 'disconnected')
        c = _repo.get(c['id'])
    return jsonify({'success': True, 'connector': _safe(c)})


@carbackground_bp.route('/api/backgrounds', methods=['GET'])
@carpark_required
def api_backgrounds():
    try:
        return jsonify({'success': True, 'backgrounds': _client.list_backgrounds()})
    except CarBackgroundError as e:
        return jsonify({'success': False, 'error': e.message}), e.status


@carbackground_bp.route('/api/credits', methods=['GET'])
@carpark_required
def api_credits():
    try:
        return jsonify({'success': True, 'balance': _client.credits()})
    except CarBackgroundError as e:
        return jsonify({'success': False, 'error': e.message}), e.status


@carbackground_bp.route('/api/logs', methods=['GET'])
@carpark_required
def api_logs():
    c = _repo.get_by_type(CONNECTOR_TYPE)
    if not c:
        return jsonify({'success': True, 'logs': []})
    try:
        limit = min(int(request.args.get('limit', 20)), 100)
    except (TypeError, ValueError):
        limit = 20
    return jsonify({'success': True, 'logs': _repo.get_sync_logs(c['id'], limit)})


# ═══════════════════════════════════════════════
# ENHANCE / PUBLISH / DELETE — vehicle-scoped enhance, photo-scoped publish+delete
# ═══════════════════════════════════════════════

@carbackground_bp.route('/api/vehicles/<int:vid>/enhance', methods=['POST'])
@login_required
@carpark_edit_required
def api_enhance(vid):
    """Enhance the given photo_ids for one vehicle. Processes each id
    independently: a mid-batch failure (e.g. 402 out-of-credits) is recorded
    per-photo and the batch still returns 200 with whatever succeeded —
    never aborts the whole request."""
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vid)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    raw = data.get('photo_ids') or []
    if not raw:
        return jsonify({'success': False, 'error': 'photo_ids is required'}), 400
    try:
        ids = [int(i) for i in raw]
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'photo_ids must be integers'}), 400

    created, errors = 0, []
    for pid in ids:
        p = _photos.get_by_id(pid)
        if not p or p.get('vehicle_id') != vid:
            errors.append(f'{pid}: not found for vehicle {vid}')
            continue
        try:
            _service.enhance_photo(pid)
            created += 1
        except CarBackgroundError as e:
            errors.append(f'{pid}: {e.status} {e.message}')
        except Exception as e:  # noqa: BLE001
            logger.exception('carbackground enhance failed (vid=%s pid=%s)', vid, pid)
            errors.append(f'{pid}: {e}')

    c = _repo.get_by_type(CONNECTOR_TYPE)
    if c:
        status = 'success' if not errors else ('partial' if created else 'error')
        _repo.add_sync_log(c['id'], 'carbackground_enhance', status,
                           invoices_found=len(ids), invoices_imported=created,
                           details={'vehicle_id': vid, 'requested': len(ids),
                                    'created': created, 'errors': errors})
    return jsonify({'success': True, 'vehicle_id': vid, 'created': created, 'errors': errors}), 200


@carbackground_bp.route('/api/photos/<int:pid>/publish', methods=['PUT'])
@login_required
@carpark_edit_required
def api_publish(pid):
    """Toggle whether a photo's enhanced variant is shown in the gallery."""
    data = request.get_json(silent=True) or {}
    published = bool(data.get('published'))
    p = _photos.get_by_id(pid)
    if not p:
        return jsonify({'success': False, 'error': 'photo not found'}), 404
    if published and not p.get('enhanced_url'):
        return jsonify({'success': False, 'error': 'no enhanced variant to publish'}), 400
    return jsonify({'success': True, 'photo': _photos.set_enhanced_published(pid, published)})


@carbackground_bp.route('/api/photos/<int:pid>/enhanced', methods=['DELETE'])
@login_required
@carpark_edit_required
def api_delete_enhanced(pid):
    """Drop the enhanced variant, resetting the photo back to its original."""
    p = _photos.get_by_id(pid)
    if not p:
        return jsonify({'success': False, 'error': 'photo not found'}), 404
    for key in (p.get('enhanced_url'), p.get('enhanced_thumbnail_url')):
        if key:
            try:
                spaces_service.delete(key)
            except Exception:  # noqa: BLE001
                logger.warning('carbackground: delete enhanced object failed: %s', key)
    return jsonify({'success': True, 'photo': _photos.clear_enhanced(pid)})
