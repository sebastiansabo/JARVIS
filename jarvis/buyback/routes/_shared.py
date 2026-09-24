"""Shared imports, singleton repos/service, and route helpers for buyback
routes.

`_acting_company_id()` is a byte-for-byte copy of
carpark/routes/vehicles.py's helper of the same name (same "permissive
tenant switcher" semantics: a request-provided company_id is honored only
if the caller may act on it — own + org-responsable companies, Admin = any
— else the request 403s; absent a company_id, falls back to the caller's
own company). Route handlers that serve 'own'-scope callers (Sales, per
migrations/domains/schema_roles.py::_seed_buyback_permissions_v2) must NOT
call this for those callers — they force company_id = current_user.company_id
directly instead, both as the correct IDOR posture (an 'own'-scope caller
has no business picking an arbitrary company_id) and because this helper's
DB-backed org lookup only resolves for real `users` rows.
"""
import decimal
import re
import secrets
from datetime import date, datetime, timezone

from flask import request, jsonify, abort, make_response, g
from flask_login import current_user

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.offer_repository import OfferRepository
from buyback.repositories.photo_repository import PhotoRepository
from buyback.repositories.event_repository import EventRepository
from buyback.services.buyback_service import BuyBackService
from buyback.services.email import Notifier
from core.organization.manager_utils import get_actable_company_ids

# Cross-module repos reused (not reimplemented) by lookups.py: the CRM client
# repo for the seller search/create, the CarPark vehicle repo for the
# trade-in target search, and the core Settings dropdown repo for
# admin-configurable option lists. Safe as top-level imports — neither crm
# nor carpark imports anything from buyback (no import cycle), and app.py
# registers crm_bp/carpark_bp before buyback_bp anyway (app.py::
# _register_blueprints).
from crm.repositories.client_repository import ClientRepository
from carpark.repositories.vehicle_repository import VehicleRepository
from core.settings.dropdowns.repositories.dropdown_repository import DropdownRepository

# ── Singleton repo/service instances (mirrors carpark/routes/vehicles.py's
# module-level `_vehicle_service = VehicleService()`) ──
records_repo = RecordRepository()
offers_repo = OfferRepository()
photos_repo = PhotoRepository()
events_repo = EventRepository()
client_repo = ClientRepository()
carpark_vehicle_repo = VehicleRepository()
dropdown_repo = DropdownRepository()
# BuyBackService itself never imports buyback.services.email at module top
# level (Ruling R2, buyback_service.py's docstring) — that import cycle risk
# doesn't apply HERE: _shared.py is a leaf the routes import, and email.py's
# own deps (core.services.notification_service, foi_parcurs.dealer_config)
# don't loop back into buyback at all. Notifier() itself never raises on
# construction; its methods swallow their own exceptions (see email.py) so
# an email/SMTP failure never surfaces as a 500 on the offer-post request.
service = BuyBackService(notifier=Notifier())

# Base64 image batch cap enforced on record CREATE (PhotoRepository.
# store_base64_images checks the DECODED total against this). Module-level
# so tests can monkeypatch `buyback.routes._shared.MAX_CREATE_BYTES` — routes
# must read it as `_shared.MAX_CREATE_BYTES` (module-attribute access) at
# call time, not via a `from ... import MAX_CREATE_BYTES` binding, or a
# monkeypatch here won't be seen by the route.
MAX_CREATE_BYTES = 12 * 1024 * 1024

# 17-char VIN shape (no I/O/Q — standard VIN alphabet exclusions). No
# check-digit validation, just shape, matching carpark's check-vin route.
VIN_RE = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')

_ADMIN_ROLE_NAMES = ('admin', 'superadmin', 'Admin', 'Manager')


def _acting_company_id():
    """Company the caller is acting as: a request-provided company_id if the
    caller may act on it (own + org-responsable companies; Admin = any), else
    aborts 403. Absent company_id falls back to the user's own company.

    COPIED from carpark/routes/vehicles.py::_acting_company_id (kept in sync
    intentionally — this is the one tenant-switcher semantics the app has).
    """
    if request.method == 'GET':
        cid = request.args.get('company_id')
    else:
        body = request.get_json(silent=True) or request.form
        cid = body.get('company_id') if body else None

    if cid not in (None, ''):
        try:
            cid_int = int(cid)
        except (TypeError, ValueError):
            cid_int = None
        if cid_int is not None:
            is_admin = getattr(current_user, 'can_access_settings', False)
            if not is_admin and cid_int not in get_actable_company_ids(current_user.id):
                abort(make_response(
                    jsonify({'success': False, 'error': 'Company not permitted'}), 403))
            return cid_int
    return getattr(current_user, 'company_id', None)


def _is_admin():
    """True for Admin/Manager-named roles, or anyone with the legacy
    can_access_settings superuser flag.

    NOTE: this is a ROLE-CAPABILITY check ("is this an admin/manager kind of
    user"), NOT a tenant boundary. It is used ONLY for the reopen route's
    "must be admin/manager" gate. It must NEVER be used to bypass the
    company/IDOR boundary — that is _guard_company's job (see below), which
    is bounded by the exact same company set the caller can LIST/CREATE
    against, so a company-A manager can't mutate a company-B record it can't
    even see.
    """
    return (
        getattr(current_user, 'role_name', None) in _ADMIN_ROLE_NAMES
        or getattr(current_user, 'can_access_settings', False)
    )


def _permitted_company_ids():
    """The set of company_ids the acting caller may READ and MUTATE — the
    single tenant boundary shared by LIST/CREATE scoping and the
    _guard_company IDOR check, so mutate access can never exceed read access
    (fix round 1: a Manager org-responsible for only company A must NOT be
    able to PUT/cancel/reopen/DELETE a company-B record it can't LIST).

    Returns None as a sentinel meaning "unrestricted — every company". This
    is returned for a true global admin (`can_access_settings`), because that
    is exactly the boundary `_acting_company_id()` already gives them on
    LIST/CREATE: its admin check is `is_admin = can_access_settings`, and a
    global admin there may switch to ANY company_id. get_actable_company_ids()
    deliberately does NOT enumerate all companies for a global admin (its
    docstring: "Admin bypass ... is the caller's responsibility; this returns
    only the user's scoped set"), so gating a global admin on it would both
    lock them out of records outside their org-responsibility AND break every
    admin test here (a fabricated test admin has an empty actable set). Hence
    the explicit unrestricted sentinel.

    Otherwise a concrete set:
      - scope 'all' held WITHOUT the global-admin flag (e.g. a Manager granted
        'all' scope): get_actable_company_ids() — the SAME source
        _acting_company_id() validates a requested company_id against.
      - own/department scope: just the caller's own company ({company_id}),
        or an EMPTY set when they have no company (fail closed — never widen
        to "all").
    """
    if g.permission_scope == 'all':
        if getattr(current_user, 'can_access_settings', False):
            return None  # unrestricted global admin
        return set(get_actable_company_ids(current_user.id))
    company_id = getattr(current_user, 'company_id', None)
    return {company_id} if company_id is not None else set()


def _guard_company(record):
    """IDOR guard for single-record mutations/reads: returns a (response,
    403) tuple if the acting caller may not touch `record`, else None. The
    boundary is `_permitted_company_ids()` — IDENTICAL to the company set the
    caller can LIST/CREATE against — so mutate access exactly mirrors read
    access. No role-name shortcut: a company-A manager is 403'd on a company-B
    record even though it's an "admin-ish" role, because company B is not in
    its permitted set. A true global admin's permitted set is None
    (unrestricted) and always passes. Callers do:

        err = _guard_company(record)
        if err:
            return err
    """
    permitted = _permitted_company_ids()
    if permitted is None or record['company_id'] in permitted:
        return None
    return jsonify({'success': False, 'error': 'Forbidden'}), 403


def _gen_record_code(vin):
    """BB-<vin8>-<ts>-<rand> — human-scannable, collision-safe record code.
    `vin` is expected already validated/upper-cased by the caller; datetime/
    secrets (not Date.now/Math.random) generate the timestamp/random parts,
    since this runs in Python route code, not the browser."""
    vin_part = (vin or 'XXXXXXXX')[:8].upper()
    ts = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')
    rand = secrets.token_hex(2).upper()
    return f'BB-{vin_part}-{ts}-{rand}'


def _serialize(obj):
    """Convert Decimal/date/datetime to JSON-safe types (mirrors
    carpark/routes/vehicles.py::_serialize — buyback_records carries the
    same NUMERIC/DATE/TIMESTAMPTZ column types)."""
    import decimal
    import datetime as _dt
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    return obj


# ── Intake validation/coercion (shared by CREATE + UPDATE) ─────────────────
#
# records.py's create_record/update_record build their column dict straight
# from client-supplied JSON and hand it to RecordRepository.create/update,
# which bind every value as a %s parameter — a badly-typed value (e.g.
# mileage_km: 'abc', or a dict where a text column is expected) doesn't fail
# in Python at all; it reaches psycopg2/Postgres and raises a DB-level error
# (psycopg2.errors.* — NOT a ValueError), which no route `except ValueError`
# catches, surfacing as a raw uncaught 500. `_validate_intake` runs BEFORE
# that, on the raw request dict, and turns any bad value into a clean
# ValueError the route can catch and 400 on.

_INTAKE_INT_FIELDS = ('mileage_km', 'engine_capacity_cm3', 'keys_count', 'general_condition')
_INTAKE_NUMERIC_FIELDS = ('client_asking_price_eur', 'reconditioning_cost_eur')
_INTAKE_DATE_FIELDS = ('manufacture_date', 'first_registration_date')
_INTAKE_BOOL_FIELDS = ('has_damage', 'is_trade_in', 'service_history_uptodate', 'extra_wheels')
# Scalar-only text fields — a dict/list here would otherwise reach psycopg2's
# adapter and raise "can't adapt type 'dict'"/'list' (a ProgrammingError, not
# a ValueError) -> uncaught 500.
_INTAKE_TEXT_FIELDS = (
    'brand', 'model', 'variant', 'equipment', 'damage_details', 'other_details',
    'seller_name', 'seller_email', 'seller_phone', 'seller_cui',
    'client_source', 'drive_folder_link', 'target_vehicle_text',
    'vat_status', 'acquisition_type', 'client_type',
)

_TRUE_STRINGS = {'true', '1', 'yes', 'y', 'on'}
_FALSE_STRINGS = {'false', '0', 'no', 'n', 'off'}


def _coerce_bool(field, value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):  # bool is an int subclass; caught above already
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in _TRUE_STRINGS:
            return True
        if low in _FALSE_STRINGS:
            return False
    raise ValueError(f'{field} must be a boolean')


def is_nonempty_str(value):
    """True for a non-blank string — used to enforce brand/model at CREATE
    (and, when supplied, at UPDATE)."""
    return isinstance(value, str) and value.strip() != ''


def validate_intake(data: dict) -> dict:
    """Validate + coerce the client-suppliable "intake" fields shared by
    CREATE and UPDATE (records.py's `_CREATE_FIELDS` whitelist). Only keys
    PRESENT (and non-None) in `data` are checked, so a partial UPDATE
    payload that omits a field is unaffected. Returns a NEW dict (shallow
    copy of `data`) with the checked fields coerced to their proper Python
    type; raises ValueError(message) on the first invalid value — callers
    must catch this and return 400 (never let it propagate to the DB
    layer).
    """
    out = dict(data)

    for field in _INTAKE_INT_FIELDS:
        if out.get(field) is not None:
            try:
                out[field] = int(out[field])
            except (TypeError, ValueError):
                raise ValueError(f'{field} must be an integer')

    if out.get('general_condition') is not None and not (1 <= out['general_condition'] <= 5):
        raise ValueError('general_condition must be between 1 and 5')
    if out.get('keys_count') is not None and out['keys_count'] < 0:
        raise ValueError('keys_count must be >= 0')

    for field in _INTAKE_NUMERIC_FIELDS:
        if out.get(field) is not None:
            try:
                out[field] = decimal.Decimal(str(out[field]))
            except (decimal.InvalidOperation, TypeError, ValueError):
                raise ValueError(f'{field} must be numeric')

    for field in _INTAKE_DATE_FIELDS:
        if out.get(field) is not None:
            try:
                date.fromisoformat(str(out[field]))
            except (TypeError, ValueError):
                raise ValueError(f'{field} must be an ISO date (YYYY-MM-DD)')

    for field in _INTAKE_BOOL_FIELDS:
        if out.get(field) is not None:
            out[field] = _coerce_bool(field, out[field])

    for field in _INTAKE_TEXT_FIELDS:
        if isinstance(out.get(field), (dict, list)):
            raise ValueError(f'{field} must be a plain value, not an object/array')

    return out
