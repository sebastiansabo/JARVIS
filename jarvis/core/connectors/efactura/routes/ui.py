"""
e-Factura UI redirect routes and migration utility.
"""
from flask import redirect, jsonify
from flask_login import login_required

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_access_required


# ============================================================
# UI Routes
# ============================================================

@efactura_bp.route('/')
@login_required
def index():
    """Redirect to React e-Factura page."""
    return redirect('/app/efactura')


@efactura_bp.route('/api/migrate-junction-table', methods=['POST'])
@api_login_required
@efactura_access_required
def migrate_junction_table():
    """One-time migration to create the supplier mapping types junction table."""
    try:
        from ..repositories.supplier_mapping_repository import SupplierMappingRepository
        repo = SupplierMappingRepository()
        count = repo.migrate_junction_table()

        return jsonify({
            'success': True,
            'message': f'Junction table created/verified. {count} type mappings exist.'
        })
    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/connections')
@login_required
def connections_page():
    """Redirect to React e-Factura connections."""
    return redirect('/app/efactura/connections')


@efactura_bp.route('/invoices')
@login_required
def invoices_page():
    """Redirect to React e-Factura invoices."""
    return redirect('/app/efactura/invoices')


@efactura_bp.route('/sync-history')
@login_required
def sync_history_page():
    """Redirect to React e-Factura sync."""
    return redirect('/app/efactura/sync')
