"""Connectors API Routes.

Currently disabled/under development. All endpoints return 503.
"""
from flask import jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from core.utils.api_helpers import error_response

from . import connectors_bp


@connectors_bp.route('/buffer')
@login_required
def buffer():
    """Buffer page - currently disabled."""
    flash('Connectors feature is coming soon.', 'info')
    return redirect(url_for('accounting'))


@connectors_bp.route('/connectors')
@login_required
def connectors():
    """Connectors page - currently disabled, shows coming soon message."""
    if not current_user.can_access_connectors:
        flash('You do not have permission to access connectors.', 'error')
        return redirect(url_for('accounting'))

    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connectors - Coming Soon</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-5">
            <div class="text-center">
                <i class="bi bi-plug display-1 text-muted mb-4 d-block"></i>
                <h2>Connectors - Coming Soon</h2>
                <p class="text-muted mb-4">
                    Automatic invoice import from Google Ads, Meta, and other platforms is under development.
                </p>
                <a href="/accounting" class="btn btn-primary">
                    <i class="bi bi-arrow-left"></i> Back to Accounting
                </a>
            </div>
        </div>
    </body>
    </html>
    '''


@connectors_bp.route('/api/connectors', methods=['GET'])
@login_required
def api_get_connectors():
    """Get all connectors - DISABLED."""
    return error_response('Connectors feature is coming soon', 503)


@connectors_bp.route('/api/connectors/<int:connector_id>', methods=['GET'])
@login_required
def api_get_connector(connector_id):
    """Get a specific connector - DISABLED."""
    return error_response('Connectors feature is coming soon', 503)


@connectors_bp.route('/api/connectors', methods=['POST'])
@login_required
def api_create_connector():
    """Create a new connector - DISABLED."""
    return error_response('Connectors feature is coming soon', 503)


@connectors_bp.route('/api/connectors/<int:connector_id>', methods=['PUT'])
@login_required
def api_update_connector(connector_id):
    """Update a connector - DISABLED."""
    return error_response('Connectors feature is coming soon', 503)


@connectors_bp.route('/api/connectors/<int:connector_id>', methods=['DELETE'])
@login_required
def api_delete_connector(connector_id):
    """Delete a connector - DISABLED."""
    return error_response('Connectors feature is coming soon', 503)


@connectors_bp.route('/api/connectors/<int:connector_id>/sync', methods=['POST'])
@login_required
def api_sync_connector(connector_id):
    """Trigger a sync for a connector - DISABLED."""
    return error_response('Connectors feature is coming soon', 503)


@connectors_bp.route('/api/buffer/fetch/<source>', methods=['POST'])
@login_required
def api_buffer_fetch(source):
    """Fetch invoices from a connector source - DISABLED."""
    return error_response('Connectors feature is coming soon', 503)
