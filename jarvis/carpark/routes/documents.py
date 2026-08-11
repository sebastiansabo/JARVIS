"""Document API routes — link/upload, delete, checklist, timeline.

No SQL lives here (per repo convention) — every route delegates to
DocumentRepository, DispoRepository (timeline), or DispoService (checklist).

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
"""
import logging
from datetime import date

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.repositories.document_repository import DocumentRepository
from carpark.repositories.dispo_repository import DispoRepository
from carpark.services.dispo_service import DispoService
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required, carpark_delete_required,
    _serialize, _verify_vehicle_ownership, _user_company_id,
)

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
})

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


# ═══════════════════════════════════════════════
# DOCUMENTS — LIST
# ═══════════════════════════════════════════════

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
        return jsonify({'documents': _serialize(documents)})
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
