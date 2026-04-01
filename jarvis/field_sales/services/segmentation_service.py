"""Client segmentation, ANAF enrichment, and renewal scoring for Field Sales.

All DB operations go through a repository instance passed in — this service
never calls get_db/release_db directly.
"""

import logging
import re
from datetime import datetime, timedelta

import requests

logger = logging.getLogger('jarvis.field_sales.segmentation')

# ── Country / legal-form detection from company suffix ──────────────────

_SUFFIX_MAP = [
    # Romania
    (r'\bS\.?R\.?L\.?\b', 'RO', 'SRL', 'suffix'),
    (r'\bS\.?A\.?\b', 'RO', 'SA', 'suffix'),
    (r'\bS\.?C\.?\b', 'RO', None, 'suffix'),
    (r'\bP\.?F\.?A\.?\b', 'RO', 'PFA', 'suffix'),
    (r'\bI\.?I\.?\b', 'RO', 'II', 'suffix'),
    # Germany
    (r'\bGmbH\b', 'DE', 'GmbH', 'suffix'),
    (r'\bAG\b', 'DE', 'AG', 'suffix'),
    (r'\bKG\b', 'DE', 'KG', 'suffix'),
    (r'\bOHG\b', 'DE', 'OHG', 'suffix'),
    (r'\bUG\b', 'DE', 'UG', 'suffix'),
    # Hungary
    (r'\bKft\.?\b', 'HU', 'Kft', 'suffix'),
    (r'\bZrt\.?\b', 'HU', 'Zrt', 'suffix'),
    (r'\bNyrt\.?\b', 'HU', 'Nyrt', 'suffix'),
    (r'\bBt\.?\b', 'HU', 'Bt', 'suffix'),
    # Bulgaria
    (r'\bEOOD\b', 'BG', 'EOOD', 'suffix'),
    (r'\bOOD\b', 'BG', 'OOD', 'suffix'),
    (r'\bAD\b', 'BG', 'AD', 'suffix'),
    # UK / Ireland
    (r'\bLtd\.?\b', 'GB', 'Ltd', 'suffix'),
    (r'\bLLP\b', 'GB', 'LLP', 'suffix'),
    (r'\bPLC\b', 'GB', 'PLC', 'suffix'),
    # France
    (r'\bSARL\b', 'FR', 'SARL', 'suffix'),
    (r'\bSAS\b', 'FR', 'SAS', 'suffix'),
    # Italy
    (r'\bS\.?p\.?A\.?\b', 'IT', 'SpA', 'suffix'),
    (r'\bS\.?r\.?l\.?\b', 'IT', 'Srl', 'suffix'),
    # Austria
    (r'\bGes\.?m\.?b\.?H\.?\b', 'AT', 'GmbH', 'suffix'),
]


def detect_legal_metadata(company_name, cui=None):
    """Detect country code and legal form from company name suffix.

    Returns:
        dict with keys: country_code, legal_form, country_detected_from
              or None if no match found.
    """
    if not company_name:
        return None

    name_upper = company_name.strip().upper()

    for pattern, country, legal_form, source in _SUFFIX_MAP:
        if re.search(pattern, name_upper, re.IGNORECASE):
            return {
                'country_code': country,
                'legal_form': legal_form,
                'country_detected_from': source,
            }

    # Fallback: if CUI looks Romanian (digits only, 2-10 chars)
    if cui and re.match(r'^\d{2,10}$', str(cui).strip()):
        return {
            'country_code': 'RO',
            'legal_form': None,
            'country_detected_from': 'cui_format',
        }

    return None


def classify_client_type(cui):
    """Return 'business' if CUI is present and non-empty, else 'private'."""
    if cui and str(cui).strip():
        return 'business'
    return 'private'


def compute_renewal_score(client_id, repo):
    """Compute a renewal opportunity score (0-100) based on fleet signals.

    Scoring factors:
    - Fleet size (more vehicles = higher potential)
    - Vehicles nearing warranty expiry (within 6 months)
    - Vehicles with financing expiring within 12 months
    - Vehicles older than 4 years
    - Already-flagged renewal candidates

    Args:
        client_id: crm_clients.id
        repo: ClientFSRepository instance

    Returns:
        int: score 0-100
    """
    fleet = repo.get_fleet(client_id)
    if not fleet:
        return 0

    score = 0
    now = datetime.now().date()
    six_months = now + timedelta(days=180)
    twelve_months = now + timedelta(days=365)

    active_vehicles = [v for v in fleet if v.get('status') == 'active']
    total_active = len(active_vehicles)

    if total_active == 0:
        return 0

    # Fleet size factor (max 20 pts)
    if total_active >= 10:
        score += 20
    elif total_active >= 5:
        score += 15
    elif total_active >= 3:
        score += 10
    else:
        score += 5

    warranty_expiring = 0
    financing_expiring = 0
    old_vehicles = 0
    flagged_candidates = 0

    for v in active_vehicles:
        # Warranty expiry within 6 months (max 25 pts)
        warranty_exp = v.get('warranty_expiry')
        if warranty_exp:
            if isinstance(warranty_exp, str):
                try:
                    warranty_exp = datetime.strptime(warranty_exp, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    warranty_exp = None
            if warranty_exp and warranty_exp <= six_months:
                warranty_expiring += 1

        # Financing expiry within 12 months (max 25 pts)
        fin_exp = v.get('financing_expiry')
        if fin_exp:
            if isinstance(fin_exp, str):
                try:
                    fin_exp = datetime.strptime(fin_exp, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    fin_exp = None
            if fin_exp and fin_exp <= twelve_months:
                financing_expiring += 1

        # Vehicle age > 4 years (max 15 pts)
        year = v.get('vehicle_year')
        if year and (now.year - year) >= 4:
            old_vehicles += 1

        # Already flagged (max 15 pts)
        if v.get('renewal_candidate'):
            flagged_candidates += 1

    # Warranty expiry score
    if warranty_expiring > 0:
        ratio = warranty_expiring / total_active
        score += min(25, int(ratio * 25) + 10)

    # Financing expiry score
    if financing_expiring > 0:
        ratio = financing_expiring / total_active
        score += min(25, int(ratio * 25) + 10)

    # Age score
    if old_vehicles > 0:
        ratio = old_vehicles / total_active
        score += min(15, int(ratio * 15) + 5)

    # Flagged candidates score
    if flagged_candidates > 0:
        ratio = flagged_candidates / total_active
        score += min(15, int(ratio * 15) + 5)

    return min(100, score)


_ANAF_DEFAULT_ENDPOINT = 'https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva'
_ANAF_DEFAULT_TIMEOUT = 5


def _get_anaf_config():
    """Read ANAF connector config from the connectors table.

    Returns:
        tuple: (api_endpoint, timeout_seconds)
    """
    try:
        from core.connectors.repositories.connector_repository import ConnectorRepository
        connector = ConnectorRepository().get_by_type('anaf')
        if connector and connector.get('config'):
            cfg = connector['config']
            return (
                cfg.get('api_endpoint', _ANAF_DEFAULT_ENDPOINT),
                cfg.get('timeout_seconds', _ANAF_DEFAULT_TIMEOUT),
            )
    except Exception:
        pass
    return (_ANAF_DEFAULT_ENDPOINT, _ANAF_DEFAULT_TIMEOUT)


def fetch_anaf_data(cui):
    """Fetch company data from ANAF public API (OPENAPI).

    Reads the API endpoint from the 'anaf' connector in the connectors table.

    Args:
        cui: Romanian CUI (fiscal code), digits only.

    Returns:
        dict with ANAF response data, or None on error.
    """
    if not cui:
        return None

    # Strip RO prefix if present
    cui_clean = str(cui).strip().upper()
    if cui_clean.startswith('RO'):
        cui_clean = cui_clean[2:]
    cui_clean = cui_clean.strip()

    if not cui_clean.isdigit():
        return None

    today_str = datetime.now().strftime('%Y-%m-%d')
    api_endpoint, timeout = _get_anaf_config()

    try:
        resp = requests.post(
            api_endpoint,
            json=[{'cui': int(cui_clean), 'data': today_str}],
            timeout=timeout,
            headers={'Content-Type': 'application/json'},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get('found') and isinstance(data['found'], list) and len(data['found']) > 0:
            return data['found'][0]

        # CUI not found in ANAF
        logger.info('CUI %s not found in ANAF', cui_clean)
        return None
    except requests.exceptions.Timeout:
        logger.warning('ANAF API timeout for CUI %s', cui_clean)
        return None
    except requests.exceptions.RequestException as e:
        logger.warning('ANAF API error for CUI %s: %s', cui_clean, str(e))
        return None
    except (ValueError, KeyError) as e:
        logger.warning('ANAF API parse error for CUI %s: %s', cui_clean, str(e))
        return None


def get_or_refresh_anaf(client_id, cui, repo):
    """Get cached ANAF data or refresh if stale (> 24h).

    Args:
        client_id: crm_clients.id
        cui: CUI string
        repo: ClientFSRepository instance

    Returns:
        dict with ANAF data or None
    """
    profile = repo.get_or_create_profile(client_id)

    # Check if we have recent data
    if profile.get('anaf_data') and profile.get('anaf_fetched_at'):
        fetched_at = profile['anaf_fetched_at']
        if isinstance(fetched_at, str):
            try:
                fetched_at = datetime.fromisoformat(fetched_at)
            except (ValueError, TypeError):
                fetched_at = None

        if fetched_at and (datetime.now() - fetched_at) < timedelta(hours=24):
            return profile['anaf_data']

    # Fetch fresh data
    anaf_data = fetch_anaf_data(cui)
    if anaf_data:
        import json
        repo.update_profile(client_id, {
            'anaf_data': json.dumps(anaf_data) if isinstance(anaf_data, dict) else anaf_data,
            'anaf_fetched_at': datetime.now().isoformat(),
        })

    return anaf_data


def enrich_client_profile(client_id, company_name, cui, repo):
    """Orchestrate full client profile enrichment.

    Steps:
    1. Detect country/legal form from company name
    2. Classify client type from CUI
    3. Fetch/refresh ANAF data (if Romanian CUI)
    4. Compute renewal score
    5. Update profile

    Args:
        client_id: crm_clients.id
        company_name: company name string
        cui: CUI / fiscal code string
        repo: ClientFSRepository instance

    Returns:
        dict: updated profile
    """
    profile = repo.get_or_create_profile(client_id)

    update_data = {}

    # 1. Legal metadata detection
    legal = detect_legal_metadata(company_name, cui)
    if legal:
        update_data['country_code'] = legal['country_code']
        if legal.get('legal_form'):
            update_data['legal_form'] = legal['legal_form']
        update_data['country_detected_from'] = legal.get('country_detected_from')

    # 2. Client type classification
    client_type = classify_client_type(cui)
    update_data['client_type'] = client_type

    # 3. CUI storage
    if cui and str(cui).strip():
        update_data['cui'] = str(cui).strip()

    # 4. ANAF enrichment (only for Romanian CUIs)
    country = update_data.get('country_code', profile.get('country_code', 'RO'))
    if country == 'RO' and cui:
        anaf_data = get_or_refresh_anaf(client_id, cui, repo)
        if anaf_data:
            import json
            update_data['anaf_data'] = json.dumps(anaf_data) if isinstance(anaf_data, dict) else anaf_data
            update_data['anaf_fetched_at'] = datetime.now().isoformat()

    # 5. Renewal score
    score = compute_renewal_score(client_id, repo)
    update_data['renewal_score'] = score
    update_data['last_scored_at'] = datetime.now().isoformat()

    # 6. Fleet size
    fleet = repo.get_fleet(client_id)
    active_count = len([v for v in fleet if v.get('status') == 'active']) if fleet else 0
    update_data['fleet_size'] = active_count

    # Apply update
    if update_data:
        updated = repo.update_profile(client_id, update_data)
        return updated

    return profile
