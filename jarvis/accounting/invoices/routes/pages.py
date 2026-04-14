"""UI page routes for invoices."""
from ._shared import *  # noqa: F401, F403


@invoices_bp.route('/add-invoice')
@login_required
def add_invoice():
    """Redirect to React add invoice page."""
    return redirect('/app/accounting/add')


@invoices_bp.route('/accounting')
@login_required
def accounting():
    """Redirect to React accounting dashboard."""
    return redirect('/app/accounting')
