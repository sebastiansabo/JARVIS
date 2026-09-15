"""Supplier master + Procesare resolution API."""
import json
import re

from flask import Blueprint, Response, jsonify, request
from flask_login import login_required, current_user
from psycopg2 import errors as pg_errors

from core.organization.repositories.company_repository import CompanyRepository
from core.roles.repositories.permission_repository import PermissionRepository
from core.suppliers.eurofib_export import build_csv, build_xlsx
from core.suppliers.normalize import normalize_cui
from core.suppliers.repository import (
    SupplierMasterRepository, KONTO_FIELDS, MAX_PRESETS_PER_SUPPLIER_COMPANY, PresetLimitError)
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


def _resolve_amounts(row):
    """Resolve (net, gross) for EuroFib posting from an invoice row.

    Whole-value invoices (subtract_vat False — e.g. foreign reverse-charge services that carry
    no VAT line) leave net_value NULL by design; they post net = gross (VAT 0). A VAT invoice
    (subtract_vat True) that is missing its net split is a data gap and is treated as unusable.
    Returns (None, None) when the row can't be posted."""
    gross = row.get('gross_amount') if row.get('gross_amount') is not None else row.get('invoice_value')
    net = row.get('net_value')
    if gross is None:
        return None, None
    if net is None:
        if row.get('subtract_vat'):
            return None, None  # VAT invoice missing its net split → unusable
        net = gross            # whole-value / reverse-charge → net = gross, VAT 0
    return net, gross


def _to_invoice_config_pairs(rows, company_id, skipped):
    """Map raw list_budgeted_invoices rows to (invoice, konto) pairs consumable by
    build_csv, appending {'invoice_number', 'supplier', 'reason': 'missing_amounts'} to
    `skipped` (mutated in place) for any row whose amounts can't be posted."""
    pairs = []
    for row in rows:
        net, gross = _resolve_amounts(row)
        if net is None or gross is None:
            skipped.append({'invoice_number': row.get('invoice_number'), 'supplier': row.get('supplier'),
                            'reason': 'missing_amounts'})
            continue
        vat = float(gross) - float(net)
        # list_budgeted_invoices resolves the effective preset (per-invoice override → active)
        # and returns its konto_config_id; use it so export honours worklist overrides. Fall back
        # to the active preset if a row somehow arrives without one.
        preset_id = row.get('konto_config_id')
        resolved = _repo.get_konto_by_id(preset_id) if preset_id else None
        konto = resolved['konto'] if resolved else _repo.get_effective_konto(row['supplier_id'], company_id)['konto']
        invoice = {
            'supplier': row.get('supplier'),
            'supplier_id': row.get('supplier_id'),
            'invoice_number': row.get('invoice_number'),
            'invoice_date': row.get('invoice_date'),
            # `valuta` = invoice due date (data scadență), sourced from the linked e-Factura
            # (efactura_invoices.due_date via list_budgeted_invoices). Parsed/manual invoices with
            # no e-Factura link have no due date → fall back to invoice_date.
            'due_date': row.get('due_date') or row.get('invoice_date'),
            'net_amount': net,
            'vat_amount': vat,
            'gross_amount': gross,
            'line_description': row.get('line_description'),
        }
        if row.get('per_line'):
            line_configs = _build_line_configs(row, konto, company_id)
            if line_configs is None:  # per-line requested but line totals don't reconcile
                skipped.append({'invoice_number': row.get('invoice_number'), 'supplier': row.get('supplier'),
                                'reason': 'line_totals_mismatch'})
                continue
            if line_configs:
                invoice['line_configs'] = line_configs
        pairs.append((invoice, konto))
    return pairs


def _build_line_configs(row, base_konto, company_id):
    """For a per-line invoice, build the list of {'net','vat','text','config'} the per-line MEDLINE
    builder consumes. Line net = line_items[i].amount (UBL LineExtensionAmount); line VAT =
    net * vat_rate/100. Each line uses its pinned preset (invoice_line_konto_override) else the
    invoice base. Returns [] if the invoice has no usable lines, or None if Σ(line net+VAT)
    diverges from the invoice gross by more than 1 ban (caller skips it)."""
    raw = row.get('line_items_json')
    try:
        items = raw if isinstance(raw, list) else (json.loads(raw) if raw else [])
    except (TypeError, ValueError):
        items = []
    line_over = _repo.list_line_overrides(row['id'])
    base_id = row.get('konto_config_id')
    configs = []
    for idx, li in enumerate(items):
        if not isinstance(li, dict) or li.get('amount') is None:
            continue
        net = float(li['amount'])
        vat = round(net * float(li.get('vat_rate') or 0) / 100.0, 2)
        cfg_id = line_over.get(idx, base_id)
        cfg = (_repo.get_konto_by_id(cfg_id) or {}).get('konto') if cfg_id else None
        configs.append({'net': net, 'vat': vat,
                        'text': li.get('name') or li.get('description') or '',
                        'config': cfg or base_konto})
    if not configs:
        return []
    line_gross = round(sum(c['net'] + c['vat'] for c in configs), 2)
    gross = row.get('invoice_value')
    if gross is not None and abs(line_gross - float(gross)) > 0.01:
        return None
    return configs


def _schedule_export_archive(invoice_ids):
    """After a EuroFib export marks invoices 'Importat', schedule their auto-archive using the
    same notification settings the manual status-change hook honours (archive_enabled +
    archive_delay_hours). The export marks status via raw SQL and bypasses invoice_service, so
    the archive must be scheduled here. Best-effort — the export has already succeeded, so an
    archive-settings/DB hiccup is swallowed rather than failing the download."""
    if not invoice_ids:
        return
    try:
        from core.notifications.repositories import NotificationRepository
        from accounting.invoices.repositories.invoice_repository import InvoiceRepository
        settings = NotificationRepository().get_settings()
        if settings.get('archive_enabled', 'true') != 'true':
            return
        delay = int(settings.get('archive_delay_hours', '24'))
        inv_repo = InvoiceRepository()
        for iid in invoice_ids:
            inv_repo.set_archive_after(iid, delay)
    except Exception:
        pass


def _cancel_export_archive(invoice_ids):
    """Cancel any scheduled auto-archive for invoices reverted from 'Importat' to 'Bugetata'."""
    if not invoice_ids:
        return
    try:
        from accounting.invoices.repositories.invoice_repository import InvoiceRepository
        inv_repo = InvoiceRepository()
        for iid in invoice_ids:
            inv_repo.clear_archive_fields(iid)
    except Exception:
        pass


@suppliers_bp.route('/api/suppliers', methods=['GET'])
@login_required
def api_list_suppliers():
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company_id = request.args.get('company_id')
    only_deleted = request.args.get('deleted') in ('1', 'true', 'True')
    suppliers = _repo.list_master(
        search=request.args.get('search'),
        limit=min(int(request.args.get('limit', 100)), 500),
        offset=int(request.args.get('offset', 0)),
        company_id=int(company_id) if company_id else None,
        only_deleted=only_deleted)
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


@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
@login_required
def api_delete_supplier(supplier_id):
    """Soft-delete a Furnizor (gated on 'edit'). Hides it from lists/resolver; recoverable via
    restore. The who/when is recorded in supplier_audit_log."""
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    deleted = _repo.soft_delete_supplier(
        supplier_id,
        actor_user_id=getattr(current_user, 'id', None),
        actor_name=getattr(current_user, 'name', None))
    if not deleted:
        return jsonify({'success': False, 'error': 'Supplier not found or already deleted'}), 404
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/restore', methods=['POST'])
@login_required
def api_restore_supplier(supplier_id):
    """Restore a soft-deleted Furnizor (gated on 'edit'). 409 if another active supplier has
    since claimed this one's normalized CUI."""
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    try:
        restored = _repo.restore_supplier(
            supplier_id,
            actor_user_id=getattr(current_user, 'id', None),
            actor_name=getattr(current_user, 'name', None))
    except pg_errors.UniqueViolation:
        return jsonify({'success': False, 'error': 'CUI now used by another supplier — resolve the conflict first'}), 409
    except Exception as exc:
        if _is_unique_violation(exc):
            return jsonify({'success': False, 'error': 'CUI now used by another supplier — resolve the conflict first'}), 409
        raise
    if not restored:
        return jsonify({'success': False, 'error': 'Supplier not found or not deleted'}), 404
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
    """Back-compat single-config writer — targets the ACTIVE preset for (supplier, company).
    The preset-manager UI uses the /konto/presets endpoints below; this stays for the legacy
    add-supplier / resolve flows and the replicate-all toggle."""
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


# ── EuroFib preset manager (up to MAX_PRESETS_PER_SUPPLIER_COMPANY per supplier×company) ──
@suppliers_bp.route('/api/suppliers/<int:supplier_id>/konto/presets', methods=['GET'])
@login_required
def api_list_presets(supplier_id):
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company_id, err = _parse_company_id(request.args.get('company_id'))
    if err:
        return err
    presets = _repo.list_presets(supplier_id, company_id)
    return jsonify({'success': True, 'presets': presets, 'max': MAX_PRESETS_PER_SUPPLIER_COMPANY})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/konto/presets', methods=['POST'])
@login_required
def api_create_preset(supplier_id):
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    company_id, err = _parse_company_id(request.args.get('company_id'))
    if err:
        return err
    fields = {k: v for k, v in data.items() if k in KONTO_FIELDS}
    uid = getattr(current_user, 'id', None)
    name = data.get('name')
    is_active = bool(data.get('is_active'))
    try:
        preset_id = _repo.create_preset(supplier_id, company_id, name, is_active=is_active, created_by=uid, **fields)
    except PresetLimitError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except pg_errors.UniqueViolation:
        return jsonify({'success': False, 'error': 'A preset with this name already exists'}), 409
    except Exception as exc:
        if _is_unique_violation(exc):
            return jsonify({'success': False, 'error': 'A preset with this name already exists'}), 409
        raise
    if data.get('replicate_all'):
        _repo.replicate_konto(supplier_id, fields, created_by=uid,
                              name=name or 'Implicit', is_active=is_active)
    return jsonify({'success': True, 'id': preset_id}), 201


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/konto/presets/<int:preset_id>', methods=['PUT'])
@login_required
def api_update_preset(supplier_id, preset_id):
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    fields = {k: v for k, v in data.items() if k in KONTO_FIELDS}
    uid = getattr(current_user, 'id', None)
    try:
        updated = _repo.update_preset(
            preset_id, name=data.get('name'),
            is_active=True if data.get('is_active') else None, **fields)
    except pg_errors.UniqueViolation:
        return jsonify({'success': False, 'error': 'A preset with this name already exists'}), 409
    except Exception as exc:
        if _is_unique_violation(exc):
            return jsonify({'success': False, 'error': 'A preset with this name already exists'}), 409
        raise
    if not updated:
        return jsonify({'success': False, 'error': 'Preset not found'}), 404
    if data.get('replicate_all'):
        _repo.replicate_konto(supplier_id, fields, created_by=uid,
                              name=data.get('name') or 'Implicit',
                              is_active=bool(data.get('is_active')))
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/konto/presets/<int:preset_id>/activate', methods=['POST'])
@login_required
def api_activate_preset(supplier_id, preset_id):
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    if not _repo.set_active(preset_id):
        return jsonify({'success': False, 'error': 'Preset not found'}), 404
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/konto/presets/<int:preset_id>', methods=['DELETE'])
@login_required
def api_delete_preset(supplier_id, preset_id):
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    if not _repo.delete_preset(
            preset_id,
            actor_user_id=getattr(current_user, 'id', None),
            actor_name=getattr(current_user, 'name', None)):
        return jsonify({'success': False, 'error': 'Preset not found'}), 404
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/invoices/<int:invoice_id>/konto-preset', methods=['POST'])
@login_required
def api_set_invoice_preset(invoice_id):
    """Pin (or clear) the EuroFib preset for a single invoice in the worklist. Body:
    {konto_config_id, supplier_id, company_id}. A null/absent konto_config_id clears the
    override → the invoice falls back to the supplier's active preset. The preset must belong to
    the given (supplier_id, company_id)."""
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    konto_config_id = data.get('konto_config_id')
    uid = getattr(current_user, 'id', None)

    if not konto_config_id:
        _repo.clear_invoice_override(invoice_id)
        return jsonify({'success': True, 'cleared': True})

    company_id, err = _parse_company_id(data.get('company_id'))
    if err:
        return err
    supplier_id = data.get('supplier_id')
    owner = _repo.get_preset_owner(konto_config_id)
    if not owner:
        return jsonify({'success': False, 'error': 'Preset not found'}), 404
    if owner['company_id'] != company_id or (supplier_id and owner['supplier_id'] != int(supplier_id)):
        return jsonify({'success': False, 'error': 'Preset does not belong to this supplier/company'}), 400
    _repo.set_invoice_override(invoice_id, konto_config_id, created_by=uid)
    return jsonify({'success': True})


def _preset_owner_error(konto_config_id, data):
    """Validate a preset belongs to the body's (supplier_id, company_id). Returns an error
    response tuple, or None if valid. Assumes konto_config_id is truthy."""
    company_id, err = _parse_company_id(data.get('company_id'))
    if err:
        return err
    owner = _repo.get_preset_owner(konto_config_id)
    if not owner:
        return jsonify({'success': False, 'error': 'Preset not found'}), 404
    supplier_id = data.get('supplier_id')
    if owner['company_id'] != company_id or (supplier_id and owner['supplier_id'] != int(supplier_id)):
        return jsonify({'success': False, 'error': 'Preset does not belong to this supplier/company'}), 400
    return None


@suppliers_bp.route('/api/suppliers/invoices/<int:invoice_id>/per-line', methods=['POST'])
@login_required
def api_set_invoice_per_line(invoice_id):
    """Enable/disable per-line schema mode for an invoice. Body: {per_line, konto_config_id?,
    supplier_id, company_id}. konto_config_id is the base (credit) schema — null = supplier active.
    Disabling clears all line overrides."""
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    per_line = bool(data.get('per_line'))
    konto_config_id = data.get('konto_config_id') or None
    if konto_config_id:
        err = _preset_owner_error(konto_config_id, data)
        if err:
            return err
    _repo.set_invoice_per_line(invoice_id, per_line, konto_config_id=konto_config_id,
                               created_by=getattr(current_user, 'id', None))
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/invoices/<int:invoice_id>/line-preset', methods=['POST'])
@login_required
def api_set_invoice_line_preset(invoice_id):
    """Pin (or clear) the EuroFib schema for one line of a per-line invoice. Body:
    {line_index, konto_config_id|null, supplier_id, company_id}."""
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    if data.get('line_index') is None:
        return jsonify({'success': False, 'error': 'line_index is required'}), 400
    line_index = int(data['line_index'])
    konto_config_id = data.get('konto_config_id') or None
    if konto_config_id:
        err = _preset_owner_error(konto_config_id, data)
        if err:
            return err
    _repo.set_invoice_line_preset(invoice_id, line_index, konto_config_id,
                                  created_by=getattr(current_user, 'id', None))
    return jsonify({'success': True})


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
    invoice status to list (default 'Bugetata'; the Worklist's "Importate" toggle passes
    'Importat' for a read-only history view of EuroFib-exported invoices)."""
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
    _repo.mark_invoices_imported(exported_ids)
    _schedule_export_archive(exported_ids)

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
    """Revert exported invoices from 'Importat' back to 'Bugetata' (send back to In lucru) and
    cancel their scheduled auto-archive."""
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
    reverted = _repo.unmark_imported_invoices(ids)
    _cancel_export_archive(ids)
    return jsonify({'success': True, 'reverted': reverted})


@suppliers_bp.route('/api/suppliers/schemas-for-invoice', methods=['GET'])
@login_required
def api_schemas_for_invoice():
    """EuroFib schemas available for an invoice's supplier at budgeting time. Resolves the
    invoice's free-text supplier → master supplier, then lists that supplier's presets for the
    given company (by name). Powers the required "Schemă EuroFib" selector in the bugetare
    dialog. Returns {presets, active_id, selected_id (current override), count, supplier_id,
    company_id}. An unresolved supplier/company yields count 0 (no selector)."""
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    invoice_id = request.args.get('invoice_id', type=int)
    company = request.args.get('company')
    if not invoice_id or not company:
        return jsonify({'success': False, 'error': 'invoice_id and company are required'}), 400

    empty = {'success': True, 'presets': [], 'active_id': None, 'selected_id': None,
             'count': 0, 'supplier_id': None, 'company_id': None}
    supplier_name = _repo.invoice_supplier_name(invoice_id)
    if not supplier_name:
        return jsonify(empty)
    res = _resolver.resolve(name=supplier_name)
    if not res.supplier_id:
        return jsonify(empty)
    crow = _company_repo.query_one(
        "SELECT id FROM companies WHERE lower(company) = lower(%s)", (company,))
    if not crow:
        return jsonify(empty)
    company_id = crow['id']
    presets = _repo.list_presets(res.supplier_id, company_id)
    active_id = next((p['id'] for p in presets if p['is_active']), None)
    ov = _repo.get_invoice_override_full(invoice_id) or {}
    li_row = _repo.query_one("SELECT line_items FROM invoices WHERE id = %s", (invoice_id,))
    raw_items = li_row.get('line_items') if li_row else None
    try:
        line_items = raw_items if isinstance(raw_items, list) else (json.loads(raw_items) if raw_items else [])
    except (TypeError, ValueError):
        line_items = []
    return jsonify({
        'success': True, 'presets': presets, 'active_id': active_id,
        'selected_id': ov.get('konto_config_id'), 'per_line': bool(ov.get('per_line')),
        'count': len(presets), 'supplier_id': res.supplier_id, 'company_id': company_id,
        'line_items': line_items, 'line_selected': _repo.list_line_overrides(invoice_id),
    })


@suppliers_bp.route('/api/suppliers/schemas-for-efactura', methods=['GET'])
@login_required
def api_schemas_for_efactura():
    """EuroFib schemas for an UNALLOCATED e-Factura invoice's supplier (resolved partner × the
    invoice's company). Powers the schema selector in the e-Factura "Edit Invoice Overrides"
    dialog. Returns {presets, active_id, selected_id (staged efactura choice), count, supplier_id,
    company_id}. Unresolved supplier/company yields count 0 (no selector)."""
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    ef_id = request.args.get('efactura_invoice_id', type=int)
    if not ef_id:
        return jsonify({'success': False, 'error': 'efactura_invoice_id is required'}), 400
    empty = {'success': True, 'presets': [], 'active_id': None, 'selected_id': None,
             'count': 0, 'supplier_id': None, 'company_id': None,
             'per_line': False, 'line_items': [], 'line_selected': {}}
    row = _repo.query_one(
        "SELECT partner_name, partner_cif, company_id, konto_config_id, konto_per_line, konto_line_map, "
        "xml_content FROM efactura_invoices WHERE id = %s", (ef_id,))
    if not row or not row.get('company_id'):
        return jsonify(empty)
    from core.connectors.efactura.services.invoice_allocation_service import xml_to_line_items
    base = {'per_line': bool(row.get('konto_per_line')),
            'line_items': xml_to_line_items(row.get('xml_content')),
            'line_selected': row.get('konto_line_map') or {}}
    res = _resolver.resolve(name=row.get('partner_name'), cui=row.get('partner_cif'))
    if not res.supplier_id:
        return jsonify({**empty, **base, 'company_id': row['company_id'], 'selected_id': row.get('konto_config_id')})
    presets = _repo.list_presets(res.supplier_id, row['company_id'])
    active_id = next((p['id'] for p in presets if p['is_active']), None)
    return jsonify({
        'success': True, 'presets': presets, 'active_id': active_id,
        'selected_id': row.get('konto_config_id'), 'count': len(presets),
        'supplier_id': res.supplier_id, 'company_id': row['company_id'], **base,
    })


@suppliers_bp.route('/api/suppliers/import-ready-ids', methods=['POST'])
@login_required
def api_import_ready_ids():
    """Given a set of invoice ids, return the subset that is READY to export to EuroFib
    (Bugetata + supplier has a complete active konto preset for an allocated company). Powers the
    Accounting "Pregătită de import" badge. Body: {invoice_ids: [...], company_id?: int}. When
    company_id is given, only that company counts; otherwise any allocated company does."""
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    raw_ids = data.get('invoice_ids') or []
    if not isinstance(raw_ids, list):
        return jsonify({'success': False, 'error': 'invoice_ids must be a list'}), 400
    try:
        ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'invoice_ids must be integers'}), 400
    company_id = data.get('company_id')
    if company_id is not None:
        try:
            company_id = int(company_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'company_id must be an integer'}), 400
    ready = _repo.import_ready_ids(ids, company_id=company_id)
    return jsonify({'success': True, 'ready_ids': ready})


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
