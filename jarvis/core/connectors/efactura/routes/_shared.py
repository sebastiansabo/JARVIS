"""
Shared imports and decorators for e-Factura routes.
"""
from functools import wraps
from flask import jsonify
from flask_login import current_user

from core.utils.logging_config import get_logger
from core.utils.api_helpers import safe_error_response, api_login_required
from core.roles.repositories.permission_repository import PermissionRepository

from .. import efactura_bp
from ..config import InvoiceDirection, ArtifactType
from ..services import EFacturaService

_perm_repo = PermissionRepository()
efactura_service = EFacturaService()
logger = get_logger('jarvis.core.connectors.efactura.routes')


def efactura_access_required(f):
    """Require efactura.module.access V2 permission."""
    @wraps(f)
    def decorated(*args, **kwargs):
        role_id = getattr(current_user, 'role_id', None)
        if not role_id:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        perm = _perm_repo.check_permission_v2(role_id, 'efactura', 'module', 'access')
        if not perm.get('has_permission'):
            return jsonify({'success': False, 'error': 'e-Factura access denied'}), 403
        return f(*args, **kwargs)
    return decorated
