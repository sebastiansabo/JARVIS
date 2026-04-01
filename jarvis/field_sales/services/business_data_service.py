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


# ── Company-type auto-detection ────────────────────────────────

COMPANY_SUFFIXES = [
    'SRL', 'S.R.L.', 'SA', 'S.A.', 'SCS', 'S.C.S.', 'SNC', 'S.N.C.',
    'SCA', 'S.C.A.', 'RA', 'R.A.', 'PFA', 'P.F.A.', 'II', 'I.I.',
    'IF', 'I.F.', 'ONG', 'FUNDATIA', 'ASOCIATIA', 'SC',
]


def detect_company_type(name):
    """Auto-detect if a client is a company from name patterns.

    Returns 'company' if company suffixes found, else None.
    """
    if not name:
        return None
    upper = name.upper().strip()
    for suffix in COMPANY_SUFFIXES:
        # check as whole word boundary (space/start before, space/end/dot after)
        import re
        if re.search(r'(?:^|\s)' + re.escape(suffix) + r'(?:\s|$|\.)', upper):
            return 'company'
    return None


# ── Company search by name ─────────────────────────────────────

def search_company_by_name(query):
    """Search for a company by name or Nr. Reg using connected APIs.

    Tries OpenAPI.ro, ListaFirme, FirmeAPI in order.
    Returns list of dicts: [{cui, name, address, ...}] or [].
    """
    results = []

    # Try OpenAPI.ro search
    config, creds, _ = _get_connector_config('openapi_ro')
    if config and creds:
        api_key = creds.get('api_key')
        if api_key:
            try:
                base_url = config.get('api_endpoint', 'https://api.openapi.ro/api/companies')
                resp = requests.get(
                    f'{base_url}/search',
                    params={'query': query.strip()},
                    headers={'X-API-KEY': api_key},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    for item in data[:10]:
                        results.append({
                            'cui': str(item.get('cif') or item.get('cui') or ''),
                            'name': item.get('denumire') or item.get('name') or '',
                            'address': item.get('adresa') or item.get('address') or '',
                            'nr_reg': item.get('nrRegCom') or item.get('nr_reg') or '',
                            'status': item.get('stare') or item.get('status') or '',
                            'source': 'openapi_ro',
                        })
                elif isinstance(data, dict) and data.get('results'):
                    for item in data['results'][:10]:
                        results.append({
                            'cui': str(item.get('cif') or item.get('cui') or ''),
                            'name': item.get('denumire') or item.get('name') or '',
                            'address': item.get('adresa') or item.get('address') or '',
                            'nr_reg': item.get('nrRegCom') or item.get('nr_reg') or '',
                            'status': item.get('stare') or item.get('status') or '',
                            'source': 'openapi_ro',
                        })
                if results:
                    return results
            except Exception as e:
                logger.warning('OpenAPI.ro search error for "%s": %s', query, e)

    # Try ListaFirme search
    config, creds, _ = _get_connector_config('listafirme')
    if config and creds:
        api_key = creds.get('api_key')
        if api_key:
            try:
                base_url = config.get('api_endpoint', 'https://listafirme.ro/api')
                resp = requests.get(
                    f'{base_url}/search-v1.asp',
                    params={'api_key': api_key, 'q': query.strip()},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data if isinstance(data, list) else data.get('results', [])
                for item in items[:10]:
                    results.append({
                        'cui': str(item.get('cui') or item.get('cif') or ''),
                        'name': item.get('denumire') or item.get('name') or '',
                        'address': item.get('adresa') or '',
                        'nr_reg': item.get('nrRegCom') or '',
                        'source': 'listafirme',
                    })
                if results:
                    return results
            except Exception as e:
                logger.warning('ListaFirme search error for "%s": %s', query, e)

    # Try FirmeAPI search
    config, creds, _ = _get_connector_config('firmeapi')
    if config and creds:
        api_key = creds.get('api_key')
        if api_key:
            try:
                base_url = config.get('api_endpoint', 'https://www.firmeapi.ro/api/v1')
                resp = requests.get(
                    f'{base_url}/companies/search',
                    params={'q': query.strip()},
                    headers={'Authorization': f'Bearer {api_key}'},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data if isinstance(data, list) else data.get('results', data.get('data', []))
                for item in items[:10]:
                    results.append({
                        'cui': str(item.get('cui') or item.get('cif') or ''),
                        'name': item.get('denumire') or item.get('name') or '',
                        'address': item.get('adresa') or '',
                        'nr_reg': item.get('nrRegCom') or '',
                        'source': 'firmeapi',
                    })
                if results:
                    return results
            except Exception as e:
                logger.warning('FirmeAPI search error for "%s": %s', query, e)

    return results


# ── AI-powered company research ────────────────────────────────

def ai_research_company(client_data, profile_data=None, fiscal_data=None, enrichment_data=None):
    """Use Claude AI to research a company and generate intelligence.

    Args:
        client_data: dict with display_name, nr_reg, city, etc.
        profile_data: optional client_profiles record
        fiscal_data: optional ANAF data
        enrichment_data: optional enrichment from other connectors

    Returns:
        dict with research results: {summary, suggested_cui, industry, news, risks, opportunities}
    """
    import os
    try:
        import anthropic
    except ImportError:
        logger.warning('anthropic package not installed')
        return {'error': 'AI not available'}

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return {'error': 'ANTHROPIC_API_KEY not configured'}

    name = client_data.get('display_name', '')
    nr_reg = client_data.get('nr_reg', '')
    city = client_data.get('city', '')
    region = client_data.get('region', '')
    country = client_data.get('country', 'Romania')
    company_name = client_data.get('company_name', '')

    context_parts = [f"Company: {name}"]
    if nr_reg:
        context_parts.append(f"Trade Registry Nr. (Nr. Reg Comert): {nr_reg}")
    if company_name and company_name != name:
        context_parts.append(f"Also known as: {company_name}")
    if city:
        context_parts.append(f"City: {city}")
    if region:
        context_parts.append(f"Region: {region}")
    if country:
        context_parts.append(f"Country: {country}")

    if profile_data:
        if profile_data.get('cui'):
            context_parts.append(f"CUI (fiscal code): {profile_data['cui']}")
        if profile_data.get('industry'):
            context_parts.append(f"Industry: {profile_data['industry']}")

    if fiscal_data:
        context_parts.append(f"ANAF data: {json.dumps(fiscal_data, ensure_ascii=False, default=str)[:1000]}")

    if enrichment_data:
        for ct, ed in enrichment_data.items():
            if isinstance(ed, dict) and ed.get('data'):
                context_parts.append(f"{ct} data: {json.dumps(ed['data'], ensure_ascii=False, default=str)[:500]}")

    context = '\n'.join(context_parts)

    prompt = f"""You are a business intelligence analyst for a Romanian automotive dealership group (Autoworld Holding).
Analyze the following company and provide actionable intelligence.

{context}

Provide your analysis in the following JSON structure (respond ONLY with valid JSON, no markdown):
{{
  "company_overview": "Brief 2-3 sentence overview of the company",
  "suggested_cui": "The CUI/CIF fiscal code if you can determine it from the Nr. Reg or name (null if unknown)",
  "industry": "Primary industry/sector",
  "company_type": "SRL/SA/PFA/etc or the legal form",
  "estimated_size": "micro/small/medium/large based on available info",
  "risk_level": "low/medium/high",
  "key_insights": ["insight 1", "insight 2", "insight 3"],
  "opportunities": ["opportunity for automotive sales/service 1", "opportunity 2"],
  "risks": ["risk 1", "risk 2"],
  "recommended_actions": ["action 1", "action 2"],
  "fleet_potential": "Assessment of potential fleet vehicle needs",
  "news_summary": "Any known recent developments or news (or 'No recent news available')"
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1500,
            temperature=0.3,
            messages=[{'role': 'user', 'content': prompt}],
        )
        content = message.content[0].text.strip()
        # Parse JSON response
        if content.startswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        result = json.loads(content)
        result['_generated_at'] = datetime.now().isoformat()
        result['_model'] = 'claude-sonnet-4-20250514'
        return result
    except json.JSONDecodeError:
        return {'summary': content, '_generated_at': datetime.now().isoformat(), '_raw': True}
    except Exception as e:
        logger.exception('AI research failed for %s', name)
        return {'error': str(e)}
