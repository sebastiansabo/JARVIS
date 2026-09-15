"""
e-Factura Unallocated Invoices API routes.
"""
from datetime import date
from flask import request, jsonify

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_access_required, InvoiceDirection
from ..services.invoice_allocation_service import InvoiceAllocationService
from ..repositories.invoice_repository import EFacturaInvoiceRepository

_alloc_service = InvoiceAllocationService()
_invoice_repo = EFacturaInvoiceRepository()


# ============================================================
# API: Unallocated Invoices
# ============================================================

@efactura_bp.route('/api/invoices/unallocated', methods=['GET'])
@api_login_required
@efactura_access_required
def list_unallocated_invoices():
    """
    List invoices that have not been sent to the Invoice Module.

    Query params:
        cif: Filter by company CIF
        company_id: Filter by company ID
        direction: 'received' or 'sent'
        start_date: Filter from date (YYYY-MM-DD)
        end_date: Filter to date (YYYY-MM-DD)
        page: Page number (default 1)
        limit: Page size (default 50, max 200)
        sort_by: Column to sort by (default 'issue_date')
        sort_dir: Sort direction ('asc' or 'desc', default 'desc')
    """
    try:
        cif = request.args.get('cif')
        company_id_filter = request.args.get('company_id')
        direction = request.args.get('direction')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')
        hide_typed = request.args.get('hide_typed', '').lower() == 'true'
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 50)), 200)
        sort_by = request.args.get('sort_by', 'issue_date')
        sort_dir = request.args.get('sort_dir', 'desc')

        # Parse direction
        direction_enum = None
        if direction:
            try:
                direction_enum = InvoiceDirection(direction)
            except ValueError:
                pass

        # Parse dates
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None

        result = _alloc_service.list_unallocated_invoices(
            cif_owner=cif,
            company_id=int(company_id_filter) if company_id_filter else None,
            direction=direction_enum,
            start_date=start,
            end_date=end,
            search=search,
            hide_typed=hide_typed,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        return jsonify({
            'success': True,
            'data': result.data['invoices'],
            'companies': result.data['companies'],
            'pagination': result.data['pagination'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/unallocated/count', methods=['GET'])
@api_login_required
@efactura_access_required
def get_unallocated_count():
    """Get count of unallocated invoices for badge."""
    try:
        count = _alloc_service.get_unallocated_count()

        return jsonify({
            'success': True,
            'count': count,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/unallocated/ids', methods=['GET'])
@api_login_required
@efactura_access_required
def get_unallocated_ids():
    """Get all IDs of unallocated invoices (for select all functionality)."""
    try:
        company_id = request.args.get('company_id', type=int)
        direction = request.args.get('direction')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')
        hide_typed = request.args.get('hide_typed', 'false').lower() == 'true'

        ids = _invoice_repo.get_unallocated_ids(
            company_id=company_id,
            direction=direction,
            start_date=start_date,
            end_date=end_date,
            search=search,
            hide_typed=hide_typed,
        )

        return jsonify({
            'success': True,
            'ids': ids,
            'count': len(ids),
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/<int:invoice_id>/overrides', methods=['PUT'])
@api_login_required
@efactura_access_required
def update_invoice_overrides(invoice_id):
    """
    Update invoice-level overrides for Type, Department, and Subdepartment.

    These overrides take precedence over the supplier mapping defaults.
    Passing null/empty clears the override.

    Request body:
        type_override: Optional type override value
        department_override: Optional department override value
        subdepartment_override: Optional subdepartment override value
        department_override_2: Optional second department (for multi-dept allocation)
        subdepartment_override_2: Optional second subdepartment
    """
    try:
        data = request.get_json()
        type_override = data.get('type_override') or None
        department_override = data.get('department_override') or None
        subdepartment_override = data.get('subdepartment_override') or None
        department_override_2 = data.get('department_override_2') or None
        subdepartment_override_2 = data.get('subdepartment_override_2') or None

        # Observers are only updated when the key is explicitly present in the payload
        if 'observer_user_ids' in data:
            raw_observers = data.get('observer_user_ids')
            observer_user_ids = list(raw_observers) if isinstance(raw_observers, list) else []
        else:
            observer_user_ids = None

        # EuroFib schema — only touched when the key is explicitly present (int to set, null to clear)
        konto_config_id = '__keep__'
        if 'konto_config_id' in data:
            raw_kc = data.get('konto_config_id')
            konto_config_id = int(raw_kc) if raw_kc else None

        # Per-line schema mode (int-keyed map {line_index: konto_config_id}). Only touched when present.
        konto_per_line = '__keep__'
        if 'konto_per_line' in data:
            konto_per_line = bool(data.get('konto_per_line'))
        konto_line_map = '__keep__'
        if 'konto_line_map' in data:
            raw_map = data.get('konto_line_map') or {}
            konto_line_map = {str(int(k)): int(v) for k, v in raw_map.items() if v} if isinstance(raw_map, dict) else {}

        # Per-allocation zones {line_index: [{department, subdepartment, value, konto_config_id}]}.
        konto_alloc_map = '__keep__'
        if 'konto_alloc_map' in data:
            raw_alloc = data.get('konto_alloc_map') or {}
            konto_alloc_map = {}
            if isinstance(raw_alloc, dict):
                for k, zones in raw_alloc.items():
                    clean = [{
                        'department': str(z['department']),
                        'subdepartment': str(z['subdepartment']) if z.get('subdepartment') else None,
                        'value': float(z.get('value') or 0),
                        'konto_config_id': int(z['konto_config_id']) if z.get('konto_config_id') else None,
                    } for z in zones if isinstance(z, dict) and z.get('department')] if isinstance(zones, list) else []
                    if clean:
                        konto_alloc_map[str(int(k))] = clean

        success = _invoice_repo.update_overrides(
            invoice_id=invoice_id,
            type_override=type_override,
            department_override=department_override,
            subdepartment_override=subdepartment_override,
            department_override_2=department_override_2,
            subdepartment_override_2=subdepartment_override_2,
            observer_user_ids=observer_user_ids,
            konto_config_id=konto_config_id,
            konto_per_line=konto_per_line,
            konto_line_map=konto_line_map,
            konto_alloc_map=konto_alloc_map,
        )

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to update overrides'}), 500

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/bulk-overrides', methods=['PUT'])
@api_login_required
@efactura_access_required
def bulk_update_invoice_overrides():
    """
    Bulk update invoice-level overrides for multiple invoices.

    Request body:
        invoice_ids: List of invoice IDs to update
        type_override: Optional type override value (only updated if key is present)
        department_override: Optional department override value (only updated if key is present)
        subdepartment_override: Optional subdepartment override value (only updated if key is present)
        department_override_2: Optional second department (only updated if key is present)
        subdepartment_override_2: Optional second subdepartment (only updated if key is present)

    Note: Only fields present in the request body will be updated.
          Passing null clears the override. Omitting a field keeps the existing value.
    """
    try:
        data = request.get_json()
        invoice_ids = data.get('invoice_ids', [])

        if not invoice_ids:
            return jsonify({'success': False, 'error': 'No invoice IDs provided'}), 400

        # Build updates dict only for fields that are explicitly provided
        updates = {}
        if 'type_override' in data:
            updates['type_override'] = data['type_override'] or None
        if 'department_override' in data:
            updates['department_override'] = data['department_override'] or None
        if 'subdepartment_override' in data:
            updates['subdepartment_override'] = data['subdepartment_override'] or None
        if 'department_override_2' in data:
            updates['department_override_2'] = data['department_override_2'] or None
        if 'subdepartment_override_2' in data:
            updates['subdepartment_override_2'] = data['subdepartment_override_2'] or None

        if not updates:
            return jsonify({'success': False, 'error': 'No fields to update provided'}), 400

        count = _invoice_repo.bulk_update_overrides(
            invoice_ids=invoice_ids,
            updates=updates,
        )

        return jsonify({
            'success': True,
            'updated_count': count,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/send-to-module', methods=['POST'])
@api_login_required
@efactura_access_required
def send_to_invoice_module():
    """
    Send selected invoices to the main JARVIS Invoice Module.

    Creates records in the main invoices table and marks these as allocated.

    Request body:
        invoice_ids: List of e-Factura invoice IDs to send
        observer_user_ids: Optional list of user IDs to attach as observers to every created invoice
    """
    try:
        data = request.get_json() or {}
        invoice_ids = data.get('invoice_ids', [])
        observer_user_ids = data.get('observer_user_ids') or None

        if not invoice_ids:
            return jsonify({
                'success': False,
                'error': "No invoices selected",
            }), 400

        result = _alloc_service.send_to_invoice_module(invoice_ids, observer_user_ids=observer_user_ids)

        if not result.success:
            # A schema-selection gate is a client-fixable validation error (400), not a 500.
            needs_schema = (result.data or {}).get('needs_schema')
            return jsonify({
                'success': False,
                'error': result.error or 'Failed to send invoices to module',
                'needs_schema': needs_schema,
            }), 400 if needs_schema else 500

        return jsonify({
            'success': True,
            'sent': result.data['sent'],
            'duplicates': result.data.get('duplicates', 0),
            'errors': result.data.get('errors'),
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/backfill-line-items', methods=['POST'])
@api_login_required
@efactura_access_required
def backfill_line_items():
    """One-time maintenance: populate invoices.line_items from stored e-Factura XML so the Procesare
    EuroFib export posts the article as `text`. Body: {only_missing?: bool (default true)}."""
    try:
        data = request.get_json(silent=True) or {}
        updated = _alloc_service.backfill_invoice_line_items(
            only_missing=bool(data.get('only_missing', True)))
        return jsonify({'success': True, 'updated': updated})
    except Exception as e:
        return safe_error_response(e)
