"""Inspection routes — save inspection fields on a buyback record while it's
sitting in INSPECTION status, and upload the accompanying service-report PDF.

Two endpoints, both gated by
@v2_permission_required('buyback', 'inspection', 'manage') (the Service-role
permission seeded by migrations/domains/schema_roles.py::_seed_buyback_permissions_v2):
  - PUT /records/<id>/inspection          — save inspection_rating/
    reconditioning_cost_eur/inspection_notes; stamps inspected_by/inspected_at.
  - POST /records/<id>/inspection/report  — upload a PDF service report to
    Spaces, sets inspection_report_key.

Both apply the SAME company-scoping/IDOR guard as records.py/offers.py
(_shared._guard_company), loaded via the SAME repo the record routes use
(_shared.records_repo.get_by_id), 404 before that guard runs. Neither
endpoint transitions the record's status — the INSPECTION -> FINAL_OFFER
move happens when acquisition posts the final offer via
offers.py::post_offer (Task 10); both endpoints here require the record to
already be in INSPECTION status, else 409.

No SQL lives here — every DB access goes through buyback.routes._shared's
singleton repos (RecordRepository, EventRepository) and
core.services.spaces_service for the PDF upload.
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from uuid import uuid4

from flask import request, jsonify
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback import lifecycle
from buyback.routes import _shared
from core.roles.decorators import v2_permission_required
from core.services import spaces_service

# inspection_rating is a 1-5 scale, stored in a SMALLINT column with NO
# DB-level CHECK constraint — an out-of-range or genuinely non-numeric value
# must be rejected here. A non-numeric value reaching the UPDATE would raise
# a psycopg2 error (NOT a ValueError), which the route has no `except` for,
# giving a raw 500 instead of a clean 400.
_RATING_MIN, _RATING_MAX = 1, 5

# 15MB cap on the service-report PDF, checked BEFORE the Spaces upload call.
MAX_REPORT_BYTES = 15 * 1024 * 1024


def _validate_rating(raw):
    """Coerce `raw` to an int in [_RATING_MIN, _RATING_MAX]. Returns
    (value, None) on success or (None, error_message) on failure — never
    raises, so the caller can turn a failure straight into a 400."""
    range_error = f'inspection_rating must be an integer between {_RATING_MIN} and {_RATING_MAX}'
    if isinstance(raw, bool):
        return None, range_error
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, float):
        if not raw.is_integer():
            return None, range_error
        value = int(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            value = int(raw.strip())
        except ValueError:
            return None, range_error
    else:
        return None, range_error
    if not (_RATING_MIN <= value <= _RATING_MAX):
        return None, range_error
    return value, None


# ═══════════════════════════════════════════════
# SAVE INSPECTION FIELDS
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/inspection', methods=['PUT'])
@login_required
@v2_permission_required('buyback', 'inspection', 'manage')
def update_inspection(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    if record['status'] != lifecycle.INSPECTION:
        return jsonify({
            'success': False,
            'error': f"Cannot save inspection on a record in status {record['status']!r} "
                     f"(only {lifecycle.INSPECTION!r} is inspectable)",
        }), 409

    data = request.get_json(silent=True) or {}

    # SECURITY: update_data is built field-by-field from a fixed, known set
    # of inspection columns — never from raw request JSON — mirroring
    # records.py::update_record's _CREATE_FIELDS whitelist reasoning:
    # RecordRepository.update()'s _UPDATABLE_COLUMNS guard is an
    # identifier-safety net, not an authorization boundary.
    update_data = {}

    rating_raw = data.get('inspection_rating')
    if rating_raw is not None:
        rating, error = _validate_rating(rating_raw)
        if error:
            return jsonify({'success': False, 'error': error}), 400
        update_data['inspection_rating'] = rating

    # reconditioning_cost_eur is a NUMERIC(12,2) column — a non-numeric
    # value would raise psycopg2.InvalidTextRepresentation (NOT a
    # ValueError) on the UPDATE, giving a 500. Validate Decimal-coercibility
    # up front, mirroring offers.py::post_offer's amount_eur check.
    cost_raw = data.get('reconditioning_cost_eur')
    if cost_raw is not None and not (isinstance(cost_raw, str) and not cost_raw.strip()):
        try:
            update_data['reconditioning_cost_eur'] = Decimal(str(cost_raw))
        except (InvalidOperation, ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'reconditioning_cost_eur must be a number',
            }), 400

    if data.get('inspection_notes') is not None:
        update_data['inspection_notes'] = data['inspection_notes']

    # Any call to this route represents inspector activity on the record —
    # always stamp who/when, even if the payload only touches one field.
    update_data['inspected_by'] = current_user.id
    update_data['inspected_at'] = datetime.now(timezone.utc)

    updated = _shared.records_repo.update(record_id, update_data)

    _shared.events_repo.log(
        record_id, 'inspection_updated', current_user.id,
        {
            'inspection_rating': update_data.get('inspection_rating'),
            'reconditioning_cost_eur': (
                float(update_data['reconditioning_cost_eur'])
                if 'reconditioning_cost_eur' in update_data else None
            ),
            'inspection_notes': update_data.get('inspection_notes'),
        },
    )

    return jsonify({'success': True, 'record': _shared._serialize(updated)})


# ═══════════════════════════════════════════════
# UPLOAD INSPECTION REPORT (PDF)
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/inspection/report', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'inspection', 'manage')
def upload_inspection_report(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    if record['status'] != lifecycle.INSPECTION:
        return jsonify({
            'success': False,
            'error': f"Cannot upload an inspection report on a record in status "
                     f"{record['status']!r} (only {lifecycle.INSPECTION!r} accepts a report)",
        }), 409

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    filename = (file.filename or '').lower()
    content_type = (file.mimetype or '').lower()
    if content_type != 'application/pdf' and not filename.endswith('.pdf'):
        return jsonify({'success': False, 'error': 'File must be a PDF'}), 400

    data = file.read()
    if not data:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    if len(data) > MAX_REPORT_BYTES:
        return jsonify({
            'success': False,
            'error': f'File too large (max {MAX_REPORT_BYTES // (1024 * 1024)} MB)',
        }), 400

    key = f'private/buyback/{record_id}/report-{uuid4().hex}.pdf'
    spaces_service.upload(data, key, 'application/pdf')

    updated = _shared.records_repo.update(record_id, {'inspection_report_key': key})

    _shared.events_repo.log(
        record_id, 'inspection_report_uploaded', current_user.id, {'key': key},
    )

    return jsonify({
        'success': True,
        'record': _shared._serialize(updated),
        'inspection_report_key': key,
    })
