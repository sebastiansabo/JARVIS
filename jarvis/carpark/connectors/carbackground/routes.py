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
import threading

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


def _preferred(cfg):
    """The curated background list, falling back to the single legacy
    `background_id` so pre-feature connectors still expose their one backdrop."""
    ids = cfg.get('preferred_background_ids')
    if isinstance(ids, list):
        ids = [str(i).strip() for i in ids if str(i).strip()]
        if ids:
            return ids
    bg = cfg.get('background_id')
    return [bg] if bg else []


def _safe(c):
    creds = _json(c.get('credentials'))
    cfg = _json(c.get('config'))
    return {'id': c['id'], 'status': c.get('status'),
            'has_api_key': bool(creds.get('api_key')),
            'background_id': cfg.get('background_id') or '',
            'preferred_background_ids': _preferred(cfg),
            'api_base_url': cfg.get('api_base_url') or '',
            'last_error': c.get('last_error')}


def _validate_default_in_preferred(cfg):
    """The house default must be one of the preferred backgrounds."""
    bg = cfg.get('background_id')
    prefs = cfg.get('preferred_background_ids')
    if bg and isinstance(prefs, list) and prefs and bg not in prefs:
        return jsonify({'success': False,
                        'error': 'background_id must be one of preferred_background_ids'}), 400
    return None


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
    preferred_raw = data.get('preferred_background_ids')
    preferred = None
    if isinstance(preferred_raw, list):
        preferred = [str(i).strip() for i in preferred_raw if str(i).strip()]
    c = _repo.get_by_type(CONNECTOR_TYPE)
    if not c:
        creds = {'api_key': api_key} if api_key else {}
        cfg = {k: v for k, v in (('background_id', background_id),) if v}
        if preferred is not None:
            cfg['preferred_background_ids'] = preferred
        err = _validate_default_in_preferred(cfg)
        if err:
            return err
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
        if preferred is not None:
            cfg['preferred_background_ids'] = preferred
        err = _validate_default_in_preferred(cfg)
        if err:
            return err
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

def _progress(log_id, vid, ids, bg, created, done, errors, status):
    """Patch the job's sync-log with the current count (and terminal status on
    the final call). Best-effort: a logging hiccup must not kill the job."""
    if not log_id:
        return
    try:
        _repo.update_sync_log(
            log_id, status=status, invoices_imported=created,
            details={'vehicle_id': vid, 'requested': len(ids), 'created': created,
                     'done': done, 'errors': errors, 'background_id': bg,
                     'finished': status is not None})
    except Exception:  # noqa: BLE001
        logger.warning('carbackground: progress update failed (log=%s)', log_id)


def _run_enhance_job(vid, ids, bg, connector_id, log_id):
    """Off-request worker (daemon thread): enhance each photo independently,
    bumping the sync-log after every one for a live progress count, then flip it
    to a terminal status. A mid-batch failure (e.g. 402 out-of-credits) is
    recorded per-photo and never aborts the run; the `finally` guarantees a
    terminal log so the UI never hangs on 'running'."""
    created, processed, errors = 0, 0, []
    try:
        for pid in ids:
            # The WHOLE body is guarded (not just enhance_photo): a failure at
            # get_by_id — e.g. a stale pooled connection — must be recorded as a
            # per-photo error, never break to `finally` with an empty error list
            # and get mislabeled 'success' while dropping the rest of the batch.
            try:
                p = _photos.get_by_id(pid)
                if not p or p.get('vehicle_id') != vid:
                    errors.append(f'{pid}: not found for vehicle {vid}')
                else:
                    _service.enhance_photo(pid, background_id=bg)
                    created += 1
            except CarBackgroundError as e:
                errors.append(f'{pid}: {e.status} {e.message}')
            except Exception as e:  # noqa: BLE001
                logger.exception('carbackground enhance failed (vid=%s pid=%s)', vid, pid)
                errors.append(f'{pid}: {e}')
            processed += 1
            _progress(log_id, vid, ids, bg, created, processed, errors, status=None)
    finally:
        status = 'success' if not errors else ('partial' if created else 'error')
        _progress(log_id, vid, ids, bg, created, len(ids), errors, status=status)


@carbackground_bp.route('/api/vehicles/<int:vid>/enhance', methods=['POST'])
@login_required
@carpark_edit_required
def api_enhance(vid):
    """Queue a background studio-enhance for the given photo_ids. Validates then
    returns 202 immediately; a daemon worker processes each photo and writes a
    'running' sync-log that /enhance/status polls. The job keeps running even if
    the user closes the gallery or navigates away."""
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

    # Optional per-batch background override; validate once up front so an
    # off-list background fails the whole request cleanly (vs. per-photo noise).
    bg = (data.get('background_id') or '').strip() or None
    if bg is not None:
        try:
            _service.resolve_background_id(bg)
        except CarBackgroundError as e:
            return jsonify({'success': False, 'error': e.message}), e.status

    c = _repo.get_by_type(CONNECTOR_TYPE)
    if not c:
        return jsonify({'success': False, 'error': 'carbackground connector not configured'}), 400

    log_id = _repo.add_sync_log(
        c['id'], 'carbackground_enhance', 'running',
        invoices_found=len(ids), invoices_imported=0,
        details={'vehicle_id': vid, 'requested': len(ids), 'created': 0,
                 'done': 0, 'errors': [], 'background_id': bg, 'finished': False})

    threading.Thread(target=_run_enhance_job,
                     args=(vid, ids, bg, c['id'], log_id), daemon=True).start()
    return jsonify({'success': True, 'vehicle_id': vid, 'queued': len(ids),
                    'job_id': log_id}), 202


@carbackground_bp.route('/api/vehicles/<int:vid>/enhance/status', methods=['GET'])
@login_required
@carpark_edit_required
def api_enhance_status(vid):
    """Latest background-enhance job state for one vehicle — the gallery polls
    this to show live progress and to resume the indicator after a reload."""
    _, err = _verify_vehicle_ownership(vid)
    if err:
        return err
    idle = {'success': True, 'running': False, 'total': 0, 'done': 0,
            'created': 0, 'errors': [], 'background_id': None}
    c = _repo.get_by_type(CONNECTOR_TYPE)
    if not c:
        return jsonify(idle)
    log = _repo.get_latest_sync_log(c['id'], 'carbackground_enhance', vid)
    if not log:
        return jsonify(idle)
    d = _json(log.get('details'))
    return jsonify({'success': True, 'running': log.get('status') == 'running',
                    'total': log.get('invoices_found') or d.get('requested', 0),
                    'done': d.get('done', log.get('invoices_imported', 0)),
                    'created': d.get('created', log.get('invoices_imported', 0)),
                    'errors': d.get('errors', []),
                    'background_id': d.get('background_id')})


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
