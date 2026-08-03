"""
Invoice Visibility Service - hidden and deleted invoice management.
"""
from typing import Optional, List, Dict, Any
from datetime import date

from core.utils.logging_config import get_logger
from core.organization.repositories import CompanyRepository as _CompanyRepo
from ..config import InvoiceDirection
from ..repositories import EFacturaInvoiceRepository
from .base import ServiceResult, _iso

logger = get_logger('jarvis.core.connectors.efactura.invoice_visibility_service')

_company_repo = _CompanyRepo()
get_companies_with_vat = _company_repo.get_all_with_vat_and_brands


class InvoiceVisibilityService:
    def __init__(self):
        self.invoice_repo = EFacturaInvoiceRepository()

    def list_hidden_invoices(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> ServiceResult:
        """List hidden (ignored) invoices."""
        offset = (page - 1) * limit

        invoices, total = self.invoice_repo.list_hidden(
            cif_owner=cif_owner,
            company_id=company_id,
            direction=direction,
            start_date=start_date,
            end_date=end_date,
            search=search,
            limit=limit,
            offset=offset,
        )

        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        return ServiceResult(success=True, data={
            'invoices': [
                {
                    'id': inv['id'],
                    'company_name': None,  # Could add lookup if needed
                    'direction': inv['direction'].value if hasattr(inv['direction'], 'value') else inv['direction'],
                    'partner_name': inv['partner_name'],
                    'partner_cif': inv['partner_cif'],
                    'invoice_number': inv['invoice_number'],
                    'invoice_series': inv['invoice_series'],
                    'issue_date': _iso(inv.get('issue_date')),
                    'total_amount': str(inv['total_amount']),
                    'total_vat': str(inv['total_vat']),
                    'total_without_vat': str(inv.get('total_without_vat', 0)),
                    'due_date': _iso(inv.get('due_date')),
                    'currency': inv['currency'],
                    'created_at': _iso(inv.get('created_at')),
                    'type_name': inv.get('type_name'),
                    'type_names': inv.get('type_names', []),
                }
                for inv in invoices
            ],
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': page < total_pages,
            },
        })

    def get_hidden_count(self) -> int:
        """Get count of hidden invoices for badge."""
        return self.invoice_repo.count_hidden()

    def bulk_hide_invoices(self, invoice_ids: List[int]) -> ServiceResult:
        """Hide multiple invoices."""
        count = self.invoice_repo.bulk_hide(invoice_ids)
        return ServiceResult(success=True, data={'hidden': count})

    def bulk_restore_from_hidden(self, invoice_ids: List[int]) -> ServiceResult:
        """Restore multiple invoices from hidden."""
        count = self.invoice_repo.bulk_restore_from_hidden(invoice_ids)
        return ServiceResult(success=True, data={'restored': count})

    def list_deleted_invoices(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> ServiceResult:
        """List deleted invoices (bin)."""
        offset = (page - 1) * limit

        invoices, total = self.invoice_repo.list_deleted(
            cif_owner=cif_owner,
            company_id=company_id,
            direction=direction,
            start_date=start_date,
            end_date=end_date,
            search=search,
            limit=limit,
            offset=offset,
        )

        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        # Company id -> name map so the Bin can show/filter by company (mirrors Unallocated)
        companies = get_companies_with_vat()
        company_map = {c['id']: c['company'] for c in companies}

        return ServiceResult(success=True, data={
            'invoices': [
                {
                    'id': inv.get('id'),
                    'direction': inv.get('direction').value if hasattr(inv.get('direction'), 'value') else inv.get('direction'),
                    'partner_name': inv.get('partner_name'),
                    'partner_cif': inv.get('partner_cif'),
                    'invoice_number': inv.get('invoice_number'),
                    'invoice_series': inv.get('invoice_series'),
                    'issue_date': _iso(inv.get('issue_date')),
                    'total_amount': str(inv.get('total_amount', 0)),
                    'total_vat': str(inv.get('total_vat', 0)),
                    'currency': inv.get('currency'),
                    'company_id': inv.get('company_id'),
                    'company_name': company_map.get(inv.get('company_id')),
                    'cif_owner': inv.get('cif_owner'),
                    'created_at': _iso(inv.get('created_at')),
                    'deleted_at': _iso(inv.get('deleted_at')),
                    'type_name': inv.get('type_name'),
                    'type_names': inv.get('type_names', []),
                }
                for inv in invoices
            ],
            'companies': [{'id': c['id'], 'name': c['company']} for c in companies],
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': page < total_pages,
            },
        })

    def get_bin_count(self) -> int:
        """Get count of deleted invoices for badge."""
        return self.invoice_repo.count_deleted()

    def delete_invoice(self, invoice_id: int) -> ServiceResult:
        """Move an invoice to the bin."""
        invoice = self.invoice_repo.get_by_id(invoice_id)
        if not invoice:
            return ServiceResult(success=False, error=f"Invoice {invoice_id} not found")

        success = self.invoice_repo.delete_invoice(invoice_id)
        if success:
            return ServiceResult(success=True, data={'invoice_id': invoice_id})
        else:
            return ServiceResult(success=False, error="Failed to delete invoice")

    def restore_from_bin(self, invoice_id: int) -> ServiceResult:
        """Restore an invoice from the bin."""
        success = self.invoice_repo.restore_from_bin(invoice_id)
        if success:
            return ServiceResult(success=True, data={'invoice_id': invoice_id})
        else:
            return ServiceResult(success=False, error="Invoice not found in bin")

    def permanent_delete(self, invoice_id: int) -> ServiceResult:
        """Permanently delete an invoice from the bin."""
        success = self.invoice_repo.permanent_delete(invoice_id)
        if success:
            return ServiceResult(success=True, data={'invoice_id': invoice_id})
        else:
            return ServiceResult(success=False, error="Invoice not found in bin")

    def bulk_delete_invoices(self, invoice_ids: List[int]) -> ServiceResult:
        """Move multiple invoices to the bin."""
        count = self.invoice_repo.bulk_delete(invoice_ids)
        return ServiceResult(success=True, data={'deleted': count})

    def bulk_restore_from_bin(self, invoice_ids: List[int]) -> ServiceResult:
        """Restore multiple invoices from the bin."""
        count = self.invoice_repo.bulk_restore_from_bin(invoice_ids)
        return ServiceResult(success=True, data={'restored': count})

    def bulk_permanent_delete(self, invoice_ids: List[int]) -> ServiceResult:
        """Permanently delete multiple invoices from the bin."""
        count = self.invoice_repo.bulk_permanent_delete(invoice_ids)
        return ServiceResult(success=True, data={'deleted': count})

    def cleanup_old_unallocated(self, days: int = 15, cif_owner: str = None) -> ServiceResult:
        """Permanently delete unallocated invoices older than N days."""
        count = self.invoice_repo.delete_old_unallocated(days=days, cif_owner=cif_owner)
        return ServiceResult(success=True, data={'deleted': count})
