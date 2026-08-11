"""Inter-company vehicle transfer routes — moves a vehicle to an AutoWorld
sibling company and logs the move (carpark_transfers).

No SQL lives here (per repo convention) — every route delegates to
TransferRepository (read: group companies) or DispoService.transfer
(write). The transfer's backing document is created here (reusing
DocumentRepository.create, mirroring documents.py's link/upload split)
BEFORE calling the service, so DispoService.transfer only ever receives an
already-persisted document_id — it never creates documents itself.

Exception mapping (mirrors dispo.py / documents.py's documented convention):
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
from carpark.repositories.transfer_repository import TransferRepository
from carpark.services.dispo_service import DispoService
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required,
    _serialize, _verify_vehicle_ownership, _user_company_id,
)
# Reused (not duplicated) — same Drive-upload plumbing and document-type
# whitelist as the general vehicle-documents route. Referenced via the
# module object (not `from ... import X`) so test monkeypatching of
# documents_mod.DRIVE_ENABLED / .upload_invoice_to_drive is honored here too.
import carpark.routes.documents as documents_mod

logger = logging.getLogger('jarvis.carpark')

_transfer_repo = TransferRepository()
_document_repo = DocumentRepository()
_dispo_service = DispoService()

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
_DEFAULT_DOCUMENT_TYPE = 'factura_transfer'


# ═══════════════════════════════════════════════
# TRANSFER — DESTINATION COMPANY PICKER
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/transfer-destinations', methods=['GET'])
@login_required
@carpark_required
def transfer_destinations():
    """AutoWorld sibling companies available as transfer destinations for
    the caller's own company (same group root, excluding itself) — feeds
    the frontend's Transfer action company picker."""
    company_id = _user_company_id()
    if not company_id:
        return jsonify({'companies': []})
    try:
        companies = _transfer_repo.group_companies(company_id)
        return jsonify({'companies': _serialize(companies)})
    except Exception as e:
        logger.error(f'Transfer destinations query failed (company_id={company_id}): {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# TRANSFER — MOVE + LOG
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/transfer', methods=['POST'])
@login_required
@carpark_edit_required
def transfer_vehicle(vehicle_id):
    """Transfer a vehicle to an AutoWorld sibling company: moves the
    vehicle row to the destination (fresh ACQUIRED intake) and logs a
    carpark_transfers row. See DispoService.transfer for the full guard
    list (AutoWorld-group destination, transfer_price > 0, a document).

    Body fields (JSON or multipart form): to_company_id (required),
    transfer_price (required), transfer_date?, transfer_currency?, notes?.

    Document (required, exactly one of):
      - multipart `file` field (+ optional document_type form field,
        defaults to 'factura_transfer') — only when Google Drive
        integration is enabled, mirroring documents.py's upload mode.
      - JSON document_file_url (http(s) URL) and/or dms_document_id.

    The cheap, document-independent guards (destination present + a valid
    AutoWorld-group sibling, price > 0) run BEFORE the document is created,
    so a rejected transfer never leaves an orphaned carpark_vehicle_documents
    row. DispoService.transfer re-validates all of them as defense-in-depth.
    """
    vehicle, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    uploaded_file = request.files.get('file') if request.files else None
    if uploaded_file:
        data = request.form.to_dict()
    else:
        data = request.get_json(silent=True) or {}

    # Validate BEFORE creating the document — otherwise an invalid transfer
    # (missing/zero price, non-group destination) would still persist a
    # dangling carpark_vehicle_documents row on the vehicle.
    val_err = _validate_transfer_request(data, _user_company_id())
    if val_err:
        return val_err

    if uploaded_file:
        document, doc_err = _create_transfer_document_via_upload(vehicle_id, vehicle, uploaded_file, data)
    else:
        document, doc_err = _create_transfer_document_via_link(vehicle_id, data)
    if doc_err:
        return doc_err

    try:
        payload = dict(data)
        payload['document_id'] = document['id']
        result = _dispo_service.transfer(vehicle_id, _user_company_id(), current_user, payload)
        return jsonify(_serialize(result))
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Transfer failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


def _validate_transfer_request(data, source_company_id):
    """Cheap, document-independent transfer guards, run BEFORE the transfer
    document is created so an invalid request leaves no orphaned
    carpark_vehicle_documents row. Mirrors DispoService.transfer's own
    guards (which still re-run as defense-in-depth) with the SAME RO
    messages. Returns an error response tuple, or None when valid.

    Calls TransferRepository.group_company_ids from the route — that's a
    repo method, not inline SQL, so the no-SQL-in-routes rule holds. The
    document-dependency guard (document_id required) is intentionally NOT
    here: the document doesn't exist yet at this point and is guaranteed by
    the route creating it next, then re-checked by the service."""
    to_company_id = data.get('to_company_id')
    if not to_company_id:
        return jsonify({'error': 'to_company_id is required'}), 400
    try:
        to_company_id = int(to_company_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'to_company_id must be a valid company id'}), 400

    transfer_price = data.get('transfer_price')
    try:
        price_ok = (transfer_price is not None and str(transfer_price).strip() != ''
                    and float(transfer_price) > 0)
    except (TypeError, ValueError):
        price_ok = False
    if not price_ok:
        return jsonify({'error': 'transfer_price is required and must be greater than 0'}), 400

    group_ids = _transfer_repo.group_company_ids(source_company_id)
    if to_company_id == source_company_id or to_company_id not in group_ids:
        return jsonify({'error': 'Transfer permis doar între companiile AutoWorld'}), 400

    return None


def _create_transfer_document_via_link(vehicle_id, data):
    """LINK MODE: {document_file_url|file_url, dms_document_id?,
    document_type?, document_title?}. Requires file_url or dms_document_id.
    Same http(s)-only guard as documents.py's _create_via_link (defense in
    depth against stored XSS — file_url is echoed back and rendered as an
    <a href>)."""
    file_url = data.get('document_file_url') or data.get('file_url')
    dms_document_id = data.get('dms_document_id')
    if not file_url and not dms_document_id:
        return None, (jsonify({
            'error': 'Documentul de transfer este obligatoriu '
                     '(document_file_url sau dms_document_id, sau un fișier multipart)'
        }), 400)
    if file_url and not str(file_url).strip().lower().startswith(('http://', 'https://')):
        return None, (jsonify({'error': 'document_file_url invalid: only http(s) URLs allowed'}), 400)

    document_type = data.get('document_type') or _DEFAULT_DOCUMENT_TYPE
    if document_type not in documents_mod.VALID_DOCUMENT_TYPES:
        return None, (jsonify({'error': f'Invalid document_type: {document_type}'}), 400)

    payload = {
        'document_type': document_type,
        'file_url': file_url,
        'dms_document_id': dms_document_id,
        'title': data.get('document_title') or 'Factură transfer',
        'notes': data.get('notes'),
        'uploaded_by': current_user.id,
    }
    try:
        document = _document_repo.create(vehicle_id, payload)
        return document, None
    except ValueError as e:
        return None, (jsonify({'error': str(e)}), 400)
    except Exception as e:
        logger.error(f'Transfer document link-create failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return None, (jsonify({'error': 'Internal error'}), 500)


def _create_transfer_document_via_upload(vehicle_id, vehicle, uploaded_file, form_data):
    """UPLOAD MODE: multipart `file` + optional document_type/document_title
    form fields. Only available when Google Drive integration is enabled;
    otherwise 400s with instructions to fall back to link mode, mirroring
    documents.py's own upload-mode gate."""
    if not documents_mod.DRIVE_ENABLED:
        return None, (jsonify({
            'error': 'File upload is unavailable (Google Drive integration is disabled '
                     'on this server). Submit the document via document_file_url in a '
                     'JSON body instead.'
        }), 400)

    document_type = form_data.get('document_type') or _DEFAULT_DOCUMENT_TYPE
    if document_type not in documents_mod.VALID_DOCUMENT_TYPES:
        return None, (jsonify({'error': f'Invalid document_type: {document_type}'}), 400)

    file_bytes = uploaded_file.read()
    if not file_bytes:
        return None, (jsonify({'error': 'Uploaded file is empty'}), 400)
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        return None, (jsonify({'error': 'File exceeds the 10MB upload limit'}), 400)

    try:
        drive_link = documents_mod.upload_invoice_to_drive(
            file_bytes,
            uploaded_file.filename or f'transfer_{vehicle_id}',
            invoice_date=date.today().isoformat(),
            company=vehicle.get('brand') or 'CarPark',
            invoice_number=vehicle.get('vin') or str(vehicle_id),
            mime_type=uploaded_file.content_type or 'application/octet-stream',
        )
    except Exception as e:
        logger.error(f'Transfer document Drive upload failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return None, (jsonify({'error': 'File upload failed'}), 500)

    payload = {
        'document_type': document_type,
        'file_url': drive_link,
        'title': form_data.get('document_title') or 'Factură transfer',
        'mime_type': uploaded_file.content_type,
        'file_size': len(file_bytes),
        'uploaded_by': current_user.id,
    }
    try:
        document = _document_repo.create(vehicle_id, payload)
        return document, None
    except ValueError as e:
        return None, (jsonify({'error': str(e)}), 400)
    except Exception as e:
        logger.error(f'Transfer document upload-create failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return None, (jsonify({'error': 'Internal error'}), 500)
