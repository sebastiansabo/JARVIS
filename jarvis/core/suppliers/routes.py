"""Supplier master + Procesare resolution API."""
import io
import re
import zipfile

from flask import Blueprint, Response, jsonify, request
from flask_login import login_required, current_user
from psycopg2 import errors as pg_errors

from core.organization.repositories.company_repository import CompanyRepository
from core.roles.repositories.permission_repository import PermissionRepository
from core.suppliers.eurofib_export import build_csv
from core.suppliers.repository import SupplierMasterRepository, KONTO_FIELDS
from core.suppliers.resolver import SupplierResolver

suppliers_bp = Blueprint('suppliers', __name__)
_perm_repo = PermissionRepository()
_repo = SupplierMasterRepository()
_company_repo = CompanyRepository()
_resolver = SupplierResolver(_repo)


def _is_unique_violation(exc: Exception) -> bool:
    """True for a psycopg2 UniqueViolation, or (fallback) any exception whose class name
    contains 'UniqueViolation' — covers cases where the driver exception is mocked/wrapped."""
    if isinstance(exc, pg_errors.UniqueViolation):
        return True
    return 'UniqueViolation' in type(exc).__name__


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
    `skipped` (mutated in place) for any row missing net/gross amounts. Shared by the
    single-file /export route and the per-supplier ZIP /export-all route."""
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
        }
        pairs.append((invoice, konto))
    return pairs


def _safe_filename_part(name):
    """Sanitize a supplier name into a filesystem-safe filename stem."""
    name = re.sub(r'[^A-Za-z0-9 _.\-]+', '_', (name or '').strip())
    name = re.sub(r'\s+', ' ', name).strip()
    return name or 'furnizor'


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
    """Budgeted invoices for the Procesare Worklist tab — company + period gated, restricted
    to suppliers with a complete Table-2 konto config for that company."""
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company_id, err = _parse_company_id(request.args.get('company_id'))
    if err:
        return err
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'start_date and end_date are required'}), 400
    company = _company_repo.get(company_id)
    if not company:
        return jsonify({'success': False, 'error': 'Company not found'}), 404
    invoices = _repo.list_budgeted_invoices(company_id, company['company'], start_date, end_date)
    return jsonify({'success': True, 'invoices': invoices})


@suppliers_bp.route('/api/suppliers/export', methods=['POST'])
@login_required
def api_export():
    """Batch EuroFib (MEDLINE) CSV export of budgeted invoices for a company + period,
    grouped by supplier. Body: {company_id, start_date, end_date, invoice_ids?}."""
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

    skipped_before_csv = len(skipped)
    csv_text = build_csv(invoices_with_configs, skipped=skipped)
    skipped_in_csv = len(skipped) - skipped_before_csv
    written = len(invoices_with_configs) - skipped_in_csv

    if written == 0:
        return jsonify({'success': False, 'skipped': skipped}), 200

    skipped_numbers = {s['invoice_number'] for s in skipped}
    exported_ids = [r['id'] for r in rows if r.get('invoice_number') not in skipped_numbers]
    _repo.mark_invoices_processed(exported_ids)

    filename = f"eurofib_{company['company']}_{start_date}_{end_date}.csv"
    filename = re.sub(r'[^A-Za-z0-9_.\-]+', '_', filename)
    return Response(
        csv_text,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@suppliers_bp.route('/api/suppliers/export-all', methods=['POST'])
@login_required
def api_export_all():
    """Export ALL budgeted invoices for a company + period as a ZIP containing one EuroFib
    (MEDLINE) CSV per supplier. Body: {company_id, start_date, end_date}."""
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

    rows = _repo.list_budgeted_invoices(company_id, company['company'], start_date, end_date, limit=5000)

    by_supplier = {}
    for row in rows:
        key = row.get('supplier_id')
        group = by_supplier.setdefault(key, {'name': row.get('supplier'), 'rows': []})
        group['rows'].append(row)

    zip_buffer = io.BytesIO()
    used_names = set()
    all_skipped = []
    exported_ids = []
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for group in sorted(by_supplier.values(), key=lambda g: (g['name'] or '').lower()):
            skipped = []
            pairs = _to_invoice_config_pairs(group['rows'], company_id, skipped)
            skipped_before_csv = len(skipped)
            csv_text = build_csv(pairs, skipped=skipped)
            skipped_in_csv = len(skipped) - skipped_before_csv
            written = len(pairs) - skipped_in_csv
            all_skipped.extend(skipped)
            if written == 0:
                continue

            skipped_numbers = {s['invoice_number'] for s in skipped}
            exported_ids.extend(r['id'] for r in group['rows'] if r.get('invoice_number') not in skipped_numbers)

            base_name = _safe_filename_part(group['name'])
            filename = f"{base_name}.csv"
            suffix = 2
            while filename in used_names:
                filename = f"{base_name}_{suffix}.csv"
                suffix += 1
            used_names.add(filename)
            zf.writestr(filename, csv_text)

    if not used_names:
        return jsonify({'success': False, 'skipped': all_skipped}), 200

    _repo.mark_invoices_processed(exported_ids)

    zip_buffer.seek(0)
    filename = f"eurofib_{company['company']}_{start_date}_{end_date}.zip"
    filename = re.sub(r'[^A-Za-z0-9_.\-]+', '_', filename)
    return Response(
        zip_buffer.getvalue(),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


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
