"""UI page routes for the statements module."""
from ._shared import *  # noqa: F401, F403


# ============== PAGE ROUTES ==============

@statements_bp.route('/')
@login_required
def index():
    """Redirect to React statements page."""
    return redirect('/app/statements')


@statements_bp.route('/mappings')
@login_required
def mappings_page():
    """Redirect to React statements page."""
    return redirect('/app/statements')


@statements_bp.route('/files')
@login_required
def files_page():
    """Redirect to React statements page."""
    return redirect('/app/statements')
