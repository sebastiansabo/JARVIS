"""Record routes — buyback_records CRUD (list/detail/create/update/cancel/
reopen/delete), gated by @v2_permission_required('buyback', 'record', ...)
plus a company-scoping/IDOR guard on top (`g.permission_scope` alone isn't
enough: an 'own'-scope caller must never read/mutate another company's
record even if they can guess/enumerate its id).

No SQL lives here — every DB access goes through buyback.routes._shared's
singleton repos/service (RecordRepository, PhotoRepository, EventRepository,
OfferRepository, BuyBackService).
"""
import logging

from flask import request, jsonify, g
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback import lifecycle
from buyback.routes import _shared
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.buyback')

# Server-side whitelist of client-suppliable "intake" fields for CREATE.
# Deliberately excludes: id/record_code/company_id/created_by/status
# (server-assigned) and every evaluation/offer/purchase-stage column
# (inspection_*, purchase_price_eur, carpark_vehicle_id, bought_at,
# finalized_by, lost_reason, updated_by, closed_at) — those are only ever
# written by the dedicated stage routes/services (later tasks), never at
# intake. `vin` is handled separately (validated against VIN_RE first).
_CREATE_FIELDS = (
    'brand_id', 'acquisition_type', 'is_trade_in', 'advisor_id', 'advisor_name',
    'client_type', 'vat_status', 'client_id',
    'seller_name', 'seller_email', 'seller_phone', 'seller_cui',
    'brand', 'model', 'variant', 'equipment',
    'mileage_km', 'engine_capacity_cm3',
    'fuel_type', 'transmission', 'gearbox',
    'manufacture_date', 'first_registration_date',
    'service_history_uptodate', 'extra_wheels', 'keys_count',
    'has_damage', 'damage_details', 'general_condition',
    'client_asking_price_eur', 'client_source',
    'other_details', 'drive_folder_link',
    'target_vehicle_text', 'target_carpark_vehicle_id', 'crm_deal_id',
)


def _scoped_company_id():
    """Resolve the company_id to act on for CREATE/LIST: an 'own'-scope
    caller (Sales) is always pinned to their own company, ignoring any
    request-supplied company_id; only an 'all'-scope caller (Admin/Manager)
    may use the tenant-switcher (_acting_company_id, which itself only
    allows companies the caller may act on).

    Returns None for a non-'all'-scope caller who has NO company — callers
    MUST fail closed on that (never pass None to RecordRepository.list for a
    non-'all' caller: list() treats company_id=None as "no company filter",
    i.e. ALL companies, a cross-tenant leak). See list_records/create_record.
    """
    if g.permission_scope != 'all':
        return getattr(current_user, 'company_id', None)
    return _shared._acting_company_id()


# ═══════════════════════════════════════════════
# LIST
# ═══════════════════════════════════════════════

@buyback_bp.route('/records', methods=['GET'])
@login_required
@v2_permission_required('buyback', 'record', 'view')
def list_records():
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = max(1, min(100, int(request.args.get('per_page', 25))))
    except (ValueError, TypeError):
        page, per_page = 1, 25

    company_id = _scoped_company_id()
    if g.permission_scope != 'all' and company_id is None:
        # Fail closed: a company-less own/department caller must NEVER fall
        # through to an unfiltered (all-companies) list. Return an empty page
        # rather than leaking every tenant's records.
        return jsonify({'records': [], 'total': 0, 'page': page, 'per_page': per_page})

    rows, total = _shared.records_repo.list(
        company_id=company_id,
        status=request.args.get('status'),
        acquisition_type=request.args.get('acquisition_type'),
        q=request.args.get('q'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        page=page, per_page=per_page,
        sort_by=request.args.get('sort_by', 'created_at'),
        sort_dir=request.args.get('sort_dir', 'DESC'),
    )
    return jsonify({
        'records': _shared._serialize(rows),
        'total': total,
        'page': page,
        'per_page': per_page,
    })


# ═══════════════════════════════════════════════
# DETAIL
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>', methods=['GET'])
@login_required
@v2_permission_required('buyback', 'record', 'view')
def get_record(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    if g.permission_scope != 'all':
        err = _shared._guard_company(record)
        if err:
            return err

    offers = _shared.offers_repo.list_for_record(record_id)
    photos = _shared.photos_repo.get_by_record(record_id)
    events = _shared.events_repo.list_for_record(record_id)
    return jsonify({
        'record': _shared._serialize(record),
        'offers': _shared._serialize(offers),
        'photos': _shared._serialize(photos),
        'events': _shared._serialize(events),
    })


# ═══════════════════════════════════════════════
# CREATE
# ═══════════════════════════════════════════════

@buyback_bp.route('/records', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'create')
def create_record():
    data = request.get_json(silent=True) or {}

    vin = (data.get('vin') or '').strip().upper()
    if not vin or not _shared.VIN_RE.match(vin):
        return jsonify({
            'success': False,
            'error': 'Invalid VIN — must be a 17-character VIN (no I/O/Q)',
        }), 400

    raw_images = data.get('images')
    if raw_images is not None and not isinstance(raw_images, list):
        return jsonify({'success': False, 'error': 'images must be an array'}), 400

    company_id = _scoped_company_id()
    if company_id is None:
        # Fail closed rather than INSERT company_id=NULL (a NOT NULL violation
        # → raw 500). A non-'all' caller with no company has no tenant to
        # create in; a global admin normally carries a company or passes one.
        return jsonify({'success': False, 'error': 'No company assigned to your account'}), 403

    create_data = {k: data[k] for k in _CREATE_FIELDS if k in data}
    create_data['vin'] = vin
    create_data['company_id'] = company_id
    create_data['created_by'] = current_user.id
    create_data['record_code'] = _shared._gen_record_code(vin)
    create_data['status'] = lifecycle.PENDING_EVALUATION

    record = _shared.records_repo.create(create_data)

    # Non-blocking heads-up: the same VIN already exists in CarPark stock.
    # Never blocks the buyback intake — just flagged in the response so the
    # UI can surface a warning.
    vin_in_carpark = False
    try:
        from carpark.repositories.vehicle_repository import VehicleRepository
        vin_in_carpark = bool(VehicleRepository().get_by_vin(vin))
    except Exception:
        logger.warning('VIN-in-carpark lookup failed for %s', vin, exc_info=True)

    # Optional base64 image batch. Blank/None entries are dropped before
    # reaching PhotoRepository.store_base64_images (it has no guard for
    # falsy entries and would TypeError on len(None)).
    images = [img for img in (raw_images or []) if img]
    if images:
        try:
            _shared.photos_repo.store_base64_images(
                record['id'], images, _shared.MAX_CREATE_BYTES,
            )
        except ValueError as e:
            # Roll back the just-inserted record so an oversized create leaves
            # NO ghost row. store_base64_images checks the batch size BEFORE any
            # Spaces upload, so nothing was uploaded and no child rows exist —
            # the record delete (its FK CASCADE would clear children anyway) is
            # all that's needed. The audit event is logged only AFTER this
            # block succeeds, so there's no orphaned event to clean up either.
            _shared.records_repo.delete(record['id'])
            return jsonify({'success': False, 'error': str(e)}), 413

    _shared.events_repo.log(
        record['id'], 'created', current_user.id,
        {'vin_in_carpark': vin_in_carpark},
    )

    response = {'success': True, 'record': _shared._serialize(record)}
    if vin_in_carpark:
        response['vin_in_carpark'] = True
    return jsonify(response), 201


# ═══════════════════════════════════════════════
# UPDATE
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>', methods=['PUT'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def update_record(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    if record['status'] != lifecycle.PENDING_EVALUATION:
        return jsonify({
            'success': False,
            'error': f"Cannot edit a record in status {record['status']!r} "
                     f"(only {lifecycle.PENDING_EVALUATION!r} is editable)",
        }), 409

    data = request.get_json(silent=True) or {}
    # SECURITY: gate through the same intake-only whitelist as CREATE, not
    # the raw request body. RecordRepository.update()'s own
    # `_UPDATABLE_COLUMNS` guard only protects against a caller-controlled
    # key becoming a SQL identifier — it is NOT an authorization boundary,
    # and it includes workflow/finance fields (purchase_price_eur,
    # carpark_vehicle_id, finalized_by, bought_at, closed_at, inspected_by,
    # inspected_at, inspection_rating, reconditioning_cost_eur, lost_reason,
    # updated_by) that only the dedicated stage services (offer/inspection/
    # purchase — later tasks) may ever set. Without this whitelist, any
    # caller with plain `record.edit` (e.g. Sales, 'own' scope) could forge
    # those fields on their own still-PENDING_EVALUATION record before any
    # offer/inspection ever happened.
    update_data = {k: data[k] for k in _CREATE_FIELDS if k in data}
    updated = _shared.records_repo.update(record_id, update_data)
    return jsonify({'success': True, 'record': _shared._serialize(updated)})


# ═══════════════════════════════════════════════
# CANCEL
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/cancel', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def cancel_record(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        updated = _shared.service.transition(
            record, lifecycle.CANCELLED, current_user.id,
            {'reason': data.get('reason')},
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 409
    return jsonify({'success': True, 'record': _shared._serialize(updated)})


# ═══════════════════════════════════════════════
# REOPEN
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/reopen', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def reopen_record(record_id):
    if not _shared._is_admin():
        return jsonify({'success': False, 'error': 'Admin/Manager permission required'}), 403

    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    # Tenant boundary applies to reopen too — an admin/manager scoped to
    # company A must not reopen a company-B record (the _is_admin() check
    # above is only the role-capability gate, NOT the company boundary).
    err = _shared._guard_company(record)
    if err:
        return err

    try:
        updated = _shared.service.transition(
            record, lifecycle.PENDING_EVALUATION, current_user.id,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 409
    return jsonify({'success': True, 'record': _shared._serialize(updated)})


# ═══════════════════════════════════════════════
# DELETE
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>', methods=['DELETE'])
@login_required
@v2_permission_required('buyback', 'record', 'delete')
def delete_record(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    _shared.records_repo.delete(record_id)
    return jsonify({'success': True})
