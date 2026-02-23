"""Invoice Service — business logic for invoice operations.

Extracts orchestration logic from routes: submit, parse, update,
allocation management, and permanent deletion with Drive cleanup.
Routes call this service; the service coordinates repositories
and side effects (notifications, auto-tagging, e-Factura linking).
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from ..repositories import InvoiceRepository, AllocationRepository

logger = logging.getLogger('jarvis.invoices.service')

ROLE_HIERARCHY = ['Viewer', 'Manager', 'Admin']


@dataclass
class UserContext:
    """Lightweight user context passed from route handlers."""
    user_id: int
    user_email: str
    role_name: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    status_code: int = 200


class InvoiceService:
    """Orchestrates invoice business logic across repositories and services."""

    def __init__(self):
        self.invoice_repo = InvoiceRepository()
        self.allocation_repo = AllocationRepository()

    # ============== Public Methods ==============

    def submit_invoice(self, data: Dict[str, Any], user: UserContext) -> ServiceResult:
        """Submit a new invoice with allocations and all side effects.

        Orchestrates: save -> correction tracking -> e-Factura link ->
                      email notify -> auto-tag -> event log.
        """
        try:
            invoice_id = self.invoice_repo.save(
                supplier=data['supplier'],
                invoice_template=data.get('invoice_template', ''),
                invoice_number=data['invoice_number'],
                invoice_date=data['invoice_date'],
                invoice_value=float(data['invoice_value']),
                currency=data.get('currency', 'RON'),
                drive_link=data.get('drive_link', ''),
                distributions=data['distributions'],
                value_ron=data.get('value_ron'),
                value_eur=data.get('value_eur'),
                exchange_rate=data.get('exchange_rate'),
                comment=data.get('comment', ''),
                payment_status=data.get('payment_status', 'not_paid'),
                subtract_vat=data.get('subtract_vat', False),
                vat_rate=data.get('vat_rate'),
                net_value=data.get('net_value'),
                line_items=data.get('_line_items'),
                invoice_type=data.get('_invoice_type', 'standard'),
            )

            self._track_corrections(data, invoice_id, user)

            efactura_match_id = data.get('_efactura_match_id')
            if efactura_match_id:
                self._link_efactura(int(efactura_match_id), invoice_id)

            notifications_sent = self._notify_allocations(
                invoice_data={
                    'id': invoice_id,
                    'invoice_number': data['invoice_number'],
                    'supplier': data['supplier'],
                    'invoice_date': data['invoice_date'],
                    'invoice_value': float(data['invoice_value']),
                    'currency': data.get('currency', 'RON'),
                },
                distributions=data['distributions'],
            )

            self._auto_tag(invoice_id, user.user_id)

            self._log_event(user, 'invoice_created',
                            f'Created invoice {data["invoice_number"]} from {data["supplier"]}',
                            entity_type='invoice', entity_id=invoice_id)

            from database import refresh_connection_pool
            refresh_connection_pool()

            return ServiceResult(success=True, data={
                'success': True,
                'message': f'Successfully saved {len(data["distributions"])} allocation(s)',
                'allocations': len(data['distributions']),
                'invoice_id': invoice_id,
                'notifications_sent': notifications_sent,
            })

        except ValueError as e:
            return ServiceResult(success=False, error=str(e), status_code=400)
        except Exception as e:
            logger.error(f"Invoice submit failed: {e}", exc_info=True)
            return ServiceResult(success=False, error=str(e), status_code=500)

    def parse_invoice(self, file_bytes: bytes, filename: str,
                      template_id: Optional[int] = None) -> ServiceResult:
        """Parse an uploaded invoice using AI or template.

        Orchestrates: template selection -> AI parse -> currency conversion ->
                      e-Factura cross-reference.
        """
        try:
            from accounting.bugetare.invoice_parser import (
                parse_invoice_with_template_from_bytes, auto_detect_and_parse,
            )

            if template_id:
                from accounting.templates.repositories import TemplateRepository
                template = TemplateRepository().get(template_id)
                if not template:
                    return ServiceResult(success=False, error='Template not found', status_code=404)
                result = parse_invoice_with_template_from_bytes(file_bytes, filename, template)
                result['auto_detected_template'] = None
                result['auto_detected_template_id'] = None
            else:
                from accounting.templates.repositories import TemplateRepository
                templates = TemplateRepository().get_all()
                result = auto_detect_and_parse(file_bytes, filename, templates)

            result['drive_link'] = None

            # Currency conversion
            try:
                from core.services.currency_converter import get_eur_ron_conversion
                if result.get('invoice_value') and result.get('currency') and result.get('invoice_date'):
                    conversion = get_eur_ron_conversion(
                        float(result['invoice_value']),
                        result['currency'],
                        result['invoice_date'],
                    )
                    result['value_ron'] = conversion.get('value_ron')
                    result['value_eur'] = conversion.get('value_eur')
                    result['exchange_rate'] = conversion.get('exchange_rate')
                else:
                    result['value_ron'] = None
                    result['value_eur'] = None
                    result['exchange_rate'] = None
            except (ImportError, Exception):
                result['value_ron'] = None
                result['value_eur'] = None
                result['exchange_rate'] = None

            # e-Factura cross-reference
            match = self._find_efactura_match(
                result.get('invoice_number', ''),
                result.get('supplier_vat', ''),
                result.get('supplier', ''),
            )
            if match:
                result['efactura_match'] = match

            from database import refresh_connection_pool
            refresh_connection_pool()

            return ServiceResult(success=True, data=result)

        except Exception as e:
            logger.error(f"Invoice parse failed: {e}", exc_info=True)
            return ServiceResult(success=False, error=str(e), status_code=500)

    def update_invoice(self, invoice_id: int, data: Dict[str, Any],
                       user: UserContext) -> ServiceResult:
        """Update an invoice with status permission checks and notifications.

        Orchestrates: permission check -> repo update -> status change
                      notification -> payment status logging.
        """
        try:
            current_invoice = self.invoice_repo.get_with_allocations(invoice_id)
            if not current_invoice:
                return ServiceResult(success=False, error='Invoice not found', status_code=404)

            old_status = current_invoice.get('status')
            old_payment_status = current_invoice.get('payment_status')
            new_status = data.get('status')
            new_payment_status = data.get('payment_status')

            if new_status and new_status != old_status:
                if not self._user_can_set_status(user.role_name, new_status, 'invoice_status'):
                    return ServiceResult(
                        success=False,
                        error=f'Permission denied: Your role cannot set status to "{new_status}"',
                        status_code=403,
                    )

            if new_payment_status and new_payment_status != old_payment_status:
                if not self._user_can_set_status(user.role_name, new_payment_status, 'payment_status'):
                    return ServiceResult(
                        success=False,
                        error=f'Permission denied: Your role cannot set payment status to "{new_payment_status}"',
                        status_code=403,
                    )

            updated = self.invoice_repo.update(
                invoice_id=invoice_id,
                supplier=data.get('supplier'),
                invoice_number=data.get('invoice_number'),
                invoice_date=data.get('invoice_date'),
                invoice_value=float(data['invoice_value']) if data.get('invoice_value') else None,
                currency=data.get('currency'),
                drive_link=data.get('drive_link'),
                comment=data.get('comment'),
                status=new_status,
                payment_status=new_payment_status,
                subtract_vat=data.get('subtract_vat'),
                vat_rate=float(data['vat_rate']) if data.get('vat_rate') else None,
                net_value=float(data['net_value']) if data.get('net_value') else None,
            )

            if not updated:
                return ServiceResult(success=False, error='Invoice not found or no changes made', status_code=404)

            # Status change handling
            if new_status is not None and old_status != new_status:
                self._log_event(
                    user, 'status_changed',
                    f'Invoice #{current_invoice.get("invoice_number", invoice_id)} '
                    f'status changed from "{old_status}" to "{new_status}"',
                    entity_type='invoice', entity_id=invoice_id,
                    details={'old_status': old_status, 'new_status': new_status},
                )
                self._notify_on_status_change(new_status, current_invoice)

            if new_payment_status is not None and old_payment_status != new_payment_status:
                self._log_event(
                    user, 'payment_status_changed',
                    f'Invoice #{current_invoice.get("invoice_number", invoice_id)} '
                    f'payment status changed from "{old_payment_status}" to "{new_payment_status}"',
                    entity_type='invoice', entity_id=invoice_id,
                    details={'old_payment_status': old_payment_status, 'new_payment_status': new_payment_status},
                )

            self._log_event(user, 'invoice_updated', f'Updated invoice ID {invoice_id}',
                            entity_type='invoice', entity_id=invoice_id)

            return ServiceResult(success=True, data={'success': True})

        except Exception as e:
            logger.error(f"Invoice update failed: {e}", exc_info=True)
            return ServiceResult(success=False, error=str(e), status_code=500)

    def update_allocations(self, invoice_id: int, allocations: List[Dict],
                           send_notification: bool, user: UserContext) -> ServiceResult:
        """Update allocations with validation, auto-status, and notifications.

        Orchestrates: validation -> repo update -> auto-status normalization ->
                      conditional email notification.
        """
        total_percent = sum(float(a.get('allocation_percent', 0)) for a in allocations)
        if abs(total_percent - 100) > 1.0:
            return ServiceResult(
                success=False,
                error=f'Allocations must sum to 100%, got {round(total_percent, 2)}%',
                status_code=400,
            )

        try:
            self.allocation_repo.update_invoice_allocations(invoice_id, allocations)

            # Auto-set status to first invoice_status option
            current_invoice = self.invoice_repo.get_with_allocations(invoice_id)
            old_status = current_invoice.get('status') if current_invoice else None
            from core.settings.dropdowns.repositories import DropdownRepository
            status_options = DropdownRepository().get_options('invoice_status', active_only=True)
            default_status = status_options[0]['value'] if status_options else None
            if default_status and old_status != default_status:
                self.invoice_repo.update(invoice_id, status=default_status)
                self._log_event(
                    user, 'status_changed',
                    f'Invoice #{current_invoice.get("invoice_number", invoice_id)} '
                    f'status auto-changed to "{default_status}" after allocation edit',
                    entity_type='invoice', entity_id=invoice_id,
                    details={'old_status': old_status, 'new_status': default_status},
                )

            notifications_sent = 0
            if send_notification and current_invoice:
                notifications_sent = self._notify_allocations(
                    invoice_data={
                        'id': invoice_id,
                        'invoice_number': current_invoice.get('invoice_number'),
                        'supplier': current_invoice.get('supplier'),
                        'invoice_date': current_invoice.get('invoice_date'),
                        'invoice_value': current_invoice.get('invoice_value'),
                        'currency': current_invoice.get('currency', 'RON'),
                    },
                    distributions=allocations,
                )

            self._log_event(user, 'allocations_updated',
                            f'Updated allocations for invoice ID {invoice_id}',
                            entity_type='invoice', entity_id=invoice_id)

            return ServiceResult(success=True, data={
                'success': True,
                'notifications_sent': notifications_sent,
            })

        except Exception as e:
            logger.error(f"Allocation update failed: {e}", exc_info=True)
            return ServiceResult(success=False, error=str(e), status_code=500)

    def permanently_delete(self, invoice_id: int, user: UserContext) -> ServiceResult:
        """Permanently delete invoice and its Google Drive file."""
        drive_link = self.invoice_repo.get_drive_link(invoice_id)

        if not self.invoice_repo.permanently_delete(invoice_id):
            return ServiceResult(success=False, error='Invoice not found', status_code=404)

        drive_deleted = False
        if drive_link:
            try:
                from core.services.drive_service import delete_file_from_drive
                drive_deleted = delete_file_from_drive(drive_link)
            except ImportError:
                pass

        self._log_event(user, 'invoice_permanently_deleted',
                        f'Permanently deleted invoice ID {invoice_id}',
                        entity_type='invoice', entity_id=invoice_id)

        return ServiceResult(success=True, data={
            'success': True, 'drive_deleted': drive_deleted,
        })

    def bulk_permanently_delete(self, invoice_ids: List[int],
                                user: UserContext) -> ServiceResult:
        """Permanently delete multiple invoices and their Drive files."""
        drive_links = self.invoice_repo.get_drive_links(invoice_ids)
        count = self.invoice_repo.bulk_permanently_delete(invoice_ids)

        drive_deleted_count = 0
        if drive_links:
            try:
                from core.services.drive_service import delete_files_from_drive
                drive_deleted_count = delete_files_from_drive(drive_links)
            except ImportError:
                pass

        return ServiceResult(success=True, data={
            'success': True, 'deleted_count': count,
            'drive_deleted_count': drive_deleted_count,
        })

    # ============== Private Helpers ==============

    def _log_event(self, user: UserContext, event_type: str,
                   description: str = None, entity_type: str = None,
                   entity_id: int = None, details: dict = None):
        """Log an event with user context (no Flask dependency)."""
        from core.auth.repositories import EventRepository
        EventRepository().log_event(
            event_type=event_type,
            event_description=description,
            user_id=user.user_id,
            user_email=user.user_email,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=user.ip_address,
            user_agent=user.user_agent,
            details=details,
        )

    def _user_can_set_status(self, role_name: str, status_value: str,
                             dropdown_type: str = 'invoice_status') -> bool:
        """Check if a user's role meets the min_role requirement for a status."""
        from core.settings.dropdowns.repositories import DropdownRepository
        options = DropdownRepository().get_options(dropdown_type, active_only=True)
        status_option = next((opt for opt in options if opt['value'] == status_value), None)
        if not status_option:
            return False
        min_role = status_option.get('min_role')
        if not min_role:
            return True
        user_level = ROLE_HIERARCHY.index(role_name) if role_name in ROLE_HIERARCHY else -1
        min_level = ROLE_HIERARCHY.index(min_role) if min_role in ROLE_HIERARCHY else 0
        return user_level >= min_level

    def _notify_allocations(self, invoice_data: Dict, distributions: List[Dict]) -> int:
        """Send email notifications for invoice allocations. Returns count sent."""
        try:
            from core.services.notification_service import notify_invoice_allocations, is_smtp_configured
            if is_smtp_configured():
                results = notify_invoice_allocations(invoice_data, distributions)
                return sum(1 for r in results if r.get('success'))
        except ImportError:
            pass
        return 0

    def _notify_on_status_change(self, new_status: str, invoice: Dict):
        """Send notifications if the new status is configured to notify."""
        try:
            from core.settings.dropdowns.repositories import DropdownRepository
            if not DropdownRepository().should_notify_on_status(new_status, 'invoice_status'):
                return
            from core.services.notification_service import notify_invoice_allocations, is_smtp_configured
            if not is_smtp_configured():
                return
            allocations = invoice.get('allocations', [])
            if not allocations:
                return
            invoice_data = {
                'supplier': invoice.get('supplier'),
                'invoice_number': invoice.get('invoice_number'),
                'invoice_date': invoice.get('invoice_date'),
                'invoice_value': invoice.get('invoice_value'),
                'currency': invoice.get('currency'),
                'drive_link': invoice.get('drive_link'),
                'status': new_status,
            }
            notify_invoice_allocations(invoice_data, allocations)
        except ImportError:
            pass

    def _track_corrections(self, data: Dict, invoice_id: int, user: UserContext):
        """Compare AI parse result vs submitted values and log corrections."""
        parse_result = data.get('_parse_result')
        if not parse_result or not data.get('invoice_template'):
            return
        corrections = {}
        if parse_result.get('supplier') and parse_result['supplier'] != data['supplier']:
            corrections['supplier'] = {'parsed': parse_result['supplier'], 'submitted': data['supplier']}
        if parse_result.get('invoice_number') and parse_result['invoice_number'] != data['invoice_number']:
            corrections['invoice_number'] = {'parsed': parse_result['invoice_number'], 'submitted': data['invoice_number']}
        if parse_result.get('invoice_value') and float(parse_result['invoice_value']) != float(data['invoice_value']):
            corrections['invoice_value'] = {'parsed': parse_result['invoice_value'], 'submitted': data['invoice_value']}
        if corrections:
            self._log_event(
                user, 'parse_correction',
                f'User corrected {len(corrections)} field(s) from template parse: {", ".join(corrections.keys())}',
                entity_type='invoice', entity_id=invoice_id,
                details={'corrections': corrections, 'template': data.get('invoice_template')},
            )

    def _link_efactura(self, efactura_match_id: int, invoice_id: int):
        """Auto-link to e-Factura record if match ID provided."""
        try:
            from core.connectors.efactura.repositories.invoice_repo import InvoiceRepository as EfacturaInvoiceRepo
            EfacturaInvoiceRepo().mark_allocated(efactura_match_id, invoice_id)
        except Exception:
            pass

    def _auto_tag(self, invoice_id: int, user_id: int):
        """Fire-and-forget auto-tag rule evaluation."""
        try:
            from core.tags.auto_tag_service import AutoTagService
            AutoTagService().evaluate_rules_for_entity('invoice', invoice_id, user_id)
        except Exception:
            pass

    def _find_efactura_match(self, invoice_number: str, supplier_vat: str,
                             supplier_name: str) -> Optional[Dict]:
        """Find matching e-Factura record by invoice number + supplier."""
        if not invoice_number:
            return None
        try:
            from database import get_db, get_cursor, release_db
            conn = get_db()
            try:
                cur = get_cursor(conn)
                cur.execute('''
                    SELECT id, partner_name, partner_cif, invoice_number, issue_date,
                           total_amount, currency, jarvis_invoice_id
                    FROM efactura_invoices
                    WHERE deleted_at IS NULL AND invoice_number = %s
                      AND (partner_cif = %s OR LOWER(partner_name) = LOWER(%s))
                    LIMIT 1
                ''', (invoice_number, supplier_vat, supplier_name))
                match = cur.fetchone()
                if match:
                    return {
                        'id': match['id'],
                        'partner_name': match['partner_name'],
                        'partner_cif': match['partner_cif'],
                        'invoice_number': match['invoice_number'],
                        'issue_date': str(match['issue_date']) if match['issue_date'] else None,
                        'total_amount': float(match['total_amount']) if match['total_amount'] else None,
                        'currency': match['currency'],
                        'jarvis_invoice_id': match['jarvis_invoice_id'],
                    }
            finally:
                release_db(conn)
        except Exception:
            pass
        return None
