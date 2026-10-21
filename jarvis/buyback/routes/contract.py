"""Manual "generate contract" route — the Task 6 integration point tying
together the P3b contract-PDF pipeline built in earlier tasks:
build_contract_context (Task 3) + render_contract_pdf (Task 4) +
PhotoRepository.store_contract_pdf (Task 5), behind one POST endpoint a user
triggers from the record detail page before a contract is signed.

No SQL lives here — every DB access goes through buyback.routes._shared's
singleton repos, ContractTemplateRepository, and core.organization's
CompanyRepository (all raw-SQL-via-BaseRepository, same posture as every
other buyback route module).

This is a MANUAL trigger, not a lifecycle gate: it must never 500 on sparse
data. The only non-2xx outcomes are 404 (no such record), 403
(_guard_company — cross-company IDOR), and 409 (no active template for this
company/brand/document_type, even after the company-default fallback).
Missing seller/offer data still renders a (partially empty) PDF and comes
back 200, with a `warnings` list calling out the gaps.
"""
import logging
from datetime import date

from flask import request, jsonify
from flask_login import login_required

from buyback import buyback_bp
from buyback.routes import _shared
from buyback.repositories.contract_template_repository import ContractTemplateRepository
from buyback.services.contract_pdf import build_contract_context, render_contract_pdf
from core.organization.repositories.company_repository import CompanyRepository
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.buyback')

# Module-level singletons (mirrors buyback/routes/contract_templates.py's
# `_repo = ContractTemplateRepository()`): both repos are stateless raw-SQL
# wrappers, so one shared instance per process is safe and avoids
# re-instantiating per request.
_template_repo = ContractTemplateRepository()
_company_repo = CompanyRepository()

_DOC_TYPES = ('purchase', 'consignment')

# Statuses on which an un-specified document_type infers 'consignment'
# rather than 'purchase' — mirrors records.py get_record's own
# status-gated consignment lookup (lifecycle.CONSIGNMENT_OFFER/CONSIGNAT).
_CONSIGNMENT_STATUSES = ('CONSIGNMENT_OFFER', 'CONSIGNAT')


def _resolve_document_type(data, record):
    """Explicit `document_type` from the request body wins when it's one of
    the two recognized values; otherwise infer from the record's current
    lifecycle status."""
    requested = data.get('document_type')
    if requested in _DOC_TYPES:
        return requested
    return 'consignment' if record.get('status') in _CONSIGNMENT_STATUSES else 'purchase'


def _accepted_offer(record_id, document_type):
    """The accepted offer of the kind matching `document_type` ('consignment'
    offers pair with a consignment contract, every other document type pairs
    with the 'final' purchase offer), or None when no offer of that kind has
    been accepted yet."""
    wanted = 'consignment' if document_type == 'consignment' else 'final'
    offers = _shared.offers_repo.list_for_record(record_id)
    return next(
        (o for o in offers
         if o.get('offer_type') == wanted and o.get('client_decision') == 'accepted'),
        None,
    )


def _consignment_agreement(record):
    """The consignment agreement for this record's CarPark vehicle, if any.

    Mirrors records.py's get_record consignment lookup (same local-import
    rationale: avoids a cross-module import cycle at buyback module-load
    time, and keeps the repo patchable in tests). A consignment agreement
    only ever exists once the record carries a carpark_vehicle_id."""
    if not record.get('carpark_vehicle_id'):
        return None
    from carpark.repositories.consignment_repository import ConsignmentRepository
    return ConsignmentRepository().get_by_vehicle(record['carpark_vehicle_id'])


def _build_warnings(context):
    """Non-blocking hints about gaps baked into the rendered contract — never
    blocks generation (only 404/403/409 do). Derived from the same empty
    critical tokens a human reviewing the PDF would notice missing."""
    warnings = []
    if not context.get('price_eur'):
        warnings.append('Nicio ofertă acceptată — preț necompletat')
    if not context.get('seller_name'):
        warnings.append('Lipsesc datele vânzătorului')
    return warnings


@buyback_bp.route('/records/<int:record_id>/generate-contract', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def generate_contract(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    # SECURITY: same unconditional IDOR guard as every other single-record
    # mutation route (records.py::get_record/update_record) — the company
    # boundary must be checked before anything else about the record is
    # read or acted on.
    err = _shared._guard_company(record)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    document_type = _resolve_document_type(data, record)

    template = _template_repo.get_active_with_default(
        record['company_id'], record['brand_id'], document_type,
    )
    if template is None:
        return jsonify({
            'error': 'Nu există un model de contract activ pentru acest brand/companie.'
        }), 409

    company = _company_repo.get(record['company_id'])
    offer = _accepted_offer(record_id, document_type)
    consignment = _consignment_agreement(record)

    context = build_contract_context(
        record, company, offer=offer, consignment=consignment,
        contract_number=record.get('record_code') or '',
        contract_date=date.today().isoformat(),
    )

    pdf_bytes = render_contract_pdf(template, context)
    photo = _shared.photos_repo.store_contract_pdf(
        record_id, pdf_bytes, caption=template.get('title') or 'Contract',
    )

    return jsonify({
        'photo': _shared.serialize_photos([photo])[0],
        'warnings': _build_warnings(context),
    }), 200
