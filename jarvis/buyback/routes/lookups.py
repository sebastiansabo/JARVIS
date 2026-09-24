"""Lookup/reference routes — dropdown option sets, CRM client search/create
(the seller), and CarPark vehicle search (the trade-in target link).

All four routes are gated identically to every other buyback route:
@login_required + @v2_permission_required('buyback', 'record', 'view') —
there is no separate "lookups" permission entity, so anyone who may view
buyback records may resolve these reference lookups too.

No SQL lives here. CRM client lookups go through
crm.repositories.client_repository.ClientRepository, CarPark vehicle lookups
go through carpark.repositories.vehicle_repository.VehicleRepository, and
dropdown lookups go through core.settings.dropdowns' DropdownRepository —
all three singletons live on buyback.routes._shared (mirroring every other
buyback route module's `_shared.records_repo` etc. convention), never
reimplemented here.
"""
import logging
import re

from flask import request, jsonify, g
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback.routes import _shared
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.buyback')

# Same phone shape foi_parcurs' login-gated crm-clients POST validates
# against (jarvis/foi_parcurs/routes/test_drive.py::_PHONE_RE) — E.164-ish
# international, or a Romanian 07xxxxxxxx / international-prefixed 004...
# local shape.
_PHONE_RE = re.compile(r'^(\+\d{7,15}|07\d{8}|004\d{10})$')

# Below this length, ClientRepository.search()'s ILIKE '%q%' would scan the
# whole crm_clients table for a near-useless result set — mirrors
# foi_parcurs's api_search_crm_clients (test_drive.py) returning an empty
# list rather than 400ing, so the frontend can fire the search on every
# keystroke without special-casing short input.
_MIN_SEARCH_LEN = 2


def _normalize_name(name):
    """Lowercase + collapse whitespace for crm_clients.name_normalized
    (trigram-indexed). Copied from foi_parcurs/routes/test_drive.py's helper
    of the same name — small enough not to warrant a shared import across
    modules."""
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


def _scoped_company_id():
    """Company to scope the CarPark vehicle search to. Mirrors
    buyback/routes/records.py::_scoped_company_id: an 'own'-scope caller
    (Sales) is always pinned to their own company, ignoring any
    request-supplied company_id; only an 'all'-scope caller (Admin/Manager)
    may use the tenant-switcher (_shared._acting_company_id, which itself
    only allows companies the caller may act on)."""
    if g.permission_scope != 'all':
        return getattr(current_user, 'company_id', None)
    return _shared._acting_company_id()


# ═══════════════════════════════════════════════
# OPTIONS — dropdown value sets for the intake form
# ═══════════════════════════════════════════════

# Static fallbacks below mirror CarPark's own frontend constants
# (frontend/src/data/autovitData.ts AUTOVIT_FUEL_TYPES / AUTOVIT_GEARBOX_TYPES
# / AUTOVIT_DRIVE_TYPES) translated to Romanian labels, since a grep of
# migrations/domains for dropdown_type usage turns up no 'fuel_type' /
# 'transmission' / 'gearbox' / 'vat_status' rows seeded in dropdown_options —
# CarPark itself sources these from frontend constants, not the DB, for the
# same fields. _dropdown_or_static() still checks dropdown_options first so
# an admin who later adds rows under one of these types via Settings >
# Dropdowns is picked up with no code change.
_STATIC_FUEL_TYPES = [
    {'value': 'petrol', 'label': 'Benzina'},
    {'value': 'diesel', 'label': 'Diesel'},
    {'value': 'electric', 'label': 'Electric'},
    {'value': 'hybrid', 'label': 'Hibrid'},
    {'value': 'plugin-hybrid', 'label': 'Hibrid Plug-In'},
    {'value': 'petrol-lpg', 'label': 'Benzina + GPL'},
    {'value': 'petrol-cng', 'label': 'Benzina + CNG'},
]

# "transmission" on buyback_records is the drive layout — front/rear/4x4 —
# distinct from "gearbox" below (manual vs automatic). Autovit's equivalent
# filter is confusingly also named "transmission" (filter_enum_transmission)
# for what is really drive-type; see carpark/connectors/vin_decoder/mapper.py.
_STATIC_TRANSMISSIONS = [
    {'value': 'front-wheel', 'label': 'Fata (FWD)'},
    {'value': 'rear-wheel', 'label': 'Spate (RWD)'},
    {'value': 'all-wheel-permanent', 'label': '4x4 Permanent'},
    {'value': 'all-wheel-auto', 'label': '4x4 Automat'},
]

_STATIC_GEARBOXES = [
    {'value': 'manual', 'label': 'Manuala'},
    {'value': 'automatic', 'label': 'Automata'},
]

_STATIC_VAT_STATUSES = [
    {'value': 'with_vat', 'label': 'Cu TVA'},
    {'value': 'no_vat', 'label': 'Fara TVA'},
]

_STATIC_CLIENT_SOURCES = [
    {'value': 'website', 'label': 'Website'},
    {'value': 'phone', 'label': 'Telefon'},
    {'value': 'walk_in', 'label': 'Vizita directa'},
    {'value': 'referral', 'label': 'Recomandare'},
    {'value': 'social_media', 'label': 'Social Media'},
    {'value': 'other', 'label': 'Altele'},
]

_ACQUISITION_TYPES = [
    {'value': 'buyback', 'label': 'Buyback'},
    {'value': 'tradein', 'label': 'Trade-In'},
]

_CLIENT_TYPES = [
    {'value': 'person', 'label': 'Persoana fizica'},
    {'value': 'company', 'label': 'Persoana juridica'},
]


def _dropdown_or_static(dropdown_type, static_list):
    """Active rows from dropdown_options for `dropdown_type` as
    {value, label} dicts, or `static_list` when there are none / the lookup
    errors (never lets a dropdown-config hiccup 500 the whole options
    response)."""
    try:
        rows = _shared.dropdown_repo.get_options(dropdown_type=dropdown_type, active_only=True)
    except Exception:
        logger.warning('Dropdown lookup failed for type=%r', dropdown_type, exc_info=True)
        rows = None
    if rows:
        return [{'value': r['value'], 'label': r['label']} for r in rows]
    return static_list


@buyback_bp.route('/lookups/options', methods=['GET'])
@login_required
@v2_permission_required('buyback', 'record', 'view')
def get_lookup_options():
    return jsonify({
        'fuel_types': _dropdown_or_static('fuel_type', _STATIC_FUEL_TYPES),
        'transmissions': _dropdown_or_static('transmission', _STATIC_TRANSMISSIONS),
        'gearboxes': _dropdown_or_static('gearbox', _STATIC_GEARBOXES),
        'vat_statuses': _dropdown_or_static('vat_status', _STATIC_VAT_STATUSES),
        'acquisition_types': _ACQUISITION_TYPES,
        'client_types': _CLIENT_TYPES,
        'client_sources': _dropdown_or_static('buyback_client_source', _STATIC_CLIENT_SOURCES),
    })


# ═══════════════════════════════════════════════
# CRM CLIENT — search (the seller)
# ═══════════════════════════════════════════════

@buyback_bp.route('/lookups/crm-clients/search', methods=['GET'])
@login_required
@v2_permission_required('buyback', 'record', 'view')
def search_crm_clients():
    q = (request.args.get('q') or '').strip()
    if len(q) < _MIN_SEARCH_LEN:
        return jsonify({'clients': []})

    try:
        limit = min(max(int(request.args.get('limit', 20)), 1), 50)
    except (TypeError, ValueError):
        limit = 20

    try:
        rows, _total = _shared.client_repo.search(q=q, limit=limit)
    except Exception:
        logger.exception('CRM client search failed for q=%r', q)
        return jsonify({'clients': [], 'error': 'Search failed'}), 500
    return jsonify({'clients': _shared._serialize(rows)})


# ═══════════════════════════════════════════════
# CRM CLIENT — create (the seller)
# ═══════════════════════════════════════════════

@buyback_bp.route('/lookups/crm-clients', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'view')
def create_crm_client():
    data = request.get_json(silent=True) or {}

    display_name = (data.get('display_name') or data.get('name') or '').strip()
    if not display_name:
        return jsonify({'success': False, 'error': 'display_name is required'}), 400

    phone = (data.get('phone') or '').strip()
    phone_clean = phone.replace(' ', '').replace('-', '')
    if not _PHONE_RE.match(phone_clean):
        return jsonify({
            'success': False,
            'error': 'Invalid phone. Use international format, e.g. +40721234567',
        }), 400

    is_company = bool(data.get('is_company')) or data.get('client_type') == 'company'
    email = (data.get('email') or '').strip() or None
    street = (data.get('street') or data.get('address') or '').strip() or None
    city = (data.get('city') or '').strip() or None
    region = (data.get('region') or data.get('county') or '').strip() or None
    company_name = (data.get('company_name') or '').strip() or None
    cui = (data.get('cui') or '').strip() or None

    try:
        row = _shared.client_repo.create(
            display_name=display_name,
            name_normalized=_normalize_name(display_name),
            client_type='company' if is_company else 'person',
            phone=phone_clean,
            phone_raw=phone,
            email=email,
            street=street,
            city=city,
            region=region,
            company_name=company_name,
            cui=cui,
            source_flags={'buyback': True},
        )
    except Exception:
        # Validation errors (bad input) and dupe/constraint errors both land
        # here — mapped to 400, never a raw 500, per the module's
        # "bad/missing typed input -> 400" convention (see records.py CREATE).
        logger.exception('Failed to create CRM client from buyback lookups')
        return jsonify({'success': False, 'error': 'Failed to create client'}), 400

    new_id = row['id'] if row else None
    client = _shared.client_repo.get_by_id(new_id) if new_id else None
    if client is None:
        return jsonify({'success': False, 'error': 'Failed to create client'}), 400
    return jsonify({'success': True, 'client': _shared._serialize(client)}), 201


# ═══════════════════════════════════════════════
# CARPARK VEHICLE — search (the trade-in target)
# ═══════════════════════════════════════════════

@buyback_bp.route('/lookups/carpark-vehicles/search', methods=['GET'])
@login_required
@v2_permission_required('buyback', 'record', 'view')
def search_carpark_vehicles():
    company_id = _scoped_company_id()
    if g.permission_scope != 'all' and company_id is None:
        # Fail closed — mirrors records.py::list_records: a company-less
        # own/department caller must never fall through to an unfiltered
        # (all-companies) vehicle search.
        return jsonify({'vehicles': []})

    try:
        per_page = min(max(int(request.args.get('limit', 20)), 1), 50)
    except (TypeError, ValueError):
        per_page = 20

    filters = {}
    if company_id is not None:
        filters['company_id'] = company_id
    q = (request.args.get('q') or '').strip()
    if len(q) >= _MIN_SEARCH_LEN:
        filters['search'] = q

    try:
        result = _shared.carpark_vehicle_repo.get_catalog(filters=filters, page=1, per_page=per_page)
    except Exception:
        logger.exception('CarPark vehicle search failed for q=%r', q)
        return jsonify({'vehicles': [], 'error': 'Search failed'}), 500
    return jsonify({'vehicles': _shared._serialize(result['items'])})
