"""CarBackground.ai connector routes — admin config + backgrounds/credits/logs.

Session-authenticated admin config + read-only lookups:
    GET  /carbackground/api/config       status + whether the API key is set
    POST /carbackground/api/config       set api_key / background_id (admin only)
    GET  /carbackground/api/backgrounds  list available backgrounds from the API
    GET  /carbackground/api/credits      remaining credit balance
    GET  /carbackground/api/logs         recent sync-log entries
"""
import json

from flask import request, jsonify

from . import carbackground_bp
from .service import CONNECTOR_TYPE, CarBackgroundError
from .client import CarBackgroundClient
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.utils.api_helpers import admin_required
from carpark.routes.vehicles import carpark_required

_repo = ConnectorRepository()
_client = CarBackgroundClient()


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
