"""Resolve + render + store a BuyBack contract for a record — the shared core
behind both the manual contract route (P3b/P3c) and the accept-time
auto-generate (P4). Signature-aware: an optional seller signature data-URL is
embedded in the rendered PDF.

Selection rule: `from_data` (or a first generate with nothing posted and
nothing stored) substitutes the active template against the record's current
data; otherwise the advisor's stored/posted contract text is rendered as-is
(so manual edits survive). No HTTP here — callers pass a record dict and get
back the stored photo row + the rendered bytes.
"""
import logging
from datetime import date

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.photo_repository import PhotoRepository
from buyback.repositories.offer_repository import OfferRepository
from buyback.repositories.contract_template_repository import ContractTemplateRepository
from buyback.services.contract_pdf import build_contract_context, render_contract_pdf_from_parts
from buyback.services.contract_template import render_contract_template
from core.organization.repositories.company_repository import CompanyRepository

logger = logging.getLogger('jarvis.buyback')

_records = RecordRepository()
_photos = PhotoRepository()
_offers = OfferRepository()
_template_repo = ContractTemplateRepository()
_company_repo = CompanyRepository()

DOC_TYPES = ('purchase', 'consignment')
_CONSIGNMENT_STATUSES = ('CONSIGNMENT_OFFER', 'CONSIGNAT')


class NoTemplateError(Exception):
    """No active contract template for this company/brand/document_type (even
    after the company-default fallback) and a substitution was required."""


def resolve_document_type(data, record):
    """Explicit `document_type` wins when recognized; else infer from status."""
    requested = (data or {}).get('document_type')
    if requested in DOC_TYPES:
        return requested
    return 'consignment' if record.get('status') in _CONSIGNMENT_STATUSES else 'purchase'


def _accepted_offer(record_id, document_type):
    wanted = 'consignment' if document_type == 'consignment' else 'final'
    offers = _offers.list_for_record(record_id)
    return next(
        (o for o in offers
         if o.get('offer_type') == wanted and o.get('client_decision') == 'accepted'),
        None,
    )


def _consignment_agreement(record):
    # Match records.py's gate: only a LOST/CONSIGNAT record carries a real
    # consignment agreement — don't fetch (stale) terms for a purchase record
    # that merely has a carpark_vehicle_id (e.g. a finalized BOUGHT hand-off).
    if record.get('status') not in ('CONSIGNAT', 'LOST') or not record.get('carpark_vehicle_id'):
        return None
    from carpark.repositories.consignment_repository import ConsignmentRepository
    return ConsignmentRepository().get_by_vehicle(record['carpark_vehicle_id'])


def build_warnings(context):
    """Non-blocking hints about gaps baked into the rendered contract."""
    warnings = []
    if not context.get('price_eur'):
        warnings.append('Nicio ofertă acceptată — preț necompletat')
    if not context.get('seller_name'):
        warnings.append('Lipsesc datele vânzătorului')
    return warnings


def _signatory_for(record):
    company = _company_repo.get(record['company_id']) or {}
    return company.get('administrator') or company.get('company') or ''


def _substitute_from_template(record, template, document_type):
    """record + template -> (title, body, general_conditions, signatory, warnings)."""
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
    return title, body, gc, signatory, build_warnings(context)


def generate_contract(record, *, signature=None, from_data=False, data=None):
    """Render + store the contract for `record`, returning the stored photo row,
    the rendered PDF bytes, the updated record, and any non-blocking warnings.

    `data` carries optional manual-edit overrides from the POST body
    (`document_type`, `title`, `body`, `general_conditions`); `from_data` forces
    a fresh template substitution. `signature` is an optional seller-signature
    data-URL embedded in the PDF (the accept path passes it; absent → the
    "Lipsă semnătură" placeholder). Raises NoTemplateError when a substitution
    is required but no active template exists.
    """
    data = data or {}
    document_type = resolve_document_type(data, record)
    provided_body = data.get('body')
    use_template = from_data or (provided_body is None and not record.get('contract_body'))

    warnings = []
    if use_template:
        template = _template_repo.get_active_with_default(
            record['company_id'], record['brand_id'], document_type)
        if template is None:
            raise NoTemplateError('Nu există un model de contract activ pentru acest brand/companie.')
        title, body, gc, signatory, warnings = _substitute_from_template(record, template, document_type)
    else:
        title = (data.get('title') if 'title' in data else record.get('contract_title')) or ''
        body = provided_body if provided_body is not None else (record.get('contract_body') or '')
        gc = (data.get('general_conditions') if 'general_conditions' in data
              else record.get('contract_general_conditions')) or ''
        signatory = _signatory_for(record)

    # contract_title is VARCHAR(300) — clamp so an over-long title can't 500 the store.
    title = (title or '')[:300]

    pdf_bytes = render_contract_pdf_from_parts(title, body, gc, signatory=signatory, signature=signature)
    updated = _records.update_contract(record['id'], title, body, gc)
    photo = _photos.store_contract_pdf(record['id'], pdf_bytes, caption=title or 'Contract')
    return {
        'photo': photo,
        'pdf_bytes': pdf_bytes,
        'updated': updated,
        'document_type': document_type,
        'parts': {'title': title, 'body': body, 'general_conditions': gc},
        'warnings': warnings,
    }
