"""Sale-document API routes — generate/preview/save contract, proforma, and
warranty (`garantie`) PDFs for a vehicle, plus the leasing-companies
directory (Task 1) used to populate the sale form's "Cumparator" picker.

No SQL and no rendering logic lives here — every route delegates to the
`carpark.services.sale_docs` facade (fetch + context build + render
dispatch) or to a repository. Mirrors `documents.py`'s conventions:
guarded Drive import, ownership check via `_verify_vehicle_ownership`, and
the same exception -> HTTP mapping.

Exception mapping (mirrors documents.py / dispo.py / reservations.py):
  PermissionError -> 403 (cross-tenant vehicle / guard failure)
  ValueError      -> 400 (validation / missing-field failure)
  anything else   -> 500 (logged)
"""
import logging
from datetime import date
from io import BytesIO

from flask import request, jsonify, send_file
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.routes.vehicles import carpark_edit_required, _verify_vehicle_ownership, _serialize
from carpark.repositories.leasing_company_repository import LeasingCompanyRepository
from carpark.repositories.document_repository import DocumentRepository
from carpark.services.sale_docs import generate as generate_sale_document
from core.auth.repositories.user_repository import UserRepository

# Google Drive integration (optional — mirrors documents.py's guarded
# import so this module still loads when the Drive packages/creds aren't
# configured; the save route simply 400s instead).
try:
    from core.services.drive_service import upload_invoice_to_drive
    DRIVE_ENABLED = True
except ImportError:
    DRIVE_ENABLED = False
    upload_invoice_to_drive = None

logger = logging.getLogger('jarvis.carpark')

# doc_type (facade / form) -> document_type (carpark_vehicle_documents row),
# per the plan's mapping.
_DOCUMENT_TYPE_MAP = {
    'contract': 'contract_vanzare',
    'proforma': 'factura_vanzare',
    'garantie': 'garantie',
}


def _resolve_consultant_name(vehicle, form):
    """Resolve the sales-consultant name (design D3) for the token context:
    prefer the vehicle's assigned salesperson (`salesperson_user_id` ->
    `users.name`), fall back to the requesting user's own name when the
    vehicle has none assigned."""
    consultant = None
    sp_id = vehicle.get('salesperson_user_id')
    if sp_id:
        u = UserRepository().get_by_id(sp_id)
        consultant = (u or {}).get('name')
    if not consultant:
        consultant = getattr(current_user, 'name', None)
    return consultant


def _request_form(vehicle):
    """Extract {doc_type, form} from the JSON body and inject the resolved
    consultant name into `form`, mutating nothing request-scoped past this
    function so the facade stays request-agnostic."""
    body = request.get_json(silent=True) or {}
    doc_type = body.get('doc_type')
    form = dict(body.get('form') or {})
    form['consultant_name'] = _resolve_consultant_name(vehicle, form)
    return doc_type, form


# ═══════════════════════════════════════════════
# SALE DOCUMENTS — GENERATE (preview / download, not saved)
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/sale-documents/generate', methods=['POST'])
@login_required
@carpark_edit_required
def generate_sale_document_route(vehicle_id):
    """Render a sale document and stream the PDF bytes back — nothing is
    persisted (no Drive upload, no document row). Body: {doc_type, form}."""
    vehicle, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    doc_type, form = _request_form(vehicle)

    try:
        pdf_bytes, filename = generate_sale_document(vehicle_id, doc_type, form)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        logger.error(f'Sale document generate failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


# ═══════════════════════════════════════════════
# SALE DOCUMENTS — SAVE (render + upload to Drive + record document row)
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/sale-documents/save', methods=['POST'])
@login_required
@carpark_edit_required
def save_sale_document_route(vehicle_id):
    """Render a sale document, upload it to Google Drive, and record it as a
    vehicle document. Body: {doc_type, form}. 400s if Drive integration is
    disabled on this server (same guard as documents.py's upload mode)."""
    vehicle, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    if not DRIVE_ENABLED:
        return jsonify({
            'error': 'Google Drive integration is disabled on this server. '
                     'Sale documents cannot be saved.'
        }), 400

    doc_type, form = _request_form(vehicle)

    try:
        pdf_bytes, filename = generate_sale_document(vehicle_id, doc_type, form)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        logger.error(f'Sale document save failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

    try:
        link = upload_invoice_to_drive(
            pdf_bytes,
            filename,
            invoice_date=date.today().isoformat(),
            company=vehicle.get('brand') or 'CarPark',
            invoice_number=vehicle.get('vin') or str(vehicle_id),
            mime_type='application/pdf',
        )
        document = DocumentRepository().create(vehicle_id, {
            'document_type': _DOCUMENT_TYPE_MAP.get(doc_type, doc_type),
            'file_url': link,
            'title': filename,
            'mime_type': 'application/pdf',
            'uploaded_by': current_user.id,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        logger.error(f'Sale document save failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

    return jsonify({'document': _serialize(document)}), 201


# ═══════════════════════════════════════════════
# LEASING COMPANIES — directory (Task 1)
# ═══════════════════════════════════════════════

@carpark_bp.route('/leasing-companies', methods=['GET'])
@login_required
@carpark_edit_required
def list_leasing_companies():
    """The global leasing-companies directory, for the sale form's
    Cumparator picker."""
    try:
        companies = LeasingCompanyRepository().list_all()
        return jsonify({'leasing_companies': _serialize(companies)})
    except Exception as e:
        logger.error(f'List leasing companies failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


@carpark_bp.route('/leasing-companies', methods=['POST'])
@login_required
@carpark_edit_required
def create_leasing_company():
    """Add a leasing company to the global directory. Body: leasing fields
    (name required)."""
    data = request.get_json(silent=True) or {}
    try:
        leasing_company = LeasingCompanyRepository().create(data, created_by=current_user.id)
        return jsonify({'leasing_company': _serialize(leasing_company)}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Create leasing company failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500
