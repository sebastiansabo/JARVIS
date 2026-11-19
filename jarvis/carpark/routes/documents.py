"""Document API routes — link/upload, delete, checklist, timeline,
invoice->cost (parse-invoice, transfer-to-cost).

No SQL lives here (per repo convention) — every route delegates to
DocumentRepository, DispoRepository (timeline), DispoService (checklist), or
VehicleService (invoice->cost transfer).

Two input modes for POST /vehicles/<id>/documents:
  - LINK MODE (primary, always available): JSON body with file_url and/or
    dms_document_id — the caller already has the file hosted somewhere
    (DMS, another upload flow, ...) and just wants it recorded.
  - UPLOAD MODE (best-effort, multipart with a `file` part): only works
    when Google Drive integration is enabled (see the guarded import
    below, mirroring core/drive/routes.py). When Drive is unavailable, the
    route 400s with a message telling the caller to fall back to link mode
    instead of silently losing the upload.

Tenant note (carried forward from DispoService's module docstring):
DocumentRepository has no company_id column of its own, so DELETE
/documents/<doc_id> must load the document, resolve its vehicle_id, and
run it through _verify_vehicle_ownership before deleting — otherwise a
caller could delete another company's document by guessing an id.

Exception mapping (mirrors dispo.py / reservations.py's documented
convention):
  PermissionError -> 403 (cross-tenant vehicle)
  ValueError      -> 400 (validation / guard failure)
  anything else   -> 500 (logged)

transfer-to-cost is the one exception: ValueError('already transferred')
(the dedup pre-check in VehicleService.transfer_document_to_cost) maps to
409 instead of 400 — it's a conflict with existing state, not a bad
request. parse-invoice never raises past the route at all: any fetch/parse
failure degrades to {'cost_prefill': None} with HTTP 200 (see its
docstring).
"""
import logging
from datetime import date

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.repositories.document_repository import DocumentRepository
from carpark.services.photo_urls import public_photo_url
from carpark.services.vehicle_service import VehicleService
from carpark.services.invoice_cost_mapper import map_parsed_invoice_to_cost
from carpark.services.document_fetch import fetch_document_bytes
from carpark.repositories.dispo_repository import DispoRepository
from carpark.services.dispo_service import DispoService
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required, carpark_delete_required,
    carpark_finance_edit_required,
    _serialize, _verify_vehicle_ownership, _user_company_id,
)
from carpark.routes.costs import VALID_COST_TYPES

logger = logging.getLogger('jarvis.carpark')

# Google Drive integration (optional — mirrors core/drive/routes.py's
# guarded import so this module still loads when the Drive packages/creds
# aren't configured; upload mode simply 400s instead).
try:
    from core.services.drive_service import (
        upload_invoice_to_drive, upload_attachment_to_folder,
        get_folder_id_from_file_link,
    )
    DRIVE_ENABLED = True
except ImportError:
    DRIVE_ENABLED = False
    upload_invoice_to_drive = None
    upload_attachment_to_folder = None
    get_folder_id_from_file_link = None

_document_repo = DocumentRepository()
_dispo_repo = DispoRepository()
_dispo_service = DispoService()
_service = VehicleService()

# Known document types (matches the CarPark Dispo document checklist —
# see DispoService.REQUIRED_DOCS for the subset that's actually
# required/blocking; this is the full set a document may be tagged with).
VALID_DOCUMENT_TYPES = frozenset({
    'pv_intrare', 'contract_achizitie', 'civ', 'talon', 'factura_achizitie',
    'contract_vanzare', 'factura_vanzare', 'pv_livrare', 'dosar_gw',
    'asigurare', 'itp', 'mandat', 'altele',
    # Inter-company transfer (carpark/routes/transfers.py) — the invoice
    # backing a transfer between AutoWorld sibling companies.
    'factura_transfer',
    # Sale-documents module (carpark/routes/sale_documents.py) — the
    # commercial warranty certificate generated/saved for a sold vehicle.
    'garantie',
})

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

# Document types that carry an invoice body eligible for the parse-invoice /
# transfer-to-cost flow below (Task 5 of the invoice->cost feature) — the
# three invoice-shaped entries already present in VALID_DOCUMENT_TYPES above.
INVOICE_DOCUMENT_TYPES = frozenset({
    'factura_achizitie', 'factura_vanzare', 'factura_transfer',
})


def is_invoice_document_type(document_type: str) -> bool:
    """True if `document_type` is one of the invoice-shaped document types
    eligible for parse-invoice / transfer-to-cost."""
    return document_type in INVOICE_DOCUMENT_TYPES


# ═══════════════════════════════════════════════
# DOCUMENTS — LIST
# ═══════════════════════════════════════════════

def _with_openable_urls(documents):
    """Presign any private Spaces key stored in `file_url` into a time-limited
    GET URL so the document is openable in the UI. Documents carried from
    BuyBack on hand-off store a private key (private/carpark/<veh>/doc-...);
    native uploads store an http(s) Drive link, which passes through unchanged
    (as do data: URIs and empty values)."""
    out = []
    for d in documents:
        d = dict(d)
        if d.get('file_url'):
            d['file_url'] = public_photo_url(d['file_url'])
        out.append(d)
    return out


@carpark_bp.route('/vehicles/<int:vehicle_id>/documents', methods=['GET'])
@login_required
@carpark_required
def list_vehicle_documents(vehicle_id):
    """All documents uploaded for a vehicle, most recently uploaded first."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    try:
        documents = _document_repo.list_for_vehicle(vehicle_id)
        return jsonify({'documents': _serialize(_with_openable_urls(documents))})
    except Exception as e:
        logger.error(f'List documents failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# DOCUMENTS — CREATE (link or upload)
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/documents', methods=['POST'])
@login_required
@carpark_edit_required
def create_vehicle_document(vehicle_id):
    """Record a document for a vehicle.

    LINK MODE (JSON body, no file): {document_type, file_url?,
    dms_document_id?, title?, mime_type?, file_size?} — at least one of
    file_url/dms_document_id is required.

    UPLOAD MODE (multipart form with a `file` part): {document_type,
    title?} as form fields, plus the file itself. Only available when
    Google Drive integration is enabled; otherwise returns 400 with
    instructions to use link mode.
    """
    vehicle, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    uploaded_file = request.files.get('file') if request.files else None
    if uploaded_file:
        return _create_via_upload(vehicle_id, vehicle, uploaded_file)

    data = request.get_json(silent=True) or {}
    return _create_via_link(vehicle_id, data)


def _validate_document_type(document_type):
    """Returns an error response tuple if document_type is missing/invalid,
    else None."""
    if not document_type:
        return jsonify({'error': 'document_type is required'}), 400
    if document_type not in VALID_DOCUMENT_TYPES:
        return jsonify({
            'error': f'Invalid document_type: {document_type}. '
                     f'Must be one of: {", ".join(sorted(VALID_DOCUMENT_TYPES))}'
        }), 400
    return None


def _create_via_link(vehicle_id, data):
    document_type = data.get('document_type')
    type_err = _validate_document_type(document_type)
    if type_err:
        return type_err

    file_url = data.get('file_url')
    if not file_url and not data.get('dms_document_id'):
        return jsonify({'error': 'file_url or dms_document_id is required'}), 400

    # Defense in depth against stored XSS: file_url is echoed back to the
    # UI and rendered as an <a href>, so only accept http(s) absolute URLs
    # and reject anything else (javascript:, data:, ...) at ingest.
    if file_url and not str(file_url).strip().lower().startswith(('http://', 'https://')):
        return jsonify({'error': 'file_url invalid: only http(s) URLs allowed'}), 400

    payload = {
        'document_type': document_type,
        'file_url': file_url,
        'dms_document_id': data.get('dms_document_id'),
        'title': data.get('title'),
        'mime_type': data.get('mime_type'),
        'file_size': data.get('file_size'),
        'notes': data.get('notes'),
        'uploaded_by': current_user.id,
    }
    try:
        document = _document_repo.create(vehicle_id, payload)
        return jsonify({'document': _serialize(document)}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Document link-create failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


def _create_via_upload(vehicle_id, vehicle, uploaded_file):
    if not DRIVE_ENABLED:
        return jsonify({
            'error': 'File upload is unavailable (Google Drive integration is disabled '
                     'on this server). Upload the file elsewhere and submit it via '
                     'file_url in a JSON body instead.'
        }), 400

    document_type = request.form.get('document_type')
    type_err = _validate_document_type(document_type)
    if type_err:
        return type_err

    file_bytes = uploaded_file.read()
    if not file_bytes:
        return jsonify({'error': 'Uploaded file is empty'}), 400
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        return jsonify({'error': 'File exceeds the 10MB upload limit'}), 400

    try:
        drive_link = upload_invoice_to_drive(
            file_bytes,
            uploaded_file.filename or f'document_{vehicle_id}',
            invoice_date=date.today().isoformat(),
            company=vehicle.get('brand') or 'CarPark',
            invoice_number=vehicle.get('vin') or str(vehicle_id),
            mime_type=uploaded_file.content_type or 'application/octet-stream',
        )
    except Exception as e:
        logger.error(f'Drive upload failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'File upload failed'}), 500

    payload = {
        'document_type': document_type,
        'file_url': drive_link,
        'title': request.form.get('title'),
        'mime_type': uploaded_file.content_type,
        'file_size': len(file_bytes),
        'uploaded_by': current_user.id,
    }
    try:
        document = _document_repo.create(vehicle_id, payload)
        return jsonify({'document': _serialize(document)}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Document upload-create failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# DOCUMENTS — DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@login_required
@carpark_delete_required
def delete_document(doc_id):
    """Delete a single document. TENANT GUARD: DocumentRepository has no
    company_id of its own, so ownership is enforced by loading the
    document, resolving its vehicle, and running that vehicle through
    _verify_vehicle_ownership before the delete — a cross-company doc_id
    404s exactly like an unknown one."""
    try:
        document = _document_repo.get(doc_id)
    except Exception as e:
        logger.error(f'Document lookup failed for doc {doc_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

    if not document:
        return jsonify({'error': 'Document not found'}), 404

    _, err = _verify_vehicle_ownership(document['vehicle_id'])
    if err:
        # Cross-tenant doc: surface the same 404 a caller would get for an
        # unknown id, so a guessed doc_id can't be used to probe for
        # another company's documents.
        return jsonify({'error': 'Document not found'}), 404

    try:
        deleted = _document_repo.delete(doc_id)
    except Exception as e:
        logger.error(f'Document delete failed for doc {doc_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

    if not deleted:
        return jsonify({'error': 'Document not found'}), 404
    return jsonify({'success': True})


# ═══════════════════════════════════════════════
# DOCUMENTS — INVOICE → COST (parse-invoice, transfer-to-cost)
# ═══════════════════════════════════════════════

def _load_invoice_document(vehicle_id, doc_id):
    """Shared lookup+guard for parse-invoice/transfer-to-cost: loads the
    document and checks it belongs to this vehicle and is an invoice-shaped
    type. Returns (document, None) on success, or (None, error_response)
    where error_response is a ready-to-return (body, status) tuple — 404 for
    missing/cross-vehicle (same oracle-avoidance pattern as delete_document
    above: a cross-tenant doc_id 404s exactly like an unknown one), 400 for
    a non-invoice document_type."""
    try:
        document = _document_repo.get(doc_id)
    except Exception as e:
        logger.error(f'Document lookup failed for doc {doc_id}: {e}', exc_info=True)
        return None, (jsonify({'error': 'Internal error'}), 500)

    if not document or document.get('vehicle_id') != vehicle_id:
        return None, (jsonify({'error': 'Document not found'}), 404)

    if not is_invoice_document_type(document.get('document_type')):
        return None, (jsonify({'error': 'Document is not an invoice type'}), 400)

    return document, None


@carpark_bp.route('/vehicles/<int:vehicle_id>/documents/<int:doc_id>/parse-invoice', methods=['POST'])
@login_required
@carpark_finance_edit_required
def parse_invoice_document(vehicle_id, doc_id):
    """Best-effort parse of an uploaded invoice document into cost-prefill
    fields for the create-cost dialog. NO persistence happens here — see
    transfer_document_to_cost_route below for that.

    Always returns HTTP 200: any failure fetching or parsing the file (an
    un-fetchable/DMS-only document, a non-PDF/image the AI parser can't
    read, the invoice_parser module itself unavailable, ...) degrades to
    {'cost_prefill': None, 'reason': '...'} so the UI falls back to a blank
    cost dialog instead of being blocked by a 500. This carries forward
    document_fetch's documented residual TOCTOU/DNS-rebind gap unresolved —
    not this route's job to close it, hence best-effort rather than a hard
    failure."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    document, err = _load_invoice_document(vehicle_id, doc_id)
    if err:
        return err

    try:
        file_bytes, filename = fetch_document_bytes(document)
        # Lazy import: accounting.bugetare.invoice_parser pulls in the AI
        # client + poppler at import time, which we don't want paid at
        # blueprint-registration time and which may simply be unavailable
        # on some deployments — either way it degrades to cost_prefill=None.
        from accounting.bugetare.invoice_parser import parse_invoice_from_bytes
        parsed = parse_invoice_from_bytes(file_bytes, filename)
        cost_prefill = map_parsed_invoice_to_cost(parsed)
        return jsonify({'cost_prefill': cost_prefill}), 200
    except Exception as e:
        # error-level + traceback (not warning): this catch-all deliberately
        # swallows genuine parser/mapper bugs into a 200 cost_prefill:null, so
        # a real regression must still be visible with a stack trace rather
        # than shipping silently below error-level alerting. Response contract
        # is unchanged — the UI still falls back to a blank dialog. The
        # client-facing `reason` is intentionally generic (not str(e)): the
        # raw exception text could leak internal details (file paths, DMS/
        # Drive URLs, parser/AI-client internals) to whoever can view this
        # vehicle's documents — the full exception stays server-side via
        # exc_info=True above.
        logger.error(f'Invoice parse failed for doc {doc_id} (vehicle {vehicle_id}): {e}', exc_info=True)
        return jsonify({'cost_prefill': None, 'reason': 'could not read invoice automatically'}), 200


@carpark_bp.route('/vehicles/<int:vehicle_id>/documents/<int:doc_id>/transfer-to-cost', methods=['POST'])
@login_required
@carpark_finance_edit_required
def transfer_document_to_cost_route(vehicle_id, doc_id):
    """Persist the user-confirmed cost fields (typically parse-invoice's
    prefill, edited) as a cost entry linked back to this document via
    source_document_id. Delegates the find-or-create-cost-line + dedup +
    insert to VehicleService.transfer_document_to_cost (Task 4)."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    _, err = _load_invoice_document(vehicle_id, doc_id)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    if data.get('cost_type') and data['cost_type'] not in VALID_COST_TYPES:
        return jsonify({
            'error': f'Invalid cost_type. Allowed: {", ".join(sorted(VALID_COST_TYPES))}'
        }), 400

    try:
        cost = _service.transfer_document_to_cost(vehicle_id, doc_id, data, created_by=current_user.id)
        return jsonify({'cost': _serialize(cost)}), 201
    except ValueError as e:
        if str(e) == 'already transferred':
            return jsonify({'error': 'already transferred'}), 409
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Transfer-to-cost failed for doc {doc_id} (vehicle {vehicle_id}): {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# DOCUMENTS — CHECKLIST
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/documents/checklist', methods=['GET'])
@login_required
@carpark_required
def vehicle_documents_checklist(vehicle_id):
    """Required-document checklist for a vehicle. Delegates entirely to
    DispoService.checklist (see its docstring for the required/present/
    missing/blocks_delivery shape)."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    try:
        result = _dispo_service.checklist(vehicle_id, _user_company_id())
        return jsonify(_serialize(result))
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Checklist failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# VEHICLE — TIMELINE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/timeline', methods=['GET'])
@login_required
@carpark_required
def vehicle_timeline(vehicle_id):
    """Merged, chronologically-sorted event history for a vehicle (status
    transitions, key lifecycle dates, document uploads). Assembly happens
    entirely in DispoRepository.timeline — this route just delegates."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    try:
        events = _dispo_repo.timeline(vehicle_id)
        return jsonify({'timeline': _serialize(events)})
    except Exception as e:
        logger.error(f'Timeline failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500
