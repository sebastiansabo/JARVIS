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

_BUSINESS_SEEDS = [
    ('anaf', 'ANAF Public API', 'connected',
     {"api_endpoint": "https://webservicesp.anaf.ro/PlatitorTvaRest/api/v8/ws/tva", "timeout_seconds": 5, "cache_hours": 24, "description": "Free government API. VAT status, company identification, fiscal activity. No auth needed. Max 500 CUIs/request."},
     {}),
    ('termene', 'Termene.ro', 'disconnected',
     {"api_endpoint": "https://termene.ro/api/dateFirmaSumar.php", "timeout_seconds": 10, "cache_hours": 24, "description": "Most comprehensive Romanian business data. Financial indicators, court cases, insolvency risk, shareholders, beneficial owners, public contracts. Subscription required."},
     {"username": "", "password": ""}),
    ('risco', 'RisCo.ro', 'disconnected',
     {"api_endpoint": "https://www.risco.ro/v3/api/external", "timeout_seconds": 10, "cache_hours": 24, "description": "Risk assessment & credit scoring. 20+ endpoints: financial rating (RAT), insolvency probability (PIM), company valuation (VAL), court cases (JST), tax debts (RES). Pay-per-query from 0.2 RON."},
     {"api_key": ""}),
    ('listafirme', 'ListaFirme.eu', 'disconnected',
     {"api_endpoint": "https://listafirme.ro/api/info-v1.asp", "search_endpoint": "https://listafirme.ro/api/search-v1.asp", "timeout_seconds": 10, "cache_hours": 24, "description": "Granular company data with view-based pricing. Balance sheets, shareholders, beneficial owners, trademarks, connected companies. Pay only for fields requested."},
     {"api_key": ""}),
    ('openapi_ro', 'OpenAPI.ro', 'disconnected',
     {"api_endpoint": "https://api.openapi.ro/api/companies", "timeout_seconds": 10, "cache_hours": 24, "description": "Developer-friendly Romanian company API. Identification, address, VAT status, financial data. Free tier: 100 req/month."},
     {"api_key": ""}),
    ('firmeapi', 'FirmeAPI.ro', 'disconnected',
     {"api_endpoint": "https://www.firmeapi.ro/api/v1", "timeout_seconds": 10, "cache_hours": 24, "description": "Fast REST API (<100ms). Company details, financial statements (/bilant), tax debts (/restante), Official Gazette (/mof). Free tier: 100/day."},
     {"api_key": ""}),
]

_seeded = False


def _ensure_business_seeds():
    """Seed business connectors if they don't exist yet (runs once per process)."""
    global _seeded
    if _seeded:
        return
    _seeded = True
    try:
        existing = {r['connector_type'] for r in _repo.get_all() if r.get('connector_type') in BUSINESS_CONNECTOR_TYPES}
        for ct, name, status, config, creds in _BUSINESS_SEEDS:
            if ct not in existing:
                _repo.save(ct, name, status=status, config=config, credentials=creds)
                logger.info('Seeded business connector: %s', ct)
    except Exception:
        logger.exception('Failed to seed business connectors')


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
    _ensure_business_seeds()
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
