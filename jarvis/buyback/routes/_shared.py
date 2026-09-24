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
import re
import secrets
from datetime import datetime, timezone

from flask import request, jsonify, abort, make_response
from flask_login import current_user

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.offer_repository import OfferRepository
from buyback.repositories.photo_repository import PhotoRepository
from buyback.repositories.event_repository import EventRepository
from buyback.services.buyback_service import BuyBackService
from core.organization.manager_utils import get_actable_company_ids

# ── Singleton repo/service instances (mirrors carpark/routes/vehicles.py's
# module-level `_vehicle_service = VehicleService()`) ──
records_repo = RecordRepository()
offers_repo = OfferRepository()
photos_repo = PhotoRepository()
events_repo = EventRepository()
service = BuyBackService()

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
    can_access_settings superuser flag."""
    return (
        getattr(current_user, 'role_name', None) in _ADMIN_ROLE_NAMES
        or getattr(current_user, 'can_access_settings', False)
    )


def _guard_company(record):
    """IDOR guard for single-record mutations/reads: returns a (response,
    403) tuple if the acting user may not touch `record` (not an admin, and
    the record belongs to a different company), else None. Callers do:

        err = _guard_company(record)
        if err:
            return err
    """
    if not _is_admin() and record['company_id'] != getattr(current_user, 'company_id', None):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    return None


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
