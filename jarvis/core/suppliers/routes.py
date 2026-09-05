"""Supplier master + Procesare resolution API."""
import re

from flask import Blueprint, Response, jsonify, request
from flask_login import login_required, current_user
from psycopg2 import errors as pg_errors

from core.organization.repositories.company_repository import CompanyRepository
from core.roles.repositories.permission_repository import PermissionRepository
from core.suppliers.eurofib_export import build_csv, build_xlsx
from core.suppliers.normalize import normalize_cui
from core.suppliers.repository import SupplierMasterRepository, KONTO_FIELDS
from core.suppliers.resolver import SupplierResolver

suppliers_bp = Blueprint('suppliers', __name__)
_perm_repo = PermissionRepository()
_repo = SupplierMasterRepository()
_company_repo = CompanyRepository()
_resolver = SupplierResolver(_repo)


def _is_unique_violation(exc: Exception) -> bool:
    """True for a psycopg2 UniqueViolation, or (fallback) any exception whose class name
    contains 'UniqueViolation' — covers cases where the driver exception is mocked/wrapped.
    The name check runs first (a real psycopg2 UniqueViolation is class-named 'UniqueViolation'
    too) so this stays correct even where pg_errors.UniqueViolation is stubbed to a non-type."""
    if 'UniqueViolation' in type(exc).__name__:
        return True
    unique_violation = getattr(pg_errors, 'UniqueViolation', None)
    return isinstance(unique_violation, type) and isinstance(exc, unique_violation)


def _check_supplier_perm(action: str) -> bool:
    if getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin'):
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'suppliers', 'master', action)
    return perm.get('has_permission', False)


def _parse_company_id(raw):
    """Parse a required company_id query param. Returns (company_id, error_response)."""
    if not raw:
        return None, (jsonify({'success': False, 'error': 'company_id is required'}), 400)
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, (jsonify({'success': False, 'error': 'company_id must be an integer'}), 400)


def _to_invoice_config_pairs(rows, company_id, skipped):
    """Map raw list_budgeted_invoices rows to (invoice, konto) pairs consumable by
    build_csv, appending {'invoice_number', 'supplier', 'reason': 'missing_amounts'} to
    `skipped` (mutated in place) for any row missing net/gross amounts."""
    pairs = []
    for row in rows:
        net = row.get('net_value')
        gross = row.get('gross_amount') if row.get('gross_amount') is not None else row.get('invoice_value')
        if net is None or gross is None:
            skipped.append({'invoice_number': row.get('invoice_number'), 'supplier': row.get('supplier'),
                            'reason': 'missing_amounts'})
            continue
        vat = float(gross) - float(net)
        konto = _repo.get_effective_konto(row['supplier_id'], company_id)['konto']
        invoice = {
            'supplier': row.get('supplier'),
            'supplier_id': row.get('supplier_id'),
            'invoice_number': row.get('invoice_number'),
            'invoice_date': row.get('invoice_date'),
            # `invoices` has no due_date column (only efactura_invoices does) — fall back to
            # invoice_date as the "valuta" value date until a real due_date is plumbed through.
            'due_date': row.get('invoice_date'),
            'net_amount': net,
            'vat_amount': vat,
            'gross_amount': gross,
            'line_description': row.get('line_description'),
        }
        pairs.append((invoice, konto))
    return pairs


@suppliers_bp.route('/api/suppliers', methods=['GET'])
@login_required
def api_list_suppliers():
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company_id = request.args.get('company_id')
    suppliers = _repo.list_master(
        search=request.args.get('search'),
        limit=min(int(request.args.get('limit', 100)), 500),
        offset=int(request.args.get('offset', 0)),
        company_id=int(company_id) if company_id else None)
    return jsonify({'success': True, 'suppliers': suppliers})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
@login_required
def api_get_supplier(supplier_id):
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    sup = _repo.get_master(supplier_id)
    if not sup:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'supplier': sup})


@suppliers_bp.route('/api/suppliers', methods=['POST'])
@login_required
def api_create_supplier():
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    fields = {k: v for k, v in data.items() if k not in {'id', 'name', 'created_by', 'created_at', 'updated_at'}}
    try:
        sid = _repo.create_master(name, created_by=getattr(current_user, 'id', None), **fields)
    except pg_errors.UniqueViolation:
        return jsonify({'success': False, 'error': 'A supplier with this CUI already exists'}), 409
    except Exception as exc:
        if _is_unique_violation(exc):
            return jsonify({'success': False, 'error': 'A supplier with this CUI already exists'}), 409
        raise
    return jsonify({'success': True, 'id': sid}), 201


@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@login_required
def api_update_supplier(supplier_id):
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    fields = {k: v for k, v in data.items() if k not in {'id', 'supplier_id', 'created_by', 'created_at', 'updated_at'}}
    _repo.update_master(supplier_id, **fields)
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/konto', methods=['GET'])
@login_required
def api_get_konto(supplier_id):
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company_id, err = _parse_company_id(request.args.get('company_id'))
    if err:
        return err
    result = _repo.get_effective_konto(supplier_id, company_id)
    return jsonify({'success': True, 'konto': result['konto'], 'has_company_config': result['has_company_config']})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/konto', methods=['PUT'])
@login_required
def api_update_konto(supplier_id):
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    fields = {k: v for k, v in data.items() if k in KONTO_FIELDS}
    uid = getattr(current_user, 'id', None)

    if data.get('replicate_all'):
        count = _repo.replicate_konto(supplier_id, fields, created_by=uid)
        return jsonify({'success': True, 'replicated': count})

    company_id, err = _parse_company_id(request.args.get('company_id'))
    if err:
        return err
    kc_id = _repo.upsert_konto(supplier_id, company_id, created_by=uid, **fields)
    return jsonify({'success': True, 'id': kc_id})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/aliases', methods=['POST'])
@login_required
def api_add_alias(supplier_id):
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    alias_id = _repo.add_alias(supplier_id, alias_name=data.get('alias_name'),
                               alias_cui=data.get('alias_cui'), source=data.get('source', 'manual'),
                               created_by=getattr(current_user, 'id', None))
    return jsonify({'success': True, 'id': alias_id}), 201


@suppliers_bp.route('/api/suppliers/merge', methods=['POST'])
@login_required
def api_merge_suppliers():
    if not _check_supplier_perm('merge'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    try:
        survivor = int(data.get('survivor_id'))
        dup = int(data.get('duplicate_id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'survivor_id and duplicate_id must be integers'}), 400
    if survivor == dup:
        return jsonify({'success': False, 'error': 'survivor_id and duplicate_id must differ'}), 400
    _repo.merge(survivor, dup, created_by=getattr(current_user, 'id', None))
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/worklist', methods=['GET'])
@login_required
def api_worklist():
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    raw_company_id = request.args.get('company_id')
    company_id, company_name = None, None
    if raw_company_id:
        try:
            company_id = int(raw_company_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'company_id must be an integer'}), 400
        company = _company_repo.get(company_id)
        company_name = company['company'] if company else None

    items = []
    for row in _repo.unresolved_efactura(company_id=company_id):
        res = _resolver.resolve(name=row['partner_name'], cui=row['partner_cif'])
        if res.confidence != 'high':
            items.append({'source': 'efactura', 'partner_name': row['partner_name'],
                          'partner_cif': row['partner_cif'],
                          'candidate_id': res.supplier_id, 'confidence': res.confidence, 'method': res.method})
    for row in _repo.unresolved_invoice_suppliers(company_name=company_name):
        res = _resolver.resolve(name=row['partner_name'])
        if res.confidence != 'high':
            items.append({'source': 'invoice', 'partner_name': row['partner_name'], 'partner_cif': None,
                          'count': row['n'], 'candidate_id': res.supplier_id,
                          'confidence': res.confidence, 'method': res.method})
    return jsonify({'success': True, 'items': items})


@suppliers_bp.route('/api/suppliers/invoices', methods=['GET'])
@login_required
def api_worklist_invoices():
    """Invoices for the Procesare Worklist tab — company + period gated, restricted to
    suppliers with a complete Table-2 konto config for that company. `?status=` selects which
    invoice status to list (default 'Bugetata'; the Worklist's "Procesate" toggle passes
    'processed' for a read-only history view)."""
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company_id, err = _parse_company_id(request.args.get('company_id'))
    if err:
        return err
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'start_date and end_date are required'}), 400
    status = request.args.get('status', 'Bugetata')
    company = _company_repo.get(company_id)
    if not company:
        return jsonify({'success': False, 'error': 'Company not found'}), 404
    invoices = _repo.list_budgeted_invoices(company_id, company['company'], start_date, end_date, status=status)
    return jsonify({'success': True, 'invoices': invoices})


# Export-format dispatch: token -> (mimetype, file extension, builder(pairs, skipped=...)).
_EXPORT_FORMATS = {
    'csv': ('text/csv', 'csv', build_csv),
    'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx', build_xlsx),
}


def _export_format(fmt):
    """Resolve an export-format token to (mimetype, extension, builder). Unknown/blank -> csv."""
    return _EXPORT_FORMATS.get((fmt or 'csv').lower(), _EXPORT_FORMATS['csv'])


@suppliers_bp.route('/api/suppliers/export', methods=['POST'])
@login_required
def api_export():
    """Batch EuroFib (MEDLINE) export of budgeted invoices for a company + period, as a single
    file (grouped/ordered by supplier). Body: {company_id, start_date, end_date, invoice_ids?,
    format?}. format is 'csv' (default) or 'xlsx'. When invoice_ids is given, only those
    invoices are exported (the general export passes the checked rows, or all shown if none)."""
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json(force=True) or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    company_id, err = _parse_company_id(data.get('company_id'))
    if err:
        return err
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'start_date and end_date are required'}), 400

    company = _company_repo.get(company_id)
    if not company:
        return jsonify({'success': False, 'error': 'Company not found'}), 404

    mimetype, ext, builder = _export_format(data.get('format'))

    rows = _repo.list_budgeted_invoices(company_id, company['company'], start_date, end_date, limit=5000)

    invoice_ids = data.get('invoice_ids')
    if invoice_ids:
        try:
            wanted = {int(i) for i in invoice_ids}
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'invoice_ids must be integers'}), 400
        rows = [r for r in rows if r['id'] in wanted]

    skipped = []
    invoices_with_configs = _to_invoice_config_pairs(rows, company_id, skipped)

    skipped_before = len(skipped)
    output = builder(invoices_with_configs, skipped=skipped)
    skipped_in_build = len(skipped) - skipped_before
    written = len(invoices_with_configs) - skipped_in_build

    if written == 0:
        return jsonify({'success': False, 'skipped': skipped}), 200

    skipped_numbers = {s['invoice_number'] for s in skipped}
    exported_ids = [r['id'] for r in rows if r.get('invoice_number') not in skipped_numbers]
    _repo.mark_invoices_processed(exported_ids)

    filename = f"eurofib_{company['company']}_{start_date}_{end_date}.{ext}"
    filename = re.sub(r'[^A-Za-z0-9_.\-]+', '_', filename)
    return Response(
        output,
        mimetype=mimetype,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@suppliers_bp.route('/api/suppliers/unprocess', methods=['POST'])
@login_required
def api_unprocess():
    """Revert exported invoices from 'processed' back to 'Bugetata' (send back to In lucru)."""
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    ids = data.get('invoice_ids') or []
    if not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'invoice_ids must be a list'}), 400
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'invoice_ids must be integers'}), 400
    reverted = _repo.mark_invoices_budgeted(ids)
    return jsonify({'success': True, 'reverted': reverted})


@suppliers_bp.route('/api/suppliers/resolve', methods=['POST'])
@login_required
def api_resolve():
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    action = data.get('action')          # 'link' | 'create' | 'ignore'
    partner_name = data.get('partner_name')
    partner_cif = data.get('partner_cif')
    uid = getattr(current_user, 'id', None)

    if action == 'link':
        sid = data.get('supplier_id')
        if not sid:
            return jsonify({'success': False, 'error': 'supplier_id required for link'}), 400
    elif action == 'create':
        if not partner_name:
            return jsonify({'success': False, 'error': 'partner_name required to create'}), 400
        try:
            sid = _repo.create_master(partner_name, created_by=uid, cui=partner_cif)
        except pg_errors.UniqueViolation:
            return jsonify({'success': False, 'error': 'A supplier with this CUI already exists'}), 409
        except Exception as exc:
            if _is_unique_violation(exc):
                return jsonify({'success': False, 'error': 'A supplier with this CUI already exists'}), 409
            raise
    elif action == 'ignore':
        return jsonify({'success': True, 'ignored': True})
    else:
        return jsonify({'success': False, 'error': 'unknown action'}), 400

    _repo.add_alias(sid, alias_name=partner_name, alias_cui=partner_cif, source='resolve', created_by=uid)
    linked = _repo.set_efactura_supplier_id(sid, partner_name=partner_name, partner_cif=partner_cif)
    return jsonify({'success': True, 'supplier_id': sid, 'efactura_linked': linked})


@suppliers_bp.route('/api/suppliers/efactura-partners', methods=['GET'])
@login_required
def api_efactura_partners():
    """List distinct e-Factura *supplier* partners (received invoices) not yet in the master —
    the picker for the "Sync cu e-Factura" modal. Each row is tagged `existing` (+candidate id/
    name) when it already resolves to a master supplier, so the UI can default those unchecked."""
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    raw = request.args.get('company_id')
    company_id = None
    if raw:
        try:
            company_id = int(raw)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'company_id must be an integer'}), 400
    resolved = [(row, _resolver.resolve(name=row['partner_name'], cui=row['partner_cif']))
                for row in _repo.list_efactura_partners(company_id=company_id)]
    names = _repo.names_by_ids([res.supplier_id for _, res in resolved
                                if res.confidence in ('high', 'medium') and res.supplier_id])
    partners = []
    for row, res in resolved:
        existing = res.confidence in ('high', 'medium') and bool(res.supplier_id)
        partners.append({
            'partner_name': row['partner_name'],
            'partner_cif': row['partner_cif'],
            'count': row['n'],
            'existing': existing,
            'candidate_id': res.supplier_id if existing else None,
            'candidate_name': names.get(res.supplier_id) if existing else None,
            'confidence': res.confidence,
        })
    return jsonify({'success': True, 'partners': partners})


def _import_partner(name, cif, uid):
    """Import one e-Factura partner into the master. Returns 'created' | 'linked' | 'skipped'.
    A partner that already resolves to a master supplier (high/medium confidence, or a CUI
    collision on create) is LINKED to it; otherwise a new master supplier is CREATED. In both
    non-skip cases the partner name/CUI is aliased and its e-Factura rows are bound. Mirrors the
    single-partner /resolve 'create' path."""
    res = _resolver.resolve(name=name, cui=cif)
    if res.confidence in ('high', 'medium') and res.supplier_id:
        sid, outcome = res.supplier_id, 'linked'
    else:
        try:
            sid, outcome = _repo.create_master(name, created_by=uid, cui=cif), 'created'
        except Exception as exc:
            if not _is_unique_violation(exc):
                raise
            # CUI already belongs to a master supplier the resolver didn't match by name — link it.
            sid = _repo.find_by_cui_normalized(normalize_cui(cif))
            if not sid:
                return 'skipped'
            outcome = 'linked'
    _repo.add_alias(sid, alias_name=name, alias_cui=cif, source='efactura_import', created_by=uid)
    _repo.set_efactura_supplier_id(sid, partner_name=name, partner_cif=cif)
    return outcome


@suppliers_bp.route('/api/suppliers/import-efactura', methods=['POST'])
@login_required
def api_import_efactura():
    """Bulk-import selected e-Factura supplier partners into the master (see _import_partner)."""
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    partners = data.get('partners') or []
    uid = getattr(current_user, 'id', None)
    created, linked, skipped = 0, 0, []
    for entry in partners:
        name = (entry or {}).get('partner_name')
        cif = (entry or {}).get('partner_cif')
        if not name:
            continue
        outcome = _import_partner(name, cif, uid)
        if outcome == 'created':
            created += 1
        elif outcome == 'linked':
            linked += 1
        else:
            skipped.append({'partner_name': name, 'reason': 'duplicate_cui'})
    return jsonify({'success': True, 'created': created, 'linked': linked, 'skipped': skipped})


@suppliers_bp.route('/api/suppliers/backfill-efactura', methods=['POST'])
@login_required
def api_backfill_efactura():
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    bound = 0
    for row in _repo.unresolved_efactura(limit=5000):
        res = _resolver.resolve(name=row['partner_name'], cui=row['partner_cif'])
        if res.confidence == 'high' and res.supplier_id:
            bound += _repo.set_efactura_supplier_id(res.supplier_id,
                                                    partner_name=row['partner_name'],
                                                    partner_cif=row['partner_cif'])
    return jsonify({'success': True, 'bound': bound})
