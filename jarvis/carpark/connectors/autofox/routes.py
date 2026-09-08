"""AutoFox connector routes (read-only photo pull).

Session-authenticated admin + per-vehicle photo sync:
    GET  /autofox/api/config     status + whether the API login token is set
    POST /autofox/api/config     set login_token / api_base_url
    GET  /autofox/api/logs       recent sync-import runs
    GET  /autofox/api/photos     list AutoFox processed photos for a VIN
    GET  /autofox/api/image      thumbnail proxy (fetches AutoFox media with our Bearer)
    POST /autofox/api/import     download + store the chosen photos for a VIN
"""
import json
import logging

from flask import request, jsonify, current_app

from . import autofox_bp
from .service import AutofoxIngestService, AutofoxIngestError, CONNECTOR_TYPE
from .client import AutofoxClient
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.services import spaces_service
from core.utils.api_helpers import api_login_required

logger = logging.getLogger('jarvis.autofox.routes')

_repo = ConnectorRepository()
_service = AutofoxIngestService()
_client = AutofoxClient()


def _json(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return {}
    return v or {}


def _connector():
    return _repo.get_by_type(CONNECTOR_TYPE)


# ── Admin config (session auth) ──

def _safe(connector) -> dict:
    creds = _json(connector.get('credentials'))
    cfg = _json(connector.get('config'))
    return {
        'id': connector['id'],
        'status': connector.get('status'),
        'has_login_token': bool(creds.get('login_token')),
        'api_base_url': cfg.get('api_base_url') or '',
        'last_sync': connector.get('last_sync'),
        'last_error': connector.get('last_error'),
    }


@autofox_bp.route('/api/config', methods=['GET'])
@api_login_required
def get_config():
    c = _connector()
    if not c:
        return jsonify({'success': True, 'configured': False})
    return jsonify({'success': True, 'configured': True, 'connector': _safe(c)})


@autofox_bp.route('/api/config', methods=['POST'])
@api_login_required
def save_config():
    """Body: {login_token?, api_base_url?}. login_token is the AutoFox pull API
    credential (stored in credentials, never returned)."""
    data = request.get_json(silent=True) or {}
    login_token = (data.get('login_token') or '').strip()
    c = _connector()
    if not c:
        creds = {'login_token': login_token} if login_token else {}
        cfg = {}
        if (data.get('api_base_url') or '').strip():
            cfg['api_base_url'] = data['api_base_url'].strip()
        cid = _repo.save(CONNECTOR_TYPE, 'AutoFox',
                         status='connected' if login_token else 'disconnected',
                         config=cfg, credentials=creds)
        c = _repo.get(cid)
    else:
        cfg = _json(c.get('config'))
        creds = _json(c.get('credentials'))
        if login_token:
            creds['login_token'] = login_token
        if 'api_base_url' in data:
            cfg['api_base_url'] = (data['api_base_url'] or '').strip()
        status = 'connected' if creds.get('login_token') else 'disconnected'
        _repo.update(c['id'], config=cfg, credentials=creds, status=status)
        c = _repo.get(c['id'])
    return jsonify({'success': True, 'connector': _safe(c)})


@autofox_bp.route('/api/logs', methods=['GET'])
@api_login_required
def get_logs():
    c = _connector()
    if not c:
        return jsonify({'success': True, 'logs': []})
    limit = min(int(request.args.get('limit', 20)), 100)
    return jsonify({'success': True, 'logs': _repo.get_sync_logs(c['id'], limit)})


# ── Per-vehicle photo sync (pull) ──

@autofox_bp.route('/api/photos', methods=['GET'])
@api_login_required
def api_photos():
    """List AutoFox processed photos for a VIN, each flagged already-imported."""
    vin = (request.args.get('vin') or '').strip().upper()
    if not vin:
        return jsonify({'success': False, 'error': 'vin is required'}), 400
    try:
        photos = _client.list_conversions_by_vin(vin)
    except AutofoxIngestError as e:
        return jsonify({'success': False, 'error': e.message}), e.status
    vehicle = _service._vehicles.get_by_vin(vin)
    imported = _service.imported_conversion_ids(vehicle['id']) if vehicle else set()
    for p in photos:
        p['already_imported'] = p['conversion_id'] in imported
        p.pop('url', None)  # browser loads via the /api/image proxy using `path`
    return jsonify({
        'success': True, 'vin': vin,
        'matched_vehicle': bool(vehicle),
        'vehicle_id': vehicle['id'] if vehicle else None,
        'photos': photos,
    })


@autofox_bp.route('/api/image', methods=['GET'])
@api_login_required
def api_image():
    """Thumbnail proxy: AutoFox media needs our Bearer token, which the browser
    can't send. Fetch server-side and stream back. SSRF-safe: `path` must be a
    relative AutoFox media path (no scheme, no traversal); the client pins it to
    the configured AutoFox host and re-validates."""
    path = (request.args.get('path') or '').strip()
    if not path or '://' in path or '..' in path:
        return jsonify({'success': False, 'error': 'invalid path'}), 400
    try:
        raw = _client.download(_client.absolute_url(path))
    except AutofoxIngestError as e:
        return jsonify({'success': False, 'error': e.message}), e.status
    mime = 'image/png' if path.lower().endswith('.png') else 'image/jpeg'
    return current_app.response_class(raw, mimetype=mime,
                                      headers={'Cache-Control': 'private, max-age=300'})


@autofox_bp.route('/api/import', methods=['POST'])
@api_login_required
def api_import():
    """Download + store the chosen AutoFox conversions for a VIN."""
    data = request.get_json(silent=True) or {}
    vin = (data.get('vin') or '').strip().upper()
    ids = [str(i) for i in (data.get('conversion_ids') or [])]
    if not vin or not ids:
        return jsonify({'success': False, 'error': 'vin and conversion_ids are required'}), 400
    if not spaces_service.is_enabled():
        return jsonify({'success': False, 'error': 'Storage not configured'}), 503
    vehicle = _service._vehicles.get_by_vin(vin)
    if not vehicle:
        return jsonify({'success': False, 'error': f'No vehicle with VIN {vin}'}), 404
    vehicle_id = vehicle['id']

    try:
        available = {c['conversion_id']: c for c in _client.list_conversions_by_vin(vin)}
    except AutofoxIngestError as e:
        return jsonify({'success': False, 'error': e.message}), e.status

    already = _service.imported_conversion_ids(vehicle_id)
    had_photos = bool(_service._photos.get_by_vehicle(vehicle_id))
    created, skipped, errors = 0, 0, []
    for cid in ids:
        if cid in already:
            skipped += 1
            continue
        conv = available.get(cid)
        if not conv:
            errors.append(f'{cid}: not found for VIN {vin}')
            continue
        try:
            raw = _client.download(conv['url'])
            _service.store_photo_bytes(vehicle_id, raw, cid,
                                       make_primary=(not had_photos and created == 0))
            created += 1
        except AutofoxIngestError as e:
            errors.append(f'{cid}: {e.message}')
        except Exception as e:  # noqa: BLE001
            logger.exception('AutoFox import failed (vin=%s cid=%s)', vin, cid)
            errors.append(f'{cid}: {e}')

    connector = _connector()
    if connector:
        status = 'success' if not errors else ('partial' if created else 'error')
        _repo.add_sync_log(connector['id'], 'autofox_pull_import', status,
                           invoices_found=len(ids), invoices_imported=created,
                           details={'vin': vin, 'vehicle_id': vehicle_id,
                                    'requested': len(ids), 'created': created,
                                    'skipped_duplicates': skipped, 'errors': errors})
    return jsonify({'success': True, 'vin': vin, 'vehicle_id': vehicle_id,
                    'created': created, 'skipped_duplicates': skipped, 'errors': errors}), 200
