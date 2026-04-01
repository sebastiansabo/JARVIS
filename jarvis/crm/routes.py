"""CRM API routes — import, search, stats, detail, CRUD, export endpoints."""

import io
import csv
import os
import tempfile
import logging
import threading
from functools import wraps
from flask import jsonify, request, Response, send_file, g
from flask_login import login_required, current_user

from . import crm_bp
from .repositories import ClientRepository, DealRepository, ImportRepository
from .services.import_service import IMPORT_HANDLERS
from core.roles.repositories import PermissionRepository
from field_sales.repositories.client_fs_repository import ClientFSRepository
from field_sales.services.segmentation_service import fetch_anaf_data, get_or_refresh_anaf
from field_sales.services.business_data_service import (
    get_connected_business_connectors, enrich_from_connector, enrich_from_all_connected,
    detect_company_type, search_company_by_name, ai_research_company,
)

logger = logging.getLogger('jarvis.crm.routes')

_client_repo = ClientRepository()
_deal_repo = DealRepository()
_import_repo = ImportRepository()
_perm_repo = PermissionRepository()
_fs_repo = ClientFSRepository()

_enrichment_col_added = False


def _ai_company_lookup(company_name, cui=None):
    """Use AI to look up basic company data when ANAF returns nothing.

    Returns dict with company fields or None.
    """
    try:
        import anthropic
        client = anthropic.Anthropic()
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

        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=300,
            messages=[{'role': 'user', 'content': prompt}],
        )
        import json
        text = resp.content[0].text.strip()
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
    try:
        _fs_repo.execute('''
            ALTER TABLE client_profiles
            ADD COLUMN IF NOT EXISTS enrichment_data JSONB DEFAULT '{}'
        ''', ())
    except Exception:
        logger.debug('enrichment_data column already exists or migration skipped')


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

    return profile, client


def _apply_connector_to_profile(client_id, connector_type, data):
    """Extract fields from connector data and save to profile + client.

    ANAF is gold standard — overwrites all fields.
    Other connectors only fill empty fields.
    """
    profile_updates, client_updates = _extract_profile_from_connector(connector_type, data)
    is_gold = connector_type == 'anaf'

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

    return {
        'score': total,
        'grade': grade,
        'tier': tier,
        'clv': round(clv, 2),
        'annual_revenue': round(annual_revenue, 2),
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
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════════
# Import
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/import', methods=['POST'])
@login_required
@crm_required
def api_import():
    """Upload and import an Excel/CSV file.
    Form data: file (multipart), source_type (deals|clients|nw|gw|crm_clients)
    """
    source_type = request.form.get('source_type')
    if source_type not in IMPORT_HANDLERS:
        return jsonify({'success': False,
                        'error': f'Invalid source_type. Use: {", ".join(IMPORT_HANDLERS.keys())}'}), 400

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.xlsx', '.xls', '.csv'):
        return jsonify({'success': False, 'error': 'Only .xlsx, .xls, .csv files supported'}), 400

    # Save to temp file (cleaned up by background thread)
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        file.save(tmp)
        tmp_path = tmp.name

    original_filename = file.filename
    user_id = current_user.id

    def _run():
        try:
            IMPORT_HANDLERS[source_type](tmp_path, user_id, original_filename=original_filename)
        except Exception:
            logger.exception('Background CRM import failed')
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'success': True, 'message': 'Import started'})


@crm_bp.route('/api/crm/import/template', methods=['GET'])
@login_required
@crm_required
def api_import_template():
    """Download the Samsaru import template (.xlsx)."""
    template_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'import-templates', 'Samsaru_Import_Template.xlsx')
    template_path = os.path.abspath(template_path)
    if not os.path.exists(template_path):
        return jsonify({'success': False, 'error': 'Template file not found'}), 404
    return send_file(template_path, as_attachment=True, download_name='Samsaru_Import_Template.xlsx')


@crm_bp.route('/api/crm/import/batches', methods=['GET'])
@login_required
@crm_required
def api_import_batches():
    source_type = request.args.get('source_type')
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    batches = _import_repo.list_batches(source_type, limit, offset)
    return jsonify({'batches': batches})


# ════════════════════════════════════════════════════════════════
# Stats
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/stats', methods=['GET'])
@login_required
@crm_required
def api_stats():
    client_stats = _client_repo.get_stats()
    deal_stats = _deal_repo.get_stats()
    last_imports = {}
    for st in ('nw', 'gw', 'crm_clients', 'clienti'):
        last = _import_repo.get_last_import(st)
        last_imports[st] = last
    return jsonify({
        'clients': client_stats,
        'deals': deal_stats,
        'last_imports': last_imports,
    })


# ════════════════════════════════════════════════════════════════
# Clients
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/clients', methods=['GET'])
@login_required
@crm_required
def api_clients():
    rows, total = _client_repo.search(
        name=request.args.get('name'),
        phone=request.args.get('phone'),
        email=request.args.get('email'),
        client_type=request.args.get('client_type'),
        responsible=request.args.get('responsible'),
        city=request.args.get('city'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        sort_by=request.args.get('sort_by'),
        sort_order=request.args.get('sort_order'),
        show_blacklisted=request.args.get('show_blacklisted'),
        limit=request.args.get('limit', 50, type=int),
        offset=request.args.get('offset', 0, type=int),
    )
    return jsonify({'clients': rows, 'total': total})


@crm_bp.route('/api/crm/clients/export', methods=['GET'])
@login_required
@crm_required
def api_clients_export():
    if not getattr(current_user, 'can_export_crm', False):
        return jsonify({'success': False, 'error': 'Export permission denied'}), 403
    rows, _ = _client_repo.search(
        name=request.args.get('name'), phone=request.args.get('phone'),
        email=request.args.get('email'), client_type=request.args.get('client_type'),
        responsible=request.args.get('responsible'), city=request.args.get('city'),
        date_from=request.args.get('date_from'), date_to=request.args.get('date_to'),
        show_blacklisted=request.args.get('show_blacklisted'),
        limit=50000, offset=0,
    )
    return _csv_response(rows, 'clients.csv', [
        'id', 'display_name', 'client_type', 'phone', 'email', 'street', 'city',
        'region', 'company_name', 'responsible', 'created_at',
    ])


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['GET'])
@login_required
@crm_required
def api_client_detail(client_id):
    """360 Client — full ecosystem data for a single client."""
    _ensure_enrichment_column()
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    deals, _ = _deal_repo.search(client_id=client_id, limit=100)
    phones = []
    try:
        phones = _client_repo.get_phones(client_id)
    except Exception:
        pass  # client_phones table may not exist yet

    # Full 360 ecosystem data
    view_360 = {}
    try:
        view_360 = _fs_repo.get_360(client_id)
    except Exception:
        logger.exception('Error fetching 360 view for client %s', client_id)

    profile = view_360.get('profile')
    fleet = view_360.get('fleet') or []
    visits = view_360.get('visit_history') or []
    interactions = view_360.get('interactions') or []
    renewal_candidates = view_360.get('renewal_candidates') or []
    fiscal = view_360.get('fiscal')

    # Auto-compute fleet_size from deals if no fleet vehicles
    if profile and not fleet and deals:
        current_fleet_size = profile.get('fleet_size') or 0
        if current_fleet_size == 0:
            try:
                _fs_repo.update_profile(client_id, {'fleet_size': len(deals)})
                profile = _fs_repo.get_or_create_profile(client_id)
            except Exception:
                pass

    # Parse enrichment_data from profile
    enrichment_data = {}
    if profile:
        ed = profile.get('enrichment_data')
        if isinstance(ed, str):
            try:
                import json as _json
                enrichment_data = _json.loads(ed)
            except (ValueError, TypeError):
                pass
        elif isinstance(ed, dict):
            enrichment_data = ed

    # Get available connectors for this client
    connectors = get_connected_business_connectors()

    # ── Compute Business Value Score ──
    bv = _compute_business_value(client, profile, deals, fleet, visits, interactions)

    return jsonify({
        'client': client,
        'deals': deals,
        'phones': phones,
        'profile': profile,
        'fleet': fleet,
        'visits': visits,
        'interactions': interactions,
        'renewal_candidates': renewal_candidates,
        'fiscal': fiscal,
        'enrichment_data': enrichment_data,
        'connectors': connectors,
        'business_value': bv,
    })


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['PUT'])
@login_required
@crm_required
def api_client_update(client_id):
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    result = _client_repo.update(client_id, data)
    if not result:
        return jsonify({'success': False, 'error': 'Not found or no editable fields'}), 404
    return jsonify({'success': True, 'client': result})


@crm_bp.route('/api/crm/clients/<int:client_id>/enrich', methods=['POST'])
@login_required
@crm_required
def api_client_enrich(client_id):
    """Enrich client with ANAF fiscal data by CUI."""
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    cui = data.get('cui', '').strip()
    if not cui:
        return jsonify({'success': False, 'error': 'CUI is required'}), 400

    # Ensure profile exists and set CUI
    try:
        _fs_repo.get_or_create_profile(client_id)
        _fs_repo.update_profile(client_id, {'cui': cui})
    except Exception:
        logger.exception('Error setting CUI for client %s', client_id)
        return jsonify({'success': False, 'error': 'Failed to update profile'}), 500

    # Enrichment chain: connectors by name → ANAF by CUI → AI fallback
    try:
        import json
        from datetime import datetime as _dt

        anaf_data = None
        source = 'anaf'
        cui_correction = None
        company_name = client.get('display_name') or client.get('company_name') or ''

        # Step 1: Search connectors by company name to find/verify CUI
        if company_name:
            matches = search_company_by_name(company_name)
            if matches:
                best = matches[0]
                found_cui = str(best.get('cui', '')).strip()
                if found_cui and found_cui != cui:
                    cui_correction = {
                        'old_cui': cui,
                        'new_cui': found_cui,
                        'found_name': best.get('name', ''),
                        'source': best.get('source', ''),
                    }
                    logger.info('CUI mismatch for %s: saved=%s, found=%s from %s',
                                company_name, cui, found_cui, best.get('source'))
                    # Use the correct CUI
                    cui = found_cui
                    _fs_repo.update_profile(client_id, {'cui': cui})

        # Step 2: Fetch ANAF with (potentially corrected) CUI
        anaf_data = get_or_refresh_anaf(client_id, cui, _fs_repo)

        # Step 3: AI fallback if still nothing
        if not anaf_data:
            logger.info('ANAF empty for %s (CUI %s), trying AI fallback', company_name, cui)
            anaf_data = _ai_company_lookup(company_name, cui)
            source = 'ai'

        # Auto-fill client/profile fields from response
        if anaf_data and isinstance(anaf_data, dict):
            _apply_connector_to_profile(client_id, 'anaf', anaf_data)
            _fs_repo.update_profile(client_id, {
                'anaf_data': json.dumps(anaf_data) if isinstance(anaf_data, dict) else anaf_data,
                'anaf_fetched_at': _dt.now().isoformat(),
            })

        profile = _fs_repo.get_or_create_profile(client_id)
        resp = {
            'success': True,
            'profile': profile,
            'fiscal': anaf_data,
            'source': source,
        }
        if cui_correction:
            resp['cui_correction'] = cui_correction
        return jsonify(resp)
    except Exception:
        logger.exception('ANAF enrichment failed for client %s', client_id)
        return jsonify({'success': False, 'error': 'Enrichment failed'}), 500


@crm_bp.route('/api/crm/clients/<int:client_id>/enrich/<connector_type>', methods=['POST'])
@login_required
@crm_required
def api_client_enrich_connector(client_id, connector_type):
    """Enrich client from a specific business data connector."""
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    cui = data.get('cui', '').strip()
    if not cui:
        return jsonify({'success': False, 'error': 'CUI is required'}), 400

    try:
        result = enrich_from_connector(cui, connector_type)
        if result is None:
            return jsonify({'success': False, 'error': f'Connector {connector_type} not connected or fetch failed'}), 400

        # Store enrichment data on profile
        import json as _json
        profile = _fs_repo.get_or_create_profile(client_id)
        existing = profile.get('enrichment_data') or {}
        if isinstance(existing, str):
            try:
                existing = _json.loads(existing)
            except (ValueError, TypeError):
                existing = {}
        existing[connector_type] = {
            'data': result,
            'fetched_at': __import__('datetime').datetime.now().isoformat(),
        }
        _fs_repo.update_profile(client_id, {'enrichment_data': _json.dumps(existing)})

        # Auto-extract structured fields from connector data
        _apply_connector_to_profile(client_id, connector_type, result)

        updated_profile = _fs_repo.get_or_create_profile(client_id)
        return jsonify({
            'success': True,
            'connector_type': connector_type,
            'data': result,
            'profile': updated_profile,
        })
    except Exception:
        logger.exception('Enrichment from %s failed for client %s', connector_type, client_id)
        return jsonify({'success': False, 'error': f'{connector_type} enrichment failed'}), 500


@crm_bp.route('/api/crm/clients/<int:client_id>/connectors', methods=['GET'])
@login_required
@crm_required
def api_client_connectors(client_id):
    """Get available business data connectors for enrichment."""
    connectors = get_connected_business_connectors()
    return jsonify({'connectors': connectors})


@crm_bp.route('/api/crm/clients/<int:client_id>/enrich-all', methods=['POST'])
@login_required
@crm_required
def api_client_enrich_all(client_id):
    """Enrich client from all connected business data connectors."""
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    cui = data.get('cui', '').strip()
    if not cui:
        return jsonify({'success': False, 'error': 'CUI is required'}), 400

    try:
        results = enrich_from_all_connected(cui)

        # Store all enrichment data on profile
        import json as _json
        profile = _fs_repo.get_or_create_profile(client_id)
        existing = profile.get('enrichment_data') or {}
        if isinstance(existing, str):
            try:
                existing = _json.loads(existing)
            except (ValueError, TypeError):
                existing = {}
        existing.update(results)
        _fs_repo.update_profile(client_id, {'enrichment_data': _json.dumps(existing)})

        # Auto-extract structured fields from each connector's data
        for conn_type, conn_result in results.items():
            conn_data = conn_result.get('data') if isinstance(conn_result, dict) else conn_result
            if conn_data:
                _apply_connector_to_profile(client_id, conn_type, conn_data)

        updated_profile = _fs_repo.get_or_create_profile(client_id)
        return jsonify({
            'success': True,
            'results': results,
            'profile': updated_profile,
        })
    except Exception:
        logger.exception('Enrich-all failed for client %s', client_id)
        return jsonify({'success': False, 'error': 'Enrichment failed'}), 500


@crm_bp.route('/api/crm/clients/<int:client_id>/lookup-cui', methods=['POST'])
@login_required
@crm_required
def api_client_lookup_cui(client_id):
    """Search for CUI by company name or Nr. Reg using connected business APIs."""
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    query = data.get('query', '').strip() or client.get('display_name', '')
    if not query:
        return jsonify({'success': False, 'error': 'No search query'}), 400

    results = search_company_by_name(query)

    # Also auto-detect company type
    detected_type = detect_company_type(client.get('display_name', ''))

    return jsonify({
        'success': True,
        'results': results,
        'detected_type': detected_type,
        'query': query,
    })


@crm_bp.route('/api/crm/clients/<int:client_id>/ai-research', methods=['POST'])
@login_required
@crm_required
def api_client_ai_research(client_id):
    """AI-powered company research — generates intelligence report."""
    _ensure_enrichment_column()
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    # Gather all available context
    view_360 = {}
    try:
        view_360 = _fs_repo.get_360(client_id)
    except Exception:
        pass

    profile = view_360.get('profile')
    fiscal = view_360.get('fiscal')
    enrichment_data = {}
    if profile:
        ed = profile.get('enrichment_data')
        if isinstance(ed, str):
            try:
                import json as _json
                enrichment_data = _json.loads(ed)
            except (ValueError, TypeError):
                pass
        elif isinstance(ed, dict):
            enrichment_data = ed

    # Run AI research
    research = ai_research_company(client, profile, fiscal, enrichment_data)

    # Store research in enrichment_data
    if research and 'error' not in research:
        try:
            import json as _json
            profile_obj = _fs_repo.get_or_create_profile(client_id)
            existing = profile_obj.get('enrichment_data') or {}
            if isinstance(existing, str):
                try:
                    existing = _json.loads(existing)
                except (ValueError, TypeError):
                    existing = {}
            existing['ai_research'] = {
                'data': research,
                'fetched_at': __import__('datetime').datetime.now().isoformat(),
            }
            _fs_repo.update_profile(client_id, {'enrichment_data': _json.dumps(existing)})

            # Auto-update client_type if detected as company
            detected_type = detect_company_type(client.get('display_name', ''))
            if detected_type == 'company' and client.get('client_type') != 'company':
                _client_repo.update(client_id, {'client_type': 'company'})

            # If AI suggested a CUI and profile has none, set it
            suggested_cui = research.get('suggested_cui')
            if suggested_cui and not profile_obj.get('cui'):
                _fs_repo.update_profile(client_id, {'cui': str(suggested_cui)})
        except Exception:
            logger.exception('Failed to store AI research for client %s', client_id)

    return jsonify({
        'success': True,
        'research': research,
    })


@crm_bp.route('/api/crm/clients/sanitize', methods=['GET'])
@login_required
@crm_required
def api_sanitize_scan():
    """Scan for data quality issues: wrong types and duplicates."""
    name = request.args.get('name')
    limit = request.args.get('limit', 50, type=int)

    wrong_types = _client_repo.find_wrong_types(name=name, limit=limit)
    duplicates = _client_repo.find_duplicates(name=name, limit=limit)

    # Group duplicates into merge suggestions
    merge_groups = []
    seen = set()
    for dup in duplicates:
        key = tuple(sorted([dup['id_a'], dup['id_b']]))
        if key in seen:
            continue
        seen.add(key)

        # Determine which to keep: prefer the one with more data
        a_score = sum(1 for f in ['phone_a', 'email_a', 'nr_reg_a', 'city_a'] if dup.get(f))
        b_score = sum(1 for f in ['phone_b', 'email_b', 'nr_reg_b', 'city_b'] if dup.get(f))
        keep_id = dup['id_a'] if a_score >= b_score else dup['id_b']
        remove_id = dup['id_b'] if keep_id == dup['id_a'] else dup['id_a']

        merge_groups.append({
            'client_a': {
                'id': dup['id_a'], 'display_name': dup['name_a'],
                'client_type': dup['type_a'], 'phone': dup['phone_a'],
                'email': dup['email_a'], 'nr_reg': dup['nr_reg_a'],
                'city': dup['city_a'],
            },
            'client_b': {
                'id': dup['id_b'], 'display_name': dup['name_b'],
                'client_type': dup['type_b'], 'phone': dup['phone_b'],
                'email': dup['email_b'], 'nr_reg': dup['nr_reg_b'],
                'city': dup['city_b'],
            },
            'similarity': float(dup['sim']),
            'suggested_keep_id': keep_id,
            'suggested_remove_id': remove_id,
        })

    return jsonify({
        'wrong_types': wrong_types,
        'wrong_types_count': len(wrong_types),
        'merge_suggestions': merge_groups,
        'merge_suggestions_count': len(merge_groups),
    })


@crm_bp.route('/api/crm/clients/sanitize/fix-types', methods=['POST'])
@login_required
@crm_required
def api_sanitize_fix_types():
    """Bulk fix client_type for detected wrong types."""
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids required'}), 400
    if len(ids) > 500:
        return jsonify({'success': False, 'error': 'Max 500 clients per batch'}), 400

    count = _client_repo.batch_update_type(ids, 'company')
    return jsonify({'success': True, 'affected': count})


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['DELETE'])
@login_required
@crm_required
def api_client_delete(client_id):
    if not getattr(current_user, 'can_delete_crm', False):
        return jsonify({'success': False, 'error': 'Delete permission denied'}), 403
    if _client_repo.delete(client_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Not found'}), 404


@crm_bp.route('/api/crm/clients/merge', methods=['POST'])
@login_required
@crm_required
def api_merge_clients():
    data = request.get_json(silent=True) or {}
    keep_id = data.get('keep_id')
    remove_id = data.get('remove_id')
    if not keep_id or not remove_id:
        return jsonify({'success': False, 'error': 'keep_id and remove_id required'}), 400
    _client_repo.merge(keep_id, remove_id)
    return jsonify({'success': True})


@crm_bp.route('/api/crm/clients/batch-blacklist', methods=['POST'])
@login_required
@crm_required
def api_batch_blacklist():
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    is_blacklisted = bool(data.get('is_blacklisted', True))
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids required'}), 400
    if len(ids) > 500:
        return jsonify({'success': False, 'error': 'Max 500 clients per batch'}), 400
    count = _client_repo.batch_blacklist(ids, is_blacklisted)
    return jsonify({'success': True, 'affected': count})


@crm_bp.route('/api/crm/clients/batch-delete', methods=['POST'])
@login_required
@crm_required
def api_batch_delete():
    if not getattr(current_user, 'can_delete_crm', False):
        return jsonify({'success': False, 'error': 'Delete permission denied'}), 403
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids required'}), 400
    if len(ids) > 500:
        return jsonify({'success': False, 'error': 'Max 500 clients per batch'}), 400
    count = _client_repo.batch_delete(ids)
    return jsonify({'success': True, 'affected': count})


@crm_bp.route('/api/crm/clients/<int:client_id>/blacklist', methods=['POST'])
@login_required
@crm_required
def api_client_toggle_blacklist(client_id):
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    is_blacklisted = bool(data.get('is_blacklisted', False))
    result = _client_repo.toggle_blacklist(client_id, is_blacklisted)
    if not result:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'client': result})


# ════════════════════════════════════════════════════════════════
# Deals
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/deals', methods=['GET'])
@login_required
@crm_required
def api_deals():
    rows, total = _deal_repo.search(
        source=request.args.get('source'),
        brand=request.args.get('brand'),
        model=request.args.get('model'),
        buyer=request.args.get('buyer'),
        vin=request.args.get('vin'),
        status=request.args.get('status'),
        dealer=request.args.get('dealer'),
        sales_person=request.args.get('sales_person'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        sort_by=request.args.get('sort_by'),
        sort_order=request.args.get('sort_order'),
        limit=request.args.get('limit', 50, type=int),
        offset=request.args.get('offset', 0, type=int),
    )
    return jsonify({'deals': rows, 'total': total})


@crm_bp.route('/api/crm/deals/export', methods=['GET'])
@login_required
@crm_required
def api_deals_export():
    if not getattr(current_user, 'can_export_crm', False):
        return jsonify({'success': False, 'error': 'Export permission denied'}), 403
    rows, _ = _deal_repo.search(
        source=request.args.get('source'), brand=request.args.get('brand'),
        model=request.args.get('model'), buyer=request.args.get('buyer'),
        vin=request.args.get('vin'), status=request.args.get('status'),
        dealer=request.args.get('dealer'), sales_person=request.args.get('sales_person'),
        date_from=request.args.get('date_from'), date_to=request.args.get('date_to'),
        sort_by=request.args.get('sort_by'), sort_order=request.args.get('sort_order'),
        limit=50000, offset=0,
    )
    return _csv_response(rows, 'deals.csv', [
        'id', 'source', 'dossier_number', 'brand', 'model_name', 'buyer_name',
        'dossier_status', 'sale_price_net', 'contract_date', 'vin', 'dealer_name',
        'branch', 'sales_person', 'fuel_type', 'color', 'model_year',
    ])


@crm_bp.route('/api/crm/deals/<int:deal_id>', methods=['GET'])
@login_required
@crm_required
def api_deal_detail(deal_id):
    deal = _deal_repo.get_by_id(deal_id)
    if not deal:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'deal': deal})


@crm_bp.route('/api/crm/deals/<int:deal_id>', methods=['PUT'])
@login_required
@crm_required
def api_deal_update(deal_id):
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    result = _deal_repo.update(deal_id, data)
    if not result:
        return jsonify({'success': False, 'error': 'Not found or no editable fields'}), 404
    return jsonify({'success': True, 'deal': result})


@crm_bp.route('/api/crm/deals/<int:deal_id>', methods=['DELETE'])
@login_required
@crm_required
def api_deal_delete(deal_id):
    if not getattr(current_user, 'can_delete_crm', False):
        return jsonify({'success': False, 'error': 'Delete permission denied'}), 403
    if _deal_repo.delete(deal_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Not found'}), 404


@crm_bp.route('/api/crm/deals/detailed-stats', methods=['GET'])
@login_required
@crm_required
def api_deal_detailed_stats():
    def _split(key):
        v = request.args.get(key)
        return [x for x in v.split(',') if x] if v else None
    return jsonify(_deal_repo.get_detailed_stats(
        dealers=_split('dealers'),
        brands=_split('brands'),
        statuses=_split('statuses'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
    ))


@crm_bp.route('/api/crm/clients/cities', methods=['GET'])
@login_required
@crm_required
def api_client_cities():
    cities = _client_repo.get_cities()
    return jsonify({'cities': [c['city'] for c in cities]})


@crm_bp.route('/api/crm/clients/responsibles', methods=['GET'])
@login_required
@crm_required
def api_client_responsibles():
    responsibles = _client_repo.get_responsibles()
    return jsonify({'responsibles': [r['responsible'] for r in responsibles]})


@crm_bp.route('/api/crm/clients/detailed-stats', methods=['GET'])
@login_required
@crm_required
def api_client_detailed_stats():
    return jsonify(_client_repo.get_detailed_stats())


@crm_bp.route('/api/crm/deals/brands', methods=['GET'])
@login_required
@crm_required
def api_deal_brands():
    brands = _deal_repo.get_brands()
    return jsonify({'brands': [b['brand'] for b in brands]})


@crm_bp.route('/api/crm/deals/dealers', methods=['GET'])
@login_required
@crm_required
def api_deal_dealers():
    return jsonify({'dealers': _deal_repo.get_dealers()})


@crm_bp.route('/api/crm/deals/sales-persons', methods=['GET'])
@login_required
@crm_required
def api_deal_sales_persons():
    return jsonify({'sales_persons': _deal_repo.get_sales_persons()})


@crm_bp.route('/api/crm/deals/statuses', methods=['GET'])
@login_required
@crm_required
def api_deal_statuses():
    statuses = _deal_repo.get_statuses()
    return jsonify({'statuses': statuses})


@crm_bp.route('/api/crm/deals/order-statuses', methods=['GET'])
@login_required
@crm_required
def api_deal_order_statuses():
    return jsonify({'statuses': _deal_repo.get_order_statuses()})


@crm_bp.route('/api/crm/deals/contract-statuses', methods=['GET'])
@login_required
@crm_required
def api_deal_contract_statuses():
    return jsonify({'statuses': _deal_repo.get_contract_statuses()})


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

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
