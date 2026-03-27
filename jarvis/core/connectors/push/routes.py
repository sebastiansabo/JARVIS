"""Push notification connector routes — Firebase config, test, device management."""

import json
import logging
import os

from flask import request, jsonify
from core.utils.api_helpers import api_login_required
from core.connectors.repositories.connector_repository import ConnectorRepository
from flask_login import current_user

from . import push_bp

logger = logging.getLogger('jarvis.push.routes')
_connector_repo = ConnectorRepository()

CONNECTOR_TYPE = 'firebase'
SERVICE_ACCOUNT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'service-account.json')
)


# ── Config ──

@push_bp.route('/api/config', methods=['GET'])
@api_login_required
def get_config():
    """Get push notification connector config."""
    connector = _connector_repo.get_by_type(CONNECTOR_TYPE)

    # Check if service-account.json exists on disk
    file_exists = os.path.exists(SERVICE_ACCOUNT_PATH)
    project_id = None
    if file_exists:
        try:
            with open(SERVICE_ACCOUNT_PATH) as f:
                sa = json.load(f)
                project_id = sa.get('project_id')
        except Exception:
            pass

    if not connector:
        return jsonify({
            'success': True,
            'data': {
                'status': 'disconnected',
                'project_id': project_id,
                'file_exists': file_exists,
                'config': {},
            }
        })

    config = connector.get('config', {})
    if isinstance(config, str):
        config = json.loads(config)

    return jsonify({
        'success': True,
        'data': {
            'id': connector['id'],
            'status': connector['status'],
            'project_id': project_id or config.get('project_id'),
            'file_exists': file_exists,
            'last_error': connector.get('last_error'),
            'config': {
                'project_id': config.get('project_id'),
                'client_email': config.get('client_email'),
            },
        }
    })


@push_bp.route('/api/config', methods=['POST'])
@api_login_required
def save_config():
    """Save Firebase service account JSON — writes to disk and stores metadata in connector."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'JSON body required'}), 400

    service_account_json = data.get('service_account_json')
    if not service_account_json:
        return jsonify({'success': False, 'error': 'service_account_json is required'}), 400

    # Validate JSON structure
    try:
        if isinstance(service_account_json, str):
            sa = json.loads(service_account_json)
        else:
            sa = service_account_json
    except json.JSONDecodeError:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    required_fields = ['project_id', 'private_key', 'client_email']
    missing = [f for f in required_fields if f not in sa]
    if missing:
        return jsonify({'success': False, 'error': f'Missing fields: {", ".join(missing)}'}), 400

    # Write service-account.json to disk
    try:
        with open(SERVICE_ACCOUNT_PATH, 'w') as f:
            json.dump(sa, f, indent=2)
        logger.info('Saved Firebase service-account.json (project: %s)', sa['project_id'])
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to write file: {e}'}), 500

    # Store metadata + full credentials in connectors table
    config = {
        'project_id': sa['project_id'],
        'client_email': sa['client_email'],
    }

    existing = _connector_repo.get_by_type(CONNECTOR_TYPE)
    if existing:
        _connector_repo.update(
            existing['id'],
            name='Firebase Cloud Messaging',
            status='connected',
            config=config,
            credentials=sa,
        )
        connector_id = existing['id']
    else:
        connector_id = _connector_repo.save(
            connector_type=CONNECTOR_TYPE,
            name='Firebase Cloud Messaging',
            status='connected',
            config=config,
            credentials=sa,
        )

    # Reset Firebase SDK so it re-initializes with new credentials
    from core.notifications.push_service import _init_firebase
    import core.notifications.push_service as ps
    ps._firebase_app = None

    return jsonify({'success': True, 'connector_id': connector_id})


@push_bp.route('/api/test', methods=['POST'])
@api_login_required
def test_push():
    """Send a test push notification to the current user's devices."""
    from database import get_db_connection

    user_id = current_user.id

    # Check if user has registered devices
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT COUNT(*) FROM mobile_devices WHERE user_id = %s',
                (user_id,),
            )
            count = cur.fetchone()[0]

    if count == 0:
        return jsonify({
            'success': False,
            'error': 'No registered devices. Open the mobile app first to register your device.',
        }), 400

    # Try sending
    from core.notifications.push_service import send_push_to_users
    try:
        send_push_to_users(
            user_ids=[user_id],
            title='JARVIS Test',
            body='Push notifications are working!',
            data={'type': 'test'},
        )
        return jsonify({'success': True, 'message': f'Test notification sent to {count} device(s)'})
    except Exception as e:
        logger.error('Test push failed: %s', e)
        # Update connector status
        connector = _connector_repo.get_by_type(CONNECTOR_TYPE)
        if connector:
            _connector_repo.update(connector['id'], status='error', last_error=str(e))
        return jsonify({'success': False, 'error': str(e)}), 500


@push_bp.route('/api/devices', methods=['GET'])
@api_login_required
def list_devices():
    """List all registered devices."""
    from database import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT md.id, md.user_id, u.name as user_name, md.platform,
                       md.device_id, md.created_at, md.updated_at,
                       LEFT(md.push_token, 20) || '...' as token_preview
                FROM mobile_devices md
                JOIN users u ON u.id = md.user_id
                ORDER BY md.updated_at DESC
            ''')
            cols = [d[0] for d in cur.description]
            devices = [dict(zip(cols, r)) for r in cur.fetchall()]
            for d in devices:
                if d.get('created_at'):
                    d['created_at'] = str(d['created_at'])
                if d.get('updated_at'):
                    d['updated_at'] = str(d['updated_at'])

    return jsonify({'success': True, 'data': devices, 'total': len(devices)})


@push_bp.route('/api/devices/<int:device_id>', methods=['DELETE'])
@api_login_required
def delete_device(device_id):
    """Remove a registered device."""
    from database import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM mobile_devices WHERE id = %s', (device_id,))
        conn.commit()

    return jsonify({'success': True})
