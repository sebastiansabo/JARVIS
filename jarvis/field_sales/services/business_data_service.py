"""Business Data Enrichment Service.

Fetches company data from multiple Romanian business data APIs
(Termene.ro, RisCo, ListaFirme, OpenAPI.ro, FirmeAPI.ro)
using connector credentials from the connectors table.
"""
import json
import logging
from datetime import datetime

import requests

from core.connectors.repositories.connector_repository import ConnectorRepository

logger = logging.getLogger('jarvis.business_data')

_connector_repo = ConnectorRepository()


def _get_connector_config(connector_type):
    """Get config and credentials for a connector.

    Returns:
        tuple: (config_dict, credentials_dict, connector_row) or (None, None, None)
    """
    row = _connector_repo.get_by_type(connector_type)
    if not row or row.get('status') != 'connected':
        return None, None, None

    config = row.get('config') or {}
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (json.JSONDecodeError, TypeError):
            config = {}

    creds = row.get('credentials') or {}
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except (json.JSONDecodeError, TypeError):
            creds = {}

    return config, creds, row


def fetch_termene(cui):
    """Fetch company data from Termene.ro API.

    API: POST /api/dateFirmaSumar.php
    Auth: username + password in request body
    """
    config, creds, _ = _get_connector_config('termene')
    if not config or not creds:
        return None

    username = creds.get('username')
    password = creds.get('password')
    if not username or not password:
        return None

    endpoint = config.get('api_endpoint', 'https://termene.ro/api/dateFirmaSumar.php')
    timeout = config.get('timeout_seconds', 10)

    try:
        resp = requests.post(
            endpoint,
            data={'cui': str(cui).strip(), 'username': username, 'password': password},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data
    except Exception as e:
        logger.warning('Termene.ro API error for CUI %s: %s', cui, str(e))
        return None


def fetch_risco(cui):
    """Fetch company data from RisCo.ro API.

    API: GET /v3/api/external/firmeSumar?cui=CUI
    Auth: api_key query param
    """
    config, creds, _ = _get_connector_config('risco')
    if not config or not creds:
        return None

    api_key = creds.get('api_key')
    if not api_key:
        return None

    base_url = config.get('api_endpoint', 'https://www.risco.ro/v3/api/external')
    timeout = config.get('timeout_seconds', 10)

    try:
        resp = requests.get(
            f'{base_url}/firmeSumar',
            params={'cui': str(cui).strip(), 'api_key': api_key},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning('RisCo API error for CUI %s: %s', cui, str(e))
        return None


def fetch_listafirme(cui):
    """Fetch company data from ListaFirme.eu API.

    API: GET /api/info-v1.asp?api_key=KEY&cui=CUI
    Auth: api_key query param
    """
    config, creds, _ = _get_connector_config('listafirme')
    if not config or not creds:
        return None

    api_key = creds.get('api_key')
    if not api_key:
        return None

    endpoint = config.get('api_endpoint', 'https://listafirme.ro/api/info-v1.asp')
    timeout = config.get('timeout_seconds', 10)

    try:
        resp = requests.get(
            endpoint,
            params={'api_key': api_key, 'cui': str(cui).strip()},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning('ListaFirme API error for CUI %s: %s', cui, str(e))
        return None


def fetch_openapi_ro(cui):
    """Fetch company data from OpenAPI.ro.

    API: GET /api/companies/{cui}
    Auth: api_key in X-API-KEY header
    """
    config, creds, _ = _get_connector_config('openapi_ro')
    if not config or not creds:
        return None

    api_key = creds.get('api_key')
    if not api_key:
        return None

    base_url = config.get('api_endpoint', 'https://api.openapi.ro/api/companies')
    timeout = config.get('timeout_seconds', 10)

    try:
        resp = requests.get(
            f'{base_url}/{str(cui).strip()}',
            headers={'X-API-KEY': api_key},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning('OpenAPI.ro error for CUI %s: %s', cui, str(e))
        return None


def fetch_firmeapi(cui):
    """Fetch company data from FirmeAPI.ro.

    API: GET /api/v1/companies/{cui}
    Auth: api_key in Authorization header
    """
    config, creds, _ = _get_connector_config('firmeapi')
    if not config or not creds:
        return None

    api_key = creds.get('api_key')
    if not api_key:
        return None

    base_url = config.get('api_endpoint', 'https://www.firmeapi.ro/api/v1')
    timeout = config.get('timeout_seconds', 10)

    try:
        resp = requests.get(
            f'{base_url}/companies/{str(cui).strip()}',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning('FirmeAPI.ro error for CUI %s: %s', cui, str(e))
        return None


# Registry of fetch functions by connector type
CONNECTOR_FETCHERS = {
    'termene': fetch_termene,
    'risco': fetch_risco,
    'listafirme': fetch_listafirme,
    'openapi_ro': fetch_openapi_ro,
    'firmeapi': fetch_firmeapi,
}


def get_connected_business_connectors():
    """Get list of business data connectors that are connected (have credentials).

    Returns:
        list of dicts with connector_type, name, status
    """
    rows = _connector_repo.get_all()
    result = []
    for r in rows:
        ct = r.get('connector_type')
        if ct not in CONNECTOR_FETCHERS and ct != 'anaf':
            continue
        result.append({
            'connector_type': ct,
            'name': r.get('name'),
            'status': r.get('status'),
            'id': r.get('id'),
        })
    return result


def enrich_from_connector(cui, connector_type):
    """Fetch company data from a specific connector.

    Args:
        cui: Romanian CUI (fiscal code)
        connector_type: one of the CONNECTOR_FETCHERS keys

    Returns:
        dict with API response data, or None
    """
    fetcher = CONNECTOR_FETCHERS.get(connector_type)
    if not fetcher:
        return None
    return fetcher(cui)


def enrich_from_all_connected(cui):
    """Fetch company data from all connected business data connectors.

    Args:
        cui: Romanian CUI

    Returns:
        dict keyed by connector_type with API response data
    """
    results = {}
    for ct, fetcher in CONNECTOR_FETCHERS.items():
        config, creds, _ = _get_connector_config(ct)
        if config is None:
            continue  # not connected
        try:
            data = fetcher(cui)
            if data:
                results[ct] = {
                    'data': data,
                    'fetched_at': datetime.now().isoformat(),
                }
        except Exception as e:
            logger.warning('Enrichment from %s failed for CUI %s: %s', ct, cui, str(e))
            results[ct] = {
                'error': str(e),
                'fetched_at': datetime.now().isoformat(),
            }
    return results
