"""Per-record contract routes — the editable draft (GET) + unified write
(manual generate | inline-edit | regenerate-from-data) (POST), plus the legacy
generate-contract alias.

The resolve/render/store core lives in buyback.services.contract_generation
(shared with the P4 accept-time auto-generate); this route layer is HTTP only:
auth, the IDOR guard, the editable-draft payload, and translating
NoTemplateError -> 409.

No SQL lives here. MANUAL trigger, not a lifecycle gate: never 500 on sparse
data — only 404 (no record), 403 (_guard_company IDOR), 409 (no active
template when a substitution is required).
"""
import logging

from flask import request, jsonify
from flask_login import login_required

from buyback import buyback_bp
from buyback.routes import _shared
from buyback.repositories.contract_template_repository import ContractTemplateRepository
from buyback.services.contract_generation import (
    generate_contract, resolve_document_type, _substitute_from_template, NoTemplateError,
)
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.buyback')

_template_repo = ContractTemplateRepository()


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
    document_type = resolve_document_type(request.args, record)
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
    try:
        result = generate_contract(record, data=data, from_data=bool(data.get('from_data')))
    except NoTemplateError as e:
        return jsonify({'error': str(e)}), 409

    serialized = _shared.serialize_photos([result['photo']])[0]
    return jsonify({
        'photo': serialized,
        'draft': _draft(
            result['updated'], result['document_type'], has_template=True,
            download_url=serialized.get('download_url'), warnings=result['warnings']),
        'warnings': result['warnings'],
    }), 200


@buyback_bp.route('/records/<int:record_id>/contract', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def write_contract(record_id):
    return _write_contract(record_id, request.get_json(silent=True) or {})


@buyback_bp.route('/records/<int:record_id>/generate-contract', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def generate_contract_route(record_id):
    """Legacy alias — a first generate substitutes from the active template."""
    data = request.get_json(silent=True) or {}
    data.setdefault('from_data', True)
    return _write_contract(record_id, data)
