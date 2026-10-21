"""Per-record contract routes — generate, inline-edit, and regenerate the
BuyBack purchase/consignation contract.

- GET  /records/<id>/contract          -> the editable draft (stored text, or
                                          a fresh template substitution preview)
- POST /records/<id>/contract          -> write: generate-from-data | save a
                                          manual edit | regenerate-from-data
- POST /records/<id>/generate-contract -> legacy alias (= POST with from_data)

The contract text (title/body/general_conditions) lives on buyback_records
(P3c) so the advisor can edit it per-record; the PDF is re-rendered from that
final text via render_contract_pdf_from_parts. `from_data` (or a first
generate with no stored body) instead substitutes the active template against
the record's current client/car data — discarding manual edits.

No SQL lives here — every DB access goes through _shared's singleton repos,
ContractTemplateRepository, and CompanyRepository.

MANUAL trigger, not a lifecycle gate: never 500 on sparse data. The only
non-2xx outcomes are 404 (no record), 403 (_guard_company IDOR), and 409 (no
active template for this company/brand/document_type when one is required).
"""
import logging
from datetime import date

from flask import request, jsonify
from flask_login import login_required

from buyback import buyback_bp
from buyback.routes import _shared
from buyback.repositories.contract_template_repository import ContractTemplateRepository
from buyback.services.contract_pdf import build_contract_context, render_contract_pdf_from_parts
from buyback.services.contract_template import render_contract_template
from core.organization.repositories.company_repository import CompanyRepository
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.buyback')

_template_repo = ContractTemplateRepository()
_company_repo = CompanyRepository()

_DOC_TYPES = ('purchase', 'consignment')
_CONSIGNMENT_STATUSES = ('CONSIGNMENT_OFFER', 'CONSIGNAT')


def _resolve_document_type(data, record):
    """Explicit `document_type` wins when recognized; else infer from status."""
    requested = (data or {}).get('document_type')
    if requested in _DOC_TYPES:
        return requested
    return 'consignment' if record.get('status') in _CONSIGNMENT_STATUSES else 'purchase'


def _accepted_offer(record_id, document_type):
    """The accepted offer matching the document type (consignment↔consignment,
    else the 'final' purchase offer), or None."""
    wanted = 'consignment' if document_type == 'consignment' else 'final'
    offers = _shared.offers_repo.list_for_record(record_id)
    return next(
        (o for o in offers
         if o.get('offer_type') == wanted and o.get('client_decision') == 'accepted'),
        None,
    )


def _consignment_agreement(record):
    """The consignment agreement for this record's CarPark vehicle, if any
    (mirrors records.py's local-import lookup; only exists once handed off)."""
    if not record.get('carpark_vehicle_id'):
        return None
    from carpark.repositories.consignment_repository import ConsignmentRepository
    return ConsignmentRepository().get_by_vehicle(record['carpark_vehicle_id'])


def _build_warnings(context):
    """Non-blocking hints about gaps baked into the rendered contract."""
    warnings = []
    if not context.get('price_eur'):
        warnings.append('Nicio ofertă acceptată — preț necompletat')
    if not context.get('seller_name'):
        warnings.append('Lipsesc datele vânzătorului')
    return warnings


def _signatory_for(record):
    """Dealer signature-line name (company administrator, else company name)."""
    company = _company_repo.get(record['company_id']) or {}
    return company.get('administrator') or company.get('company') or ''


def _substitute_from_template(record, template, document_type):
    """Resolve the token context from the record's current data and substitute
    the template -> (title, body, general_conditions, signatory, warnings)."""
    company = _company_repo.get(record['company_id'])
    offer = _accepted_offer(record['id'], document_type)
    consignment = _consignment_agreement(record)
    context = build_contract_context(
        record, company, offer=offer, consignment=consignment,
        contract_number=record.get('record_code') or '',
        contract_date=date.today().isoformat(),
    )
    title = render_contract_template(template.get('title') or '', context)
    body = render_contract_template(template.get('body_template') or '', context)
    gc = render_contract_template(template.get('general_conditions') or '', context)
    signatory = context.get('company_administrator') or context.get('company_name') or ''
    return title, body, gc, signatory, _build_warnings(context)


def _contract_download_url(record_id):
    """download_url of the record's current stored contract document, or None."""
    photos = _shared.photos_repo.get_by_record(record_id)
    contract = next((p for p in photos if p.get('photo_type') == 'contract'), None)
    if not contract:
        return None
    return _shared.serialize_photos([contract])[0].get('download_url')


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _draft(record, document_type, *, has_template, download_url, warnings):
    """The editable-draft payload, read from the record's stored contract text."""
    return {
        'has_template': has_template,
        'has_contract': bool(record.get('contract_body')),
        'document_type': document_type,
        'title': record.get('contract_title') or '',
        'body': record.get('contract_body') or '',
        'general_conditions': record.get('contract_general_conditions') or '',
        'generated_at': _iso(record.get('contract_generated_at')),
        'download_url': download_url,
        'warnings': warnings,
    }


def _load_guarded(record_id):
    """(record, None) or (None, response) — 404 then IDOR guard, in that order."""
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return None, (jsonify({'success': False, 'error': 'Record not found'}), 404)
    err = _shared._guard_company(record)
    if err:
        return None, err
    return record, None


@buyback_bp.route('/records/<int:record_id>/contract', methods=['GET'])
@login_required
@v2_permission_required('buyback', 'record', 'view')
def get_contract(record_id):
    record, err = _load_guarded(record_id)
    if err:
        return err
    document_type = _resolve_document_type(request.args, record)
    template = _template_repo.get_active_with_default(
        record['company_id'], record['brand_id'], document_type)

    if record.get('contract_body'):
        return jsonify(_draft(
            record, document_type, has_template=template is not None,
            download_url=_contract_download_url(record_id), warnings=[])), 200

    # No stored contract yet: offer a fresh substitution preview to edit.
    if template is None:
        return jsonify({
            'has_template': False, 'has_contract': False, 'document_type': document_type,
            'title': '', 'body': '', 'general_conditions': '',
            'generated_at': None, 'download_url': None, 'warnings': [],
        }), 200
    title, body, gc, _signatory, warnings = _substitute_from_template(record, template, document_type)
    return jsonify({
        'has_template': True, 'has_contract': False, 'document_type': document_type,
        'title': title, 'body': body, 'general_conditions': gc,
        'generated_at': None, 'download_url': None, 'warnings': warnings,
    }), 200


def _write_contract(record_id, data):
    """Shared handler for POST /contract and the generate-contract alias."""
    record, err = _load_guarded(record_id)
    if err:
        return err
    document_type = _resolve_document_type(data, record)
    from_data = bool(data.get('from_data'))
    provided_body = data.get('body')
    # Rebuild from the template when asked (from_data) or on a first generate
    # with nothing posted and nothing stored; otherwise honour the manual edit.
    use_template = from_data or (provided_body is None and not record.get('contract_body'))

    warnings = []
    if use_template:
        template = _template_repo.get_active_with_default(
            record['company_id'], record['brand_id'], document_type)
        if template is None:
            return jsonify({
                'error': 'Nu există un model de contract activ pentru acest brand/companie.'
            }), 409
        title, body, gc, signatory, warnings = _substitute_from_template(record, template, document_type)
    else:
        title = (data.get('title') if 'title' in data else record.get('contract_title')) or ''
        body = provided_body if provided_body is not None else (record.get('contract_body') or '')
        gc = (data.get('general_conditions') if 'general_conditions' in data
              else record.get('contract_general_conditions')) or ''
        signatory = _signatory_for(record)

    # contract_title is VARCHAR(300) — clamp so an over-long title (e.g. a
    # paste, or an API client bypassing the form's maxLength) can't 500 the
    # store. Body/general_conditions are TEXT (unbounded).
    title = (title or '')[:300]

    pdf_bytes = render_contract_pdf_from_parts(title, body, gc, signatory=signatory)
    updated = _shared.records_repo.update_contract(record_id, title, body, gc)
    photo = _shared.photos_repo.store_contract_pdf(
        record_id, pdf_bytes, caption=title or 'Contract')
    serialized = _shared.serialize_photos([photo])[0]

    return jsonify({
        'photo': serialized,
        'draft': _draft(
            updated, document_type, has_template=True,
            download_url=serialized.get('download_url'), warnings=warnings),
        'warnings': warnings,
    }), 200


@buyback_bp.route('/records/<int:record_id>/contract', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def write_contract(record_id):
    return _write_contract(record_id, request.get_json(silent=True) or {})


@buyback_bp.route('/records/<int:record_id>/generate-contract', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def generate_contract(record_id):
    """Legacy alias — a first generate substitutes from the active template."""
    data = request.get_json(silent=True) or {}
    data.setdefault('from_data', True)
    return _write_contract(record_id, data)
