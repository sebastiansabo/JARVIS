"""Shared imports and singletons for voucher routes."""
import logging
from flask import jsonify, request, send_file
from flask_login import login_required, current_user

from accounting.vouchers import vouchers_bp
from accounting.vouchers.repositories import VoucherRepository
from accounting.vouchers.services import VoucherService
from accounting.vouchers.schemas import VoucherCreate, VoucherRead, VoucherListItem, VoucherRedeem
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

__all__ = [
    'logging', 'jsonify', 'request', 'send_file', 'login_required', 'current_user',
    'vouchers_bp',
    'VoucherRepository', 'VoucherService',
    'VoucherCreate', 'VoucherRead', 'VoucherListItem', 'VoucherRedeem',
    'error_response', 'handle_api_errors', 'PermissionRepository',
    'logger', '_repo', '_service', '_perm_repo',
    '_check_accounting_role', '_check_voucher_perm',
]

logger = logging.getLogger('jarvis.vouchers.routes')
_repo = VoucherRepository()
_service = VoucherService()
_perm_repo = PermissionRepository()


def _check_voucher_perm(entity: str, action: str) -> bool:
    """Check vouchers.{entity}.{action} V2 permission."""
    if getattr(current_user, 'role_name', '') in ('admin', 'superadmin'):
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'vouchers', entity, action)
    return perm.get('has_permission', False)


def _check_accounting_role() -> bool:
    """Check if current user has accounting voucher access."""
    return _check_voucher_perm('accounting', 'view')
