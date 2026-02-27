"""DMS supplier routes (master supplier list)."""
import json
import logging
import urllib.request
from datetime import date

from flask import request, jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import SupplierRepository
from dms.routes.documents import dms_permission_required
from core.utils.api_helpers import safe_error_response, get_json_or_error

logger = logging.getLogger('jarvis.dms.routes.suppliers')

_sup_repo = SupplierRepository()


@dms_bp.route('/api/dms/suppliers', methods=['GET'])
@login_required
@dms_permission_required('supplier', 'view')
def api_list_suppliers():
    """List suppliers with search, filters, pagination."""
    company_id = getattr(current_user, 'company_id', None)
    search = request.args.get('search', '').strip() or None
    supplier_type = request.args.get('supplier_type') or None
    active_only = request.args.get('active_only', 'true').lower() != 'false'
    try:
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))
    except (ValueError, TypeError):
        limit, offset = 50, 0

    suppliers = _sup_repo.list_all(
        company_id=company_id, active_only=active_only,
        search=search, supplier_type=supplier_type,
        limit=limit, offset=offset,
    )
    total = _sup_repo.count(
        company_id=company_id, active_only=active_only,
        search=search, supplier_type=supplier_type,
    )
    return jsonify({'success': True, 'suppliers': suppliers, 'total': total})


@dms_bp.route('/api/dms/suppliers/<int:sup_id>', methods=['GET'])
@login_required
@dms_permission_required('supplier', 'view')
def api_get_supplier(sup_id):
    """Get a single supplier."""
    sup = _sup_repo.get_by_id(sup_id)
    company_id = getattr(current_user, 'company_id', None)
    if not sup or (company_id and sup.get('company_id') != company_id):
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404
    return jsonify({'success': True, 'supplier': sup})


@dms_bp.route('/api/dms/suppliers', methods=['POST'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_create_supplier():
    """Create a new supplier."""
    data, error = get_json_or_error()
    if error:
        return error

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    company_id = getattr(current_user, 'company_id', None)

    try:
        row = _sup_repo.create(
            name=name,
            company_id=company_id,
            created_by=current_user.id,
            supplier_type=data.get('supplier_type', 'company'),
            cui=data.get('cui'),
            j_number=data.get('j_number'),
            address=data.get('address'),
            city=data.get('city'),
            county=data.get('county'),
            nr_reg_com=data.get('nr_reg_com'),
            bank_account=data.get('bank_account'),
            iban=data.get('iban'),
            bank_name=data.get('bank_name'),
            phone=data.get('phone'),
            email=data.get('email'),
            contact_name=data.get('contact_name'),
            contact_function=data.get('contact_function'),
            contact_email=data.get('contact_email'),
            contact_phone=data.get('contact_phone'),
            owner_name=data.get('owner_name'),
            owner_function=data.get('owner_function'),
            owner_email=data.get('owner_email'),
            owner_phone=data.get('owner_phone'),
        )
        return jsonify({'success': True, 'id': row['id']}), 201
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/suppliers/<int:sup_id>', methods=['PUT'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_update_supplier(sup_id):
    """Update a supplier."""
    data, error = get_json_or_error()
    if error:
        return error

    sup = _sup_repo.get_by_id(sup_id)
    company_id = getattr(current_user, 'company_id', None)
    if not sup or (company_id and sup.get('company_id') != company_id):
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    try:
        fields = {}
        for key in ('name', 'supplier_type', 'cui', 'j_number', 'address', 'city',
                     'county', 'nr_reg_com', 'bank_account', 'iban', 'bank_name',
                     'phone', 'email', 'is_active',
                     'contact_name', 'contact_function', 'contact_email', 'contact_phone',
                     'owner_name', 'owner_function', 'owner_email', 'owner_phone'):
            if key in data:
                fields[key] = data[key]
        _sup_repo.update(sup_id, **fields)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/suppliers/<int:sup_id>', methods=['DELETE'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_delete_supplier(sup_id):
    """Soft-delete a supplier."""
    sup = _sup_repo.get_by_id(sup_id)
    company_id = getattr(current_user, 'company_id', None)
    if not sup or (company_id and sup.get('company_id') != company_id):
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404
    _sup_repo.delete(sup_id)
    return jsonify({'success': True})


@dms_bp.route('/api/dms/suppliers/batch-deactivate', methods=['POST'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_batch_deactivate_suppliers():
    """Batch deactivate suppliers."""
    data, error = get_json_or_error()
    if error:
        return error
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list) or len(ids) > 500:
        return jsonify({'success': False, 'error': 'ids array required (max 500)'}), 400
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'All ids must be integers'}), 400
    company_id = getattr(current_user, 'company_id', None)
    placeholders = ','.join(['%s'] * len(ids))
    conditions = [f'id IN ({placeholders})']
    params = list(ids)
    if company_id:
        conditions.append('company_id = %s')
        params.append(company_id)
    result = _sup_repo.execute(
        f"UPDATE suppliers SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE {' AND '.join(conditions)}",
        tuple(params)
    )
    return jsonify({'success': True, 'affected': result if isinstance(result, int) else len(ids)})


@dms_bp.route('/api/dms/suppliers/<int:sup_id>/documents', methods=['GET'])
@login_required
@dms_permission_required('supplier', 'view')
def api_supplier_documents(sup_id):
    """Get documents and annexes linked to a supplier (by name match in document_parties)."""
    sup = _sup_repo.get_by_id(sup_id)
    if not sup:
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404
    limit = min(int(request.args.get('limit', 20)), 50)
    docs = _sup_repo.query_all('''
        SELECT d.id, d.title, d.status, d.doc_number, d.doc_date, d.expiry_date,
               d.parent_id, d.relationship_type,
               dp.party_role, c.name AS category_name
        FROM document_parties dp
        JOIN dms_documents d ON d.id = dp.document_id AND d.deleted_at IS NULL
        LEFT JOIN dms_categories c ON c.id = d.category_id
        WHERE dp.entity_name = %s
        ORDER BY d.doc_date DESC NULLS LAST, d.created_at DESC
        LIMIT %s
    ''', (sup['name'], limit))
    return jsonify({'success': True, 'documents': docs})


# ── ANAF sync helpers ──────────────────────────────────────────

ANAF_TVA_URL = 'https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva'


def _fetch_anaf(cui_list: list[int]) -> dict:
    """Call ANAF API with a list of CUIs, return {cui: date_generale}."""
    today = date.today().strftime('%Y-%m-%d')
    payload = [{'cui': c, 'data': today} for c in cui_list]
    req = urllib.request.Request(
        ANAF_TVA_URL,
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
    )
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    result = {}
    for item in data.get('found', []):
        dg = item.get('date_generale', {})
        result[dg.get('cui')] = dg
    return result


def _parse_anaf_data(dg: dict) -> dict:
    """Parse ANAF date_generale into supplier fields."""
    addr_full = dg.get('adresa', '')
    phone = dg.get('telefon', '') or ''
    nrc = dg.get('nrRegCom', '') or ''

    city, county = '', ''
    parts = [p.strip() for p in addr_full.split(',')]
    for p in parts:
        pu = p.upper().strip()
        if pu.startswith('JUD.'):
            county = p.replace('JUD.', '').replace('jud.', '').strip()
        elif 'MUNICIPIUL' in pu:
            city = 'București' if ('BUCUREŞTI' in pu or 'BUCURESTI' in pu) else pu.replace('MUNICIPIUL', '').strip()
        elif pu.startswith('MUN.'):
            city = p.replace('MUN.', '').replace('mun.', '').strip()
        elif pu.startswith('SAT '):
            city = p.split('COM.')[0].replace('SAT', '').replace('sat', '').strip() if 'COM.' in p.upper() else p[4:].strip()
        elif pu.startswith('ORAŞ') or pu.startswith('ORA.'):
            city = pu.replace('ORAŞ', '').replace('ORA.', '').strip()

    street_parts = []
    for p in parts:
        pu = p.upper().strip()
        if any(pu.startswith(pf) for pf in ['STR', 'ŞOS', 'SOS', 'CAL', 'ALEEA', 'B-DUL', 'BD.']):
            street_parts.append(p.strip())
        elif any(kw in pu for kw in ['NR.', 'BL.', 'SC.', 'ET.', 'AP.', 'CAMERA', 'CLADIREA']):
            street_parts.append(p.strip())
    street_addr = ', '.join(street_parts) if street_parts else ''

    return {
        'address': street_addr,
        'city': city,
        'county': county,
        'phone': phone,
        'j_number': nrc,
        'nr_reg_com': nrc if '/' in nrc else '',
        'anaf_name': dg.get('denumire', ''),
    }


@dms_bp.route('/api/dms/suppliers/<int:sup_id>/sync-anaf', methods=['POST'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_sync_anaf_supplier(sup_id):
    """Sync a single supplier with ANAF by CUI."""
    sup = _sup_repo.get_by_id(sup_id)
    company_id = getattr(current_user, 'company_id', None)
    if not sup or (company_id and sup.get('company_id') != company_id):
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    cui_raw = (sup.get('cui') or '').strip().replace('RO', '').replace('ro', '')
    if not cui_raw or not cui_raw.isdigit():
        return jsonify({'success': False, 'error': 'Supplier has no valid CUI'}), 400

    cui = int(cui_raw)
    try:
        anaf_data = _fetch_anaf([cui])
    except Exception as e:
        logger.error(f'ANAF API error for CUI {cui}: {e}')
        return jsonify({'success': False, 'error': f'ANAF API error: {str(e)}'}), 502

    if cui not in anaf_data:
        return jsonify({'success': False, 'error': f'CUI {cui} not found in ANAF'}), 404

    parsed = _parse_anaf_data(anaf_data[cui])
    anaf_name = parsed.pop('anaf_name', '')

    # Update only empty fields (don't overwrite existing data)
    updates = {}
    for key in ('address', 'city', 'county', 'phone', 'j_number', 'nr_reg_com'):
        if not sup.get(key) and parsed.get(key):
            updates[key] = parsed[key]

    if updates:
        _sup_repo.update(sup_id, **updates)

    return jsonify({
        'success': True,
        'anaf_name': anaf_name,
        'updated_fields': list(updates.keys()),
        'supplier': _sup_repo.get_by_id(sup_id),
    })


@dms_bp.route('/api/dms/suppliers/sync-anaf-batch', methods=['POST'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_sync_anaf_batch():
    """Sync all suppliers that have a CUI with ANAF data."""
    company_id = getattr(current_user, 'company_id', None)
    all_sups = _sup_repo.list_all(company_id=company_id, active_only=True, limit=500, offset=0)

    # Collect suppliers with valid CUIs
    to_sync = []
    for s in all_sups:
        cui_raw = (s.get('cui') or '').strip().replace('RO', '').replace('ro', '')
        if cui_raw and cui_raw.isdigit():
            to_sync.append((s, int(cui_raw)))

    if not to_sync:
        return jsonify({'success': True, 'synced': 0, 'skipped': 0, 'results': []})

    # ANAF API supports up to 500 CUIs per request
    cui_list = [c for _, c in to_sync]
    try:
        anaf_data = _fetch_anaf(cui_list)
    except Exception as e:
        logger.error(f'ANAF batch sync error: {e}')
        return jsonify({'success': False, 'error': f'ANAF API error: {str(e)}'}), 502

    results = []
    synced = 0
    for sup, cui in to_sync:
        if cui not in anaf_data:
            results.append({'id': sup['id'], 'name': sup['name'], 'cui': str(cui), 'status': 'not_found'})
            continue

        parsed = _parse_anaf_data(anaf_data[cui])
        anaf_name = parsed.pop('anaf_name', '')

        updates = {}
        for key in ('address', 'city', 'county', 'phone', 'j_number', 'nr_reg_com'):
            if not sup.get(key) and parsed.get(key):
                updates[key] = parsed[key]

        if updates:
            _sup_repo.update(sup['id'], **updates)
            synced += 1
            results.append({
                'id': sup['id'], 'name': sup['name'], 'cui': str(cui),
                'status': 'updated', 'anaf_name': anaf_name,
                'updated_fields': list(updates.keys()),
            })
        else:
            results.append({
                'id': sup['id'], 'name': sup['name'], 'cui': str(cui),
                'status': 'already_complete', 'anaf_name': anaf_name,
            })

    return jsonify({
        'success': True,
        'synced': synced,
        'total': len(to_sync),
        'results': results,
    })


@dms_bp.route('/api/dms/suppliers/<int:sup_id>/invoices', methods=['GET'])
@login_required
@dms_permission_required('supplier', 'view')
def api_supplier_invoices(sup_id):
    """Get last invoices for a supplier (by name match)."""
    sup = _sup_repo.get_by_id(sup_id)
    if not sup:
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404
    limit = min(int(request.args.get('limit', 10)), 50)
    invoices = _sup_repo.query_all('''
        SELECT id, supplier, invoice_number, invoice_date, invoice_value,
               currency, value_ron, value_eur, status, payment_status, drive_link
        FROM invoices
        WHERE supplier = %s AND deleted_at IS NULL
        ORDER BY invoice_date DESC
        LIMIT %s
    ''', (sup['name'], limit))
    return jsonify({'success': True, 'invoices': invoices})
