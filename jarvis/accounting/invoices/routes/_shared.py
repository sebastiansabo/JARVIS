"""Shared imports, singletons, and helpers for invoice route sub-modules."""
import os
import logging
from flask import jsonify, request, redirect
from flask_login import login_required, current_user

from accounting.invoices import invoices_bp
from accounting.invoices.repositories import (
    InvoiceRepository,
    AllocationRepository,
    SummaryRepository,
    InvoiceDmsLinkRepository,
)
from accounting.invoices.services import InvoiceService
from accounting.invoices.services.invoice_service import UserContext
from core.utils.api_helpers import error_response, safe_error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

logger = logging.getLogger('jarvis.invoices.routes')

_invoice_repo = InvoiceRepository()
_allocation_repo = AllocationRepository()
_summary_repo = SummaryRepository()
_service = InvoiceService()
_perm_repo = PermissionRepository()

_LEGACY_FLAG = {
    'view': 'can_view_invoices',
    'add': 'can_add_invoices',
    'edit': 'can_edit_invoices',
    'delete': 'can_delete_invoices',
}


def _check_invoice_perm(action: str) -> bool:
    """Check invoices.records.<action> V2 permission for current user.

    Falls back to legacy boolean flag when no explicit v2 entry exists,
    so local/dev environments without seeded role_permissions_v2 still work.
    """
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'invoices', 'records', action)
    if perm.get('has_explicit_entry'):
        return perm.get('has_permission', False)
    # No v2 entry — fall back to legacy boolean on current_user
    legacy = _LEGACY_FLAG.get(action)
    return bool(getattr(current_user, legacy, False)) if legacy else False


def _get_invoice_scope(action: str) -> str:
    """Return the V2 scope for invoices.records.<action> ('own', 'department', 'all').

    Falls back to 'all' when no explicit v2 entry exists (legacy behaviour).
    """
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return 'deny'
    perm = _perm_repo.check_permission_v2(role_id, 'invoices', 'records', action)
    if perm.get('has_explicit_entry'):
        return perm.get('scope', 'deny')
    return 'all'  # legacy roles without v2 entries see everything


def _get_user_context() -> UserContext:
    """Build UserContext from Flask globals."""
    return UserContext(
        user_id=current_user.id,
        user_email=current_user.email,
        role_name=current_user.role_name,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500],
    )
