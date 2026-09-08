"""AutoFox connector routes.

Inbound (called by AutoFox, token-authenticated, no session):
    POST /autofox/webhook            JSON  {vin, images:[url|{url,...}]}  (tolerant)
                                     or multipart: vin=<VIN> files=<image>...
Admin (session-authenticated):
    GET  /autofox/api/config         status, webhook URL, masked token
    POST /autofox/api/config         create/rotate inbound token, set options
    GET  /autofox/api/logs           recent deliveries
"""
import hmac
import json
import logging
import secrets

from flask import request, jsonify, current_app

from . import autofox_bp
from .service import (AutofoxIngestService, AutofoxIngestError, extract_delivery,
                      CONNECTOR_TYPE, MAX_IMAGES_PER_DELIVERY)
from .client import AutofoxClient
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.services import spaces_service
from core.utils.api_helpers import api_login_required

logger = logging.getLogger('jarvis.autofox.routes')

_repo = ConnectorRepository()
_service = AutofoxIngestService()
_client = AutofoxClient()

_TOKEN_HEADERS = ('X-Autofox-Token', 'X-API-Key', 'X-Api-Key')
RAW_LOG_LIMIT = 8000


def _json(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return {}
    return v or {}


def _connector():
    return _repo.get_by_type(CONNECTOR_TYPE)


def _presented_token() -> str:
    auth = request.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    if request.authorization and request.authorization.password:
        return request.authorization.password
    for h in _TOKEN_HEADERS:
        if request.headers.get(h):
            return request.headers[h].strip()
    return (request.args.get('token') or '').strip()


def _client_ip() -> str:
    xff = request.headers.get('X-Forwarded-For', '')
    return (xff.split(',')[0].strip() if xff else request.remote_addr) or ''


def _authorize(connector) -> bool:
    """Hard authentication gate = the shared bearer token only.

    The IP allowlist is deliberately NOT enforced here (see `_ip_allowed`):
    `_client_ip()` trusts X-Forwarded-For, which the caller can spoof, and
    JARVIS runs with no trusted-proxy (ProxyFix) config — so an IP check
    would be false assurance, not a real boundary.
    """
    if not connector or connector.get('status') == 'disabled':
        return False
    expected = _json(connector.get('credentials')).get('inbound_token') or ''
    if not expected:
        return False
    return hmac.compare_digest(expected, _presented_token())


def _ip_allowed(connector) -> bool:
    """Advisory only: True if no allowlist is set or the best-effort client IP
    is in it. Spoofable — used for logging/visibility, never to reject."""
    allowed = _json(connector.get('config')).get('allowed_ips') or []
    return not allowed or _client_ip() in allowed


def _webhook_url() -> str:
    base = current_app.config.get('APP_BASE_URL', 'https://jarvis.autoworld.ro').rstrip('/')
    return f'{base}/autofox/webhook'


# ── Inbound webhook ──

@autofox_bp.route('/webhook', methods=['POST'])
def webhook():
    connector = _connector()
    if not _authorize(connector):
        logger.warning('AutoFox webhook rejected from %s', _client_ip())
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    cfg = _json(connector.get('config'))
    ip_ok = _ip_allowed(connector)
    if not ip_ok:
        logger.warning('AutoFox delivery from non-allowlisted IP %s (advisory, not blocked)', _client_ip())
    raw_blobs, payload = [], None
    if request.files:
        raw_blobs = [f.read() for f in request.files.getlist('files') + request.files.getlist('file')
                     + [f for k, f in request.files.items() if k not in ('files', 'file')]]
        payload = {k: v for k, v in request.form.items()}
    else:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {k: v for k, v in request.form.items()} or {}

    vin, images = extract_delivery(payload)
    if len(raw_blobs) > MAX_IMAGES_PER_DELIVERY:
        raw_blobs = raw_blobs[:MAX_IMAGES_PER_DELIVERY]

    raw_excerpt = json.dumps(payload, default=str)[:RAW_LOG_LIMIT]
    log_details = {'ip': _client_ip(), 'ip_allowed': ip_ok, 'vin': vin, 'image_refs': len(images),
                   'multipart_files': len(raw_blobs), 'raw': raw_excerpt}

    try:
        result = _service.ingest(vin, images, raw_blobs=raw_blobs,
                                 replace_existing=bool(cfg.get('replace_existing')))
    except AutofoxIngestError as e:
        _repo.add_sync_log(connector['id'], 'autofox_delivery', 'error',
                           error_message=e.message, details=log_details)
        _repo.update(connector['id'], last_error=e.message)
        return jsonify({'success': False, 'error': e.message, 'vin': vin}), e.status
    except Exception:
        logger.exception('AutoFox ingest failed (vin=%s)', vin)
        _repo.add_sync_log(connector['id'], 'autofox_delivery', 'error',
                           error_message='internal error', details=log_details)
        return jsonify({'success': False, 'error': 'Ingest failed'}), 500

    log_details.update({k: result[k] for k in ('created', 'skipped_duplicates', 'errors')})
    status = 'success' if not result['errors'] else 'partial'
    _repo.add_sync_log(connector['id'], 'autofox_delivery', status,
                       invoices_found=result['received'], invoices_imported=result['created'],
                       details=log_details)
    from datetime import datetime
    _repo.update(connector['id'], status='connected', last_sync=datetime.now(),
                 last_error=('; '.join(result['errors'])[:500] or None))
    return jsonify({'success': True, **result}), 200


# ── Admin config ──

def _safe(connector) -> dict:
    creds = _json(connector.get('credentials'))
    cfg = _json(connector.get('config'))
    tok = creds.get('inbound_token') or ''
    return {
        'id': connector['id'],
        'status': connector.get('status'),
        'webhook_url': _webhook_url(),
        'token_preview': (tok[:4] + '…' + tok[-4:]) if tok else '',
        'allowed_ips': cfg.get('allowed_ips') or [],
        'replace_existing': bool(cfg.get('replace_existing')),
        'last_sync': connector.get('last_sync'),
        'last_error': connector.get('last_error'),
    }


@autofox_bp.route('/api/config', methods=['GET'])
@api_login_required
def get_config():
    c = _connector()
    if not c:
        return jsonify({'success': True, 'configured': False, 'webhook_url': _webhook_url()})
    return jsonify({'success': True, 'configured': True, 'connector': _safe(c)})


@autofox_bp.route('/api/config', methods=['POST'])
@api_login_required
def save_config():
    """Body: {rotate_token?: bool, allowed_ips?: [..], replace_existing?: bool, enabled?: bool}
    Returns the full token ONLY when it is (re)generated — copy it to AutoFox then."""
    data = request.get_json(silent=True) or {}
    c = _connector()
    new_token = None
    if not c:
        new_token = secrets.token_urlsafe(32)
        cid = _repo.save(CONNECTOR_TYPE, 'AutoFox', status='disconnected',
                         config={'allowed_ips': data.get('allowed_ips') or [],
                                 'replace_existing': bool(data.get('replace_existing'))},
                         credentials={'inbound_token': new_token})
        c = _repo.get(cid)
    else:
        cfg = _json(c.get('config'))
        creds = _json(c.get('credentials'))
        if 'allowed_ips' in data:
            cfg['allowed_ips'] = [ip.strip() for ip in (data['allowed_ips'] or []) if ip.strip()]
        if 'replace_existing' in data:
            cfg['replace_existing'] = bool(data['replace_existing'])
        if data.get('rotate_token'):
            new_token = secrets.token_urlsafe(32)
            creds['inbound_token'] = new_token
        status = None
        if 'enabled' in data:
            status = 'disconnected' if data['enabled'] else 'disabled'
        _repo.update(c['id'], config=cfg, credentials=creds, status=status)
        c = _repo.get(c['id'])
    out = {'success': True, 'connector': _safe(c)}
    if new_token:
        out['token'] = new_token
        out['curl_example'] = (
            f"curl -X POST {_webhook_url()} -H 'Authorization: Bearer {new_token}' "
            "-H 'Content-Type: application/json' "
            "-d '{\"vin\":\"WBA...\",\"images\":[\"https://.../1.jpg\"]}'"
        )
    return jsonify(out), 201 if not c.get('last_sync') else 200


@autofox_bp.route('/api/logs', methods=['GET'])
@api_login_required
def get_logs():
    c = _connector()
    if not c:
        return jsonify({'success': True, 'logs': []})
    limit = min(int(request.args.get('limit', 20)), 100)
    return jsonify({'success': True, 'logs': _repo.get_sync_logs(c['id'], limit)})


# ── Sync-from-AutoFox pull (per-vehicle photo picker; session auth) ──

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
