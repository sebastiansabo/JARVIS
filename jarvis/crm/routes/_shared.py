"""Shared imports, blueprint reference, decorators, and helpers for CRM routes."""

__all__ = [
    # stdlib / flask
    'io', 'csv', 'os', 'tempfile', 'logging', 'threading', 'wraps',
    'jsonify', 'request', 'Response', 'send_file', 'g',
    'login_required', 'current_user',
    # app imports
    'crm_bp', 'ClientRepository', 'DealRepository', 'ImportRepository',
    'IMPORT_HANDLERS', 'PermissionRepository', 'logger',
    # singletons (private — exported explicitly)
    '_client_repo', '_deal_repo', '_import_repo', '_perm_repo',
    '_enrichment_col_added',
    # private helpers
    '_ai_company_lookup', '_ensure_enrichment_column', '_parse_name_nr_reg',
    '_auto_fix_client_on_load', '_parse_anaf_address',
    '_extract_profile_from_connector', '_apply_connector_to_profile',
    '_compute_business_value', '_csv_response',
    # public decorator
    'crm_required',
]

import io
import csv
import os
import tempfile
import logging
import threading
from functools import wraps
from flask import jsonify, request, Response, send_file, g
from flask_login import login_required, current_user

from .. import crm_bp
from ..repositories import ClientRepository, DealRepository, ImportRepository
from ..services.import_service import IMPORT_HANDLERS
from core.roles.repositories import PermissionRepository

logger = logging.getLogger('jarvis.crm.routes')

_client_repo = ClientRepository()
_deal_repo = DealRepository()
_import_repo = ImportRepository()
_perm_repo = PermissionRepository()

_enrichment_col_added = False


def _ai_company_lookup(company_name, cui=None):
    """Use AI to look up basic company data when ANAF returns nothing.

    Returns dict with company fields or None.
    """
    try:
        from ai_agent.services.llm_client import ask
        prompt = f"""Find basic company information for the Romanian company: "{company_name}"{f' (CUI: {cui})' if cui else ''}.

Return ONLY a JSON object with these fields (use null if unknown):
{{
  "denumire": "official company name",
  "adresa": "full address",
  "localitate": "city",
  "judet": "county",
  "cod_CAEN": "CAEN code",
  "forma_juridica": "legal form (SRL, SA, etc.)",
  "nrRegCom": "trade register number",
  "telefon": "phone number",
  "stare_inregistrare": "active/inactive/radiat"
}}

Return ONLY valid JSON, no explanation."""

        import json
        text = ask(prompt, model='claude-haiku-4-5-20251001', max_tokens=300).strip()
        # Extract JSON from possible markdown
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
            text = text.strip()
        result = json.loads(text)
        result['_source'] = 'ai_lookup'
        return result
    except Exception:
        logger.exception('AI company lookup failed for %s', company_name)
        return None


def _ensure_enrichment_column():
    """Add enrichment_data JSONB column to client_profiles if missing."""
    global _enrichment_col_added
    if _enrichment_col_added:
        return
    _enrichment_col_added = True
    from field_sales.repositories.client_fs_repository import ClientFSRepository
    _fs_repo = ClientFSRepository()
    try:
        _fs_repo.execute('''
            ALTER TABLE client_profiles
            ADD COLUMN IF NOT EXISTS enrichment_data JSONB DEFAULT '{}'
        ''', ())
    except Exception:
        logger.debug('enrichment_data column already exists or migration skipped')


def _parse_name_nr_reg(display_name):
    """Extract Nr. Reg. Com. (e.g. J40/1716/2000) from company display name.

    Returns (clean_name, nr_reg) tuple.
    """
    import re
    if not display_name:
        return display_name, ''
    # Pattern: J followed by 1-2 digits, then /digits/4-digit year
    m = re.search(r'\b(J\d{1,2}/\d+/\d{4})\b', display_name)
    if m:
        nr_reg = m.group(1)
        clean = display_name[:m.start()].strip().rstrip(',').rstrip('-').strip()
        return clean, nr_reg
    return display_name, ''


def _auto_fix_client_on_load(client_id, client):
    """Auto-fix client data on detail load: parse nr_reg from name, detect company type.

    Returns updated client dict (may write to DB).
    """
    from field_sales.services.business_data_service import detect_company_type
    updates = {}
    display_name = client.get('display_name') or ''

    # 1. Parse Nr. Reg. Com. from display_name if present
    clean_name, parsed_nr_reg = _parse_name_nr_reg(display_name)
    if parsed_nr_reg and clean_name != display_name:
        updates['display_name'] = clean_name
        if not client.get('nr_reg'):
            updates['nr_reg'] = parsed_nr_reg

    # 2. Auto-detect client_type from name
    effective_name = updates.get('display_name', display_name)
    detected = detect_company_type(effective_name)
    if detected == 'company' and client.get('client_type') != 'company':
        updates['client_type'] = 'company'

    # Apply updates if any
    if updates:
        try:
            result = _client_repo.update(client_id, updates)
            if result:
                client = result
        except Exception:
            logger.exception('Auto-fix failed for client %s', client_id)

    return client


def _parse_anaf_address(adresa):
    """Parse ANAF compound address like 'JUD. CLUJ, MUN. CLUJ-NAPOCA, STR. FABRICII, NR.124'.

    Returns (street, city, region) tuple.
    """
    import re
    street, city, region = '', '', ''
    if not adresa:
        return street, city, region

    parts = [p.strip() for p in adresa.split(',')]
    for part in parts:
        p = part.upper()
        if p.startswith('JUD.') or p.startswith('JUD '):
            region = part.replace('JUD.', '').replace('JUD ', '').strip().title()
        elif any(p.startswith(x) for x in ('MUN.', 'MUN ', 'ORA', 'COM.', 'COM ', 'SAT ', 'LOC.')):
            city = re.sub(r'^(MUN\.|MUN |ORAS|ORA[SȘŞ]UL?|COM\.|COM |SAT |LOC\.)\s*', '', part, flags=re.IGNORECASE).strip().title()
        elif any(p.startswith(x) for x in ('STR.', 'STR ', 'BD.', 'B-DUL', 'CAL.', 'ȘOS.', 'SOS.', 'ŞOS.', 'AL.', 'SPL.', 'P-TA', 'NR.', 'NR ')):
            street = (street + ', ' + part.strip()) if street else part.strip()
        elif not region and not city:
            # Fallback: might be county if first
            region = part.strip().title()

    # Combine street parts
    if street:
        street = street.strip(', ')

    return street, city, region


def _extract_profile_from_connector(connector_type, data):
    """Extract structured profile + client fields from raw connector API response.

    Returns (profile_updates, client_updates) dicts.
    """
    if not data or not isinstance(data, dict):
        return {}, {}

    profile = {}
    client = {}

    # ANAF wraps data in date_generale + adresa_sediu_social sub-objects
    if 'date_generale' in data and isinstance(data['date_generale'], dict):
        flat = {**data}
        for k, v in data['date_generale'].items():
            flat.setdefault(k, v)
        data = flat
    if 'adresa_sediu_social' in data and isinstance(data['adresa_sediu_social'], dict):
        for k, v in data['adresa_sediu_social'].items():
            data.setdefault(k, v)

    # --- CUI / CIF ---
    for key in ('cui', 'cif', 'cod_fiscal', 'fiscal_code'):
        val = data.get(key)
        if val and str(val).strip() and str(val).strip() not in ('null', 'None', '0'):
            profile['cui'] = str(val).strip()
            break

    # --- Industry / CAEN ---
    for key in ('cod_caen', 'cod_CAEN', 'caen', 'caen_code'):
        val = data.get(key)
        if val and str(val).strip():
            profile['industry'] = str(val).strip()
            break

    # --- Legal form ---
    for key in ('forma_juridica', 'forma_organizare', 'forma_legala', 'legal_form'):
        val = data.get(key)
        if val and str(val).strip():
            lf = str(val).strip()
            profile['legal_form'] = lf
            # Detect client_type from legal form
            lf_upper = lf.upper()
            if any(x in lf_upper for x in ('SRL', 'SA', 'SCS', 'SNC', 'RA', 'SOCIETA',
                                            'ASOCIAT', 'FUNDATI', 'COOPERATIV', 'JURIDIC')):
                profile['client_type'] = 'company'
            break

    # ANAF only has companies — force client_type
    if connector_type == 'anaf':
        profile['client_type'] = 'company'

    # --- Phone ---
    for key in ('telefon', 'phone', 'tel'):
        val = data.get(key)
        if val and str(val).strip() and str(val).strip() not in ('null', 'None', ''):
            client['phone'] = str(val).strip()
            break

    # --- Email ---
    for key in ('email', 'email_address'):
        val = data.get(key)
        if val and str(val).strip() and str(val).strip() not in ('null', 'None', ''):
            client['email'] = str(val).strip()
            break

    # --- Address: parse ANAF compound address into street/city/region ---
    anaf_adresa = None
    for key in ('adresa', 'adresa_domiciliu_fiscal', 'address', 'sediu', 'sediu_social'):
        val = data.get(key)
        if val and str(val).strip() and str(val).strip() not in ('null', 'None'):
            anaf_adresa = str(val).strip()
            break

    if anaf_adresa:
        parsed_street, parsed_city, parsed_region = _parse_anaf_address(anaf_adresa)
        if parsed_street:
            client['street'] = parsed_street
        elif anaf_adresa:
            client['street'] = anaf_adresa  # Fallback: full address as street
        if parsed_city:
            client['city'] = parsed_city
        if parsed_region:
            client['region'] = parsed_region

    # Separate city/region fields (override parsed if explicit fields exist)
    for key in ('localitate', 'oras', 'city', 'loc', 'sdenumire_Localitate'):
        val = data.get(key)
        if val and str(val).strip() and str(val).strip() not in ('null', 'None'):
            client['city'] = str(val).strip().title()
            break

    for key in ('judet', 'county', 'region', 'jud', 'sdenumire_Judet'):
        val = data.get(key)
        if val and str(val).strip() and str(val).strip() not in ('null', 'None'):
            client['region'] = str(val).strip().title()
            break

    # --- Nr Reg Com ---
    for key in ('numar_reg_com', 'nrRegCom', 'nr_reg_com', 'numar_registru_comertului', 'nr_registru'):
        val = data.get(key)
        if val and str(val).strip() and str(val).strip() not in ('null', 'None'):
            client['nr_reg'] = str(val).strip()
            break

    # --- Company name / denumire ---
    for key in ('denumire', 'name', 'company_name', 'den'):
        val = data.get(key)
        if val and str(val).strip() and str(val).strip() not in ('null', 'None'):
            client['company_name'] = str(val).strip()
            break

    # --- Country ---
    profile['country_code'] = 'RO'

    # --- ANAF-specific extended fields (stored in profile as JSON-friendly dict) ---
    if connector_type == 'anaf':
        extra = {}
        # Registration date
        for key in ('data_inregistrare', 'registration_date'):
            val = data.get(key)
            if val and str(val).strip():
                extra['data_inregistrare'] = str(val).strip()
                break
        # Ownership form
        for key in ('forma_de_proprietate',):
            val = data.get(key)
            if val and str(val).strip():
                extra['forma_de_proprietate'] = str(val).strip()
                break
        # Organization form
        for key in ('forma_organizare',):
            val = data.get(key)
            if val and str(val).strip():
                extra['forma_organizare'] = str(val).strip()
                break
        # Tax office
        for key in ('organFiscalCompetent',):
            val = data.get(key)
            if val and str(val).strip():
                extra['organ_fiscal'] = str(val).strip()
                break
        # Fax
        for key in ('fax',):
            val = data.get(key)
            if val and str(val).strip():
                extra['fax'] = str(val).strip()
                break
        # Postal code
        for key in ('codPostal', 'scod_Postal', 'dcod_Postal'):
            val = data.get(key)
            if val and str(val).strip():
                extra['cod_postal'] = str(val).strip()
                break
        # IBAN
        for key in ('iban',):
            val = data.get(key)
            if val and str(val).strip():
                extra['iban'] = str(val).strip()
                break
        # e-Factura
        extra['e_factura'] = bool(data.get('statusRO_e_Factura', False))
        if data.get('data_inreg_Reg_RO_e_Factura'):
            extra['e_factura_date'] = str(data['data_inreg_Reg_RO_e_Factura'])
        # Stare inregistrare
        for key in ('stare_inregistrare',):
            val = data.get(key)
            if val and str(val).strip():
                extra['stare_inregistrare'] = str(val).strip()
                break
        # VAT details
        tva_section = data.get('inregistrare_scop_Tva') or {}
        if isinstance(tva_section, dict):
            extra['scp_tva'] = bool(tva_section.get('scpTVA', False))
            periods = tva_section.get('perioade_TVA', [])
            if periods and isinstance(periods, list):
                latest = periods[0]
                extra['tva_start'] = latest.get('data_inceput_ScpTVA', '')
                extra['tva_end'] = latest.get('data_sfarsit_ScpTVA', '')
        # Inactive status
        inactive_section = data.get('stare_inactiv') or {}
        if isinstance(inactive_section, dict):
            extra['is_inactive'] = bool(inactive_section.get('statusInactivi', False))
            if inactive_section.get('dataRadiere'):
                extra['data_radiere'] = str(inactive_section['dataRadiere'])
        # TVA la incasare
        rtvai = data.get('inregistrare_RTVAI') or {}
        if isinstance(rtvai, dict):
            extra['tva_incasare'] = bool(rtvai.get('statusTvaIncasare', False))
        # Split TVA
        split = data.get('inregistrare_SplitTVA') or {}
        if isinstance(split, dict):
            extra['split_tva'] = bool(split.get('statusSplitTVA', False))
        # County auto code
        addr = data.get('adresa_sediu_social') or {}
        if isinstance(addr, dict):
            if addr.get('scod_JudetAuto'):
                extra['cod_judet_auto'] = str(addr['scod_JudetAuto'])
        # Store CAEN activity description (if we add lookup later)
        caen = data.get('cod_CAEN') or data.get('cod_caen') or ''
        if caen:
            extra['cod_caen'] = str(caen).strip()

        if extra:
            profile['_anaf_extra'] = extra

    return profile, client


def _apply_connector_to_profile(client_id, connector_type, data):
    """Extract fields from connector data and save to profile + client.

    ANAF is gold standard — overwrites all fields.
    Other connectors only fill empty fields.
    """
    from field_sales.repositories.client_fs_repository import ClientFSRepository
    _fs_repo = ClientFSRepository()
    profile_updates, client_updates = _extract_profile_from_connector(connector_type, data)
    is_gold = connector_type == 'anaf'

    # Handle _anaf_extra: store as JSON in enrichment_data.anaf_extra
    anaf_extra = profile_updates.pop('_anaf_extra', None)
    if anaf_extra:
        try:
            import json as _json
            prof = _fs_repo.get_or_create_profile(client_id)
            existing = prof.get('enrichment_data') or {}
            if isinstance(existing, str):
                try:
                    existing = _json.loads(existing)
                except (ValueError, TypeError):
                    existing = {}
            existing['anaf_extra'] = anaf_extra
            _fs_repo.update_profile(client_id, {'enrichment_data': _json.dumps(existing)})
        except Exception:
            logger.exception('Failed to store anaf_extra for client %s', client_id)

    if profile_updates:
        try:
            _fs_repo.update_profile(client_id, profile_updates)
        except Exception:
            logger.exception('Failed to update profile from %s for client %s', connector_type, client_id)

    if client_updates:
        try:
            client = _client_repo.get_by_id(client_id)
            if client:
                if is_gold:
                    # ANAF = gold standard: overwrite all fields
                    _client_repo.update(client_id, client_updates)
                else:
                    # Other connectors: only fill empty fields
                    filtered = {k: v for k, v in client_updates.items()
                                if not client.get(k) or client.get(k) == '—'}
                    if filtered:
                        _client_repo.update(client_id, filtered)
        except Exception:
            logger.exception('Failed to update client from %s for client %s', connector_type, client_id)


def _compute_business_value(client, profile, deals, fleet, visits, interactions):
    """Compute a composite Business Value Score (0-100) with breakdown.

    Weights:
      - Purchase Value  (30%): total revenue, avg deal value, recency
      - Retention        (25%): years as client, purchase frequency, visit engagement
      - Fleet / Volume   (20%): fleet size, number of vehicles
      - Profile Quality  (15%): data completeness, enrichment
      - Renewal Potential (10%): renewal score, renewal candidates
    """
    from datetime import datetime, timedelta

    breakdown = {}
    now = datetime.now()

    # ── 1. Purchase Value (0-30) ──
    # Uses actual sale_price_net (your total sales) and gross_profit (your margin)
    pv_score = 0
    total_sales = 0.0
    total_margin = 0.0
    deal_count = len(deals) if deals else 0
    avg_deal_value = 0.0
    avg_margin_per_deal = 0.0
    margin_pct = 0.0
    last_deal_date = None
    first_deal_date = None
    deal_dates = []

    if deals:
        for d in deals:
            # Total sales (sale_price_net = your invoice to client)
            price = d.get('sale_price_net') or 0
            try:
                total_sales += float(price)
            except (ValueError, TypeError):
                pass
            # Total margin (gross_profit = your profit)
            profit = d.get('gross_profit') or 0
            try:
                total_margin += float(profit)
            except (ValueError, TypeError):
                pass
            # Track dates
            cd = d.get('contract_date')
            if cd:
                try:
                    dt = datetime.fromisoformat(str(cd)[:10]) if isinstance(cd, str) else cd
                    deal_dates.append(dt)
                    if not last_deal_date or dt > last_deal_date:
                        last_deal_date = dt
                    if not first_deal_date or dt < first_deal_date:
                        first_deal_date = dt
                except Exception:
                    pass

        avg_deal_value = total_sales / deal_count if deal_count > 0 else 0
        avg_margin_per_deal = total_margin / deal_count if deal_count > 0 else 0
        margin_pct = (total_margin / total_sales * 100) if total_sales > 0 else 0

        # Revenue tiers (automotive: RON net)
        if total_sales >= 500_000:
            pv_score += 12
        elif total_sales >= 200_000:
            pv_score += 9
        elif total_sales >= 100_000:
            pv_score += 7
        elif total_sales >= 50_000:
            pv_score += 4
        elif total_sales > 0:
            pv_score += 2

        # Margin tiers
        if total_margin >= 50_000:
            pv_score += 6
        elif total_margin >= 20_000:
            pv_score += 4
        elif total_margin >= 5_000:
            pv_score += 2
        elif total_margin > 0:
            pv_score += 1

        # Deal volume
        if deal_count >= 10:
            pv_score += 6
        elif deal_count >= 5:
            pv_score += 5
        elif deal_count >= 3:
            pv_score += 3
        elif deal_count >= 1:
            pv_score += 1

        # Recency bonus
        if last_deal_date:
            try:
                days_since = (now.date() - (last_deal_date.date() if hasattr(last_deal_date, 'date') else last_deal_date)).days
            except Exception:
                days_since = 999
            if days_since <= 365:
                pv_score += 6
            elif days_since <= 730:
                pv_score += 3
            elif days_since <= 1095:
                pv_score += 1

    breakdown['purchase_value'] = {'score': min(pv_score, 30), 'max': 30,
                                    'total_sales': round(total_sales, 2),
                                    'total_margin': round(total_margin, 2),
                                    'margin_pct': round(margin_pct, 1),
                                    'deal_count': deal_count,
                                    'avg_deal_value': round(avg_deal_value, 2),
                                    'avg_margin_per_deal': round(avg_margin_per_deal, 2),
                                    'last_deal_date': str(last_deal_date)[:10] if last_deal_date else None}

    # ── 2. Retention (0-25) ──
    ret_score = 0
    years_as_client = 0
    if first_deal_date:
        try:
            years_as_client = (now.date() - (first_deal_date.date() if hasattr(first_deal_date, 'date') else first_deal_date)).days / 365.25
        except Exception:
            pass
        if years_as_client >= 5:
            ret_score += 10
        elif years_as_client >= 3:
            ret_score += 7
        elif years_as_client >= 1:
            ret_score += 4
        elif years_as_client > 0:
            ret_score += 2

    # Purchase frequency = avg deals per year (return rate)
    freq = deal_count / max(years_as_client, 1)
    if freq >= 3:
        ret_score += 8
    elif freq >= 1.5:
        ret_score += 6
    elif freq >= 0.5:
        ret_score += 3
    elif deal_count > 0:
        ret_score += 1

    # Visit engagement
    visit_count = len(visits) if visits else 0
    interaction_count = len(interactions) if interactions else 0
    if visit_count >= 5 or interaction_count >= 5:
        ret_score += 7
    elif visit_count >= 2 or interaction_count >= 2:
        ret_score += 4
    elif visit_count >= 1 or interaction_count >= 1:
        ret_score += 2

    # Average return interval (months between deals)
    avg_return_months = 0
    if len(deal_dates) >= 2:
        sorted_dates = sorted(deal_dates)
        intervals = []
        for i in range(1, len(sorted_dates)):
            try:
                d1 = sorted_dates[i-1].date() if hasattr(sorted_dates[i-1], 'date') else sorted_dates[i-1]
                d2 = sorted_dates[i].date() if hasattr(sorted_dates[i], 'date') else sorted_dates[i]
                intervals.append((d2 - d1).days / 30.44)
            except Exception:
                pass
        if intervals:
            avg_return_months = sum(intervals) / len(intervals)

    breakdown['retention'] = {'score': min(ret_score, 25), 'max': 25,
                               'years_as_client': round(years_as_client, 1),
                               'deals_per_year': round(freq, 2),
                               'avg_return_months': round(avg_return_months, 1),
                               'visit_count': visit_count,
                               'first_deal_date': str(first_deal_date)[:10] if first_deal_date else None}

    # ── 3. Fleet / Volume (0-20) ──
    fleet_score = 0
    fleet_size = len(fleet) if fleet else 0
    profile_fleet = (profile or {}).get('fleet_size') or 0
    effective_fleet = max(fleet_size, int(profile_fleet or 0), deal_count)

    if effective_fleet >= 20:
        fleet_score = 20
    elif effective_fleet >= 10:
        fleet_score = 16
    elif effective_fleet >= 5:
        fleet_score = 12
    elif effective_fleet >= 3:
        fleet_score = 8
    elif effective_fleet >= 1:
        fleet_score = 4

    breakdown['fleet_volume'] = {'score': min(fleet_score, 20), 'max': 20,
                                  'fleet_vehicles': fleet_size,
                                  'effective_fleet': effective_fleet}

    # ── 4. Profile Quality (0-15) ──
    pq_score = 0
    checks = 0
    filled = 0
    for k in ['display_name', 'company_name', 'phone', 'email', 'city', 'region', 'street', 'nr_reg']:
        checks += 1
        if client.get(k) and client.get(k) != '—':
            filled += 1
    for k in ['cui', 'industry', 'legal_form', 'priority', 'client_type']:
        checks += 1
        if (profile or {}).get(k):
            filled += 1
    checks += 1
    if (profile or {}).get('anaf_data'):
        filled += 1
    checks += 1
    ed = (profile or {}).get('enrichment_data')
    if ed and isinstance(ed, (dict, str)) and (isinstance(ed, dict) and len(ed) > 0 or isinstance(ed, str) and len(ed) > 5):
        filled += 1

    completeness = filled / checks if checks > 0 else 0
    pq_score = round(completeness * 15)

    breakdown['profile_quality'] = {'score': min(pq_score, 15), 'max': 15,
                                     'completeness_pct': round(completeness * 100)}

    # ── 5. Renewal Potential (0-10) ──
    rn_score = 0
    renewal_score = (profile or {}).get('renewal_score') or 0
    try:
        renewal_score = int(renewal_score)
    except (ValueError, TypeError):
        renewal_score = 0
    rn_score = round(renewal_score / 100 * 10)

    breakdown['renewal_potential'] = {'score': min(rn_score, 10), 'max': 10,
                                       'renewal_score': renewal_score}

    # ── Composite ──
    total = sum(v['score'] for v in breakdown.values())
    grade = 'A' if total >= 80 else 'B' if total >= 60 else 'C' if total >= 40 else 'D' if total >= 20 else 'E'

    # Client tier (loyalty program categorization)
    if total >= 80:
        tier = 'Platinum'
    elif total >= 65:
        tier = 'Gold'
    elif total >= 45:
        tier = 'Silver'
    elif total >= 25:
        tier = 'Bronze'
    else:
        tier = 'Prospect'

    # Client Lifetime Value (CLV) estimate: avg annual revenue * expected remaining years
    annual_revenue = total_sales / max(years_as_client, 1) if total_sales > 0 else 0
    expected_years = 5 if tier in ('Platinum', 'Gold') else 3 if tier == 'Silver' else 2
    clv = annual_revenue * expected_years

    # Years per purchase (inverse of deals_per_year — more intuitive)
    years_per_purchase = max(years_as_client, 1) / deal_count if deal_count > 0 else 0

    # EUR equivalents (approximate RON→EUR rate)
    eur_rate = 4.97  # NBR reference rate
    total_sales_eur = total_sales / eur_rate if total_sales else 0
    total_margin_eur = total_margin / eur_rate if total_margin else 0
    avg_deal_value_eur = avg_deal_value / eur_rate if avg_deal_value else 0
    clv_eur = clv / eur_rate if clv else 0
    annual_revenue_eur = annual_revenue / eur_rate if annual_revenue else 0

    return {
        'score': total,
        'grade': grade,
        'tier': tier,
        'clv': round(clv, 2),
        'clv_eur': round(clv_eur, 2),
        'annual_revenue': round(annual_revenue, 2),
        'annual_revenue_eur': round(annual_revenue_eur, 2),
        'total_sales_eur': round(total_sales_eur, 2),
        'total_margin_eur': round(total_margin_eur, 2),
        'avg_deal_value_eur': round(avg_deal_value_eur, 2),
        'years_per_purchase': round(years_per_purchase, 1),
        'breakdown': breakdown,
    }


def crm_required(f):
    """Require sales.module.access V2 permission. Sets g.permission_scope."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        role_id = getattr(current_user, 'role_id', None)
        if role_id:
            perm = _perm_repo.check_permission_v2(role_id, 'sales', 'module', 'access')
            if not perm.get('has_permission'):
                return jsonify({'success': False, 'error': 'CRM access denied'}), 403
            g.permission_scope = perm.get('scope', 'all')
        else:
            if not getattr(current_user, 'can_access_crm', False):
                return jsonify({'success': False, 'error': 'CRM access denied'}), 403
            g.permission_scope = 'all'

        # Per-client tenant scope: for any /clients/<client_id> route, a non-'all'
        # scope may only touch clients in the user's own company (department;
        # 'own' collapses to department until per-KAM ownership/assigned_kam_id
        # exists). Covers the 360 detail AND every per-client mutation uniformly.
        cid = kwargs.get('client_id')
        if cid is not None and getattr(g, 'permission_scope', 'all') != 'all':
            uc = getattr(current_user, 'company_id', None)
            from field_sales.repositories.client_fs_repository import ClientFSRepository
            if uc is None or ClientFSRepository().get_client_company_id(cid) != uc:
                return jsonify({'success': False, 'error': 'Access denied for this client'}), 403
        return f(*args, **kwargs)
    return decorated


def _csv_response(rows, filename, columns):
    """Stream rows as CSV download."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(c, '') for c in columns])
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
