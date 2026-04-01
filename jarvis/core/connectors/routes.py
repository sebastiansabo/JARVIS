"""Connectors API Routes.

Generic connector listing and update endpoints.
"""
import json
import logging

from flask import jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from core.utils.api_helpers import error_response

from . import connectors_bp
from .repositories.connector_repository import ConnectorRepository

logger = logging.getLogger('jarvis.connectors')

_repo = ConnectorRepository()

# Business-data connector types (shown in Settings → Connectors)
BUSINESS_CONNECTOR_TYPES = {'anaf', 'termene', 'risco', 'listafirme', 'openapi_ro', 'firmeapi'}


@connectors_bp.route('/buffer')
@login_required
def buffer():
    """Buffer page - currently disabled."""
    flash('Connectors feature is coming soon.', 'info')
    return redirect(url_for('accounting'))


def _safe_row(r):
    """Strip sensitive credentials from a connector row."""
    row = dict(r)
    creds = row.get('credentials')
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except (json.JSONDecodeError, TypeError):
            creds = {}
    if isinstance(creds, dict):
        row['credential_fields'] = {k: ('••••••' if v else '') for k, v in creds.items()}
    else:
        row['credential_fields'] = {}
    row.pop('credentials', None)
    return row


@connectors_bp.route('/api/connectors', methods=['GET'])
@login_required
def api_get_connectors():
    """Get all connectors, optionally filtered by category."""
    category = request.args.get('category')
    rows = _repo.get_all()

    if category == 'business':
        rows = [r for r in rows if r.get('connector_type') in BUSINESS_CONNECTOR_TYPES]

    return jsonify({'connectors': [_safe_row(r) for r in rows]})


@connectors_bp.route('/api/connectors/<int:connector_id>', methods=['PUT'])
@login_required
def api_update_connector(connector_id):
    """Update connector credentials/config."""
    data = request.get_json(silent=True) or {}
    connector = _repo.get(connector_id)
    if not connector:
        return error_response('Connector not found', 404)

    credentials = data.get('credentials')
    config = data.get('config')
    status = data.get('status')

    # Merge credentials — only update fields that are non-empty
    if credentials and isinstance(credentials, dict):
        existing = connector.get('credentials') or {}
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        for k, v in credentials.items():
            if v:  # only overwrite if non-empty
                existing[k] = v
        credentials = existing

    _repo.update(
        connector_id,
        status=status,
        config=config,
        credentials=credentials,
    )

    updated = _repo.get(connector_id)
    return jsonify({'success': True, 'connector': _safe_row(updated)})
