"""
Invoice Service - Business logic for invoice operations.

Provides a clean service layer API for invoice management,
wrapping the database functions with proper business logic.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from decimal import Decimal

from core.utils.logging_config import get_logger
from database import (
    get_all_invoices,
    get_invoice_with_allocations,
    get_invoices_with_allocations,
    search_invoices,
    get_summary_by_company,
    get_summary_by_department,
    get_summary_by_brand,
    get_summary_by_supplier,
    delete_invoice,
    restore_invoice,
    update_invoice,
    save_invoice,
    update_invoice_allocations,
    check_invoice_number_exists,
    bulk_soft_delete_invoices,
    bulk_restore_invoices,
    permanently_delete_invoice,
    bulk_permanently_delete_invoices,
    get_invoice_drive_link,
    get_invoice_drive_links,
    update_allocation_comment,
)

logger = get_logger('jarvis.core.services.invoice')


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class InvoiceService:
    """
    Service for invoice operations.

    Coordinates invoice CRUD, allocations, search, and summaries.
    """

    # ============== List & Get ==============

    def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        company: Optional[str] = None,
        brand: Optional[str] = None,
        department: Optional[str] = None,
        subdepartment: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
        payment_status: Optional[str] = None,
        include_deleted: bool = False,
        include_allocations: bool = False,
    ) -> ServiceResult:
        """
        Get all invoices with optional filters.

        Args:
            limit: Max number of invoices to return
            offset: Pagination offset
            company: Filter by company name
            brand: Filter by brand
            department: Filter by department
            subdepartment: Filter by subdepartment
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)
            status: Filter by invoice status
            payment_status: Filter by payment status
            include_deleted: Include soft-deleted invoices
            include_allocations: Include allocation details

        Returns:
            ServiceResult with list of invoices
        """
        try:
            if include_allocations:
                invoices = get_invoices_with_allocations(
                    limit=limit,
                    offset=offset,
                    company=company,
                    brand=brand,
                    department=department,
                    subdepartment=subdepartment,
                    start_date=start_date,
                    end_date=end_date,
                    status=status,
                    payment_status=payment_status,
                    include_deleted=include_deleted,
                )
            else:
                invoices = get_all_invoices(
                    limit=limit,
                    offset=offset,
                    company=company,
                    brand=brand,
                    department=department,
                    subdepartment=subdepartment,
                    start_date=start_date,
                    end_date=end_date,
                    status=status,
                    payment_status=payment_status,
                    include_deleted=include_deleted,
                )

            return ServiceResult(success=True, data=invoices)

        except Exception as e:
            logger.error(f"Error getting invoices: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_by_id(self, invoice_id: int) -> ServiceResult:
        """
        Get a single invoice with allocations.

        Args:
            invoice_id: Invoice ID

        Returns:
            ServiceResult with invoice data or error
        """
        try:
            invoice = get_invoice_with_allocations(invoice_id)

            if invoice is None:
                return ServiceResult(success=False, error="Invoice not found")

            return ServiceResult(success=True, data=invoice)

        except Exception as e:
            logger.error(f"Error getting invoice {invoice_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_drive_link(self, invoice_id: int) -> ServiceResult:
        """Get Google Drive link for an invoice."""
        try:
            link = get_invoice_drive_link(invoice_id)
            return ServiceResult(success=True, data={'link': link})
        except Exception as e:
            logger.error(f"Error getting drive link: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_drive_links(self, invoice_ids: List[int]) -> ServiceResult:
        """Get Google Drive links for multiple invoices."""
        try:
            links = get_invoice_drive_links(invoice_ids)
            return ServiceResult(success=True, data={'links': links})
        except Exception as e:
            logger.error(f"Error getting drive links: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Create & Update ==============

    def create(
        self,
        supplier: str,
        supplier_vat: str,
        invoice_number: str,
        invoice_date: str,
        invoice_value: float,
        currency: str,
        dedicated_to: str,
        allocations: List[Dict],
        drive_link: Optional[str] = None,
        customer_vat: Optional[str] = None,
        subtract_vat: bool = False,
        vat_rate_id: Optional[int] = None,
        net_value: Optional[float] = None,
        user_id: Optional[int] = None,
    ) -> ServiceResult:
        """
        Create a new invoice with allocations.

        Args:
            supplier: Supplier name
            supplier_vat: Supplier VAT number
            invoice_number: Invoice number
            invoice_date: Invoice date (YYYY-MM-DD)
            invoice_value: Total invoice value
            currency: Currency code (RON, EUR, etc.)
            dedicated_to: Company name (dedicated to)
            allocations: List of allocation dicts
            drive_link: Optional Google Drive link
            customer_vat: Customer VAT number
            subtract_vat: Whether to subtract VAT
            vat_rate_id: VAT rate ID if subtracting
            net_value: Net value after VAT
            user_id: ID of user creating the invoice

        Returns:
            ServiceResult with new invoice ID
        """
        try:
            invoice_id = save_invoice(
                supplier=supplier,
                supplier_vat=supplier_vat,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                invoice_value=invoice_value,
                currency=currency,
                dedicated_to=dedicated_to,
                allocations=allocations,
                drive_link=drive_link,
                customer_vat=customer_vat,
                subtract_vat=subtract_vat,
                vat_rate_id=vat_rate_id,
                net_value=net_value,
                user_id=user_id,
            )

            if invoice_id:
                logger.info(
                    "Invoice created",
                    extra={'invoice_id': invoice_id, 'supplier': supplier}
                )
                return ServiceResult(success=True, data={'invoice_id': invoice_id})
            else:
                return ServiceResult(success=False, error="Failed to create invoice")

        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            return ServiceResult(success=False, error=str(e))

    def update(
        self,
        invoice_id: int,
        supplier: str,
        supplier_vat: str,
        invoice_number: str,
        invoice_date: str,
        invoice_value: float,
        currency: str,
        dedicated_to: str,
        customer_vat: Optional[str] = None,
        subtract_vat: bool = False,
        vat_rate_id: Optional[int] = None,
        net_value: Optional[float] = None,
        drive_link: Optional[str] = None,
    ) -> ServiceResult:
        """
        Update an existing invoice (without allocations).

        Args:
            invoice_id: Invoice ID
            supplier: Supplier name
            supplier_vat: Supplier VAT number
            invoice_number: Invoice number
            invoice_date: Invoice date
            invoice_value: Total value
            currency: Currency code
            dedicated_to: Company name
            customer_vat: Customer VAT
            subtract_vat: Whether to subtract VAT
            vat_rate_id: VAT rate ID
            net_value: Net value
            drive_link: Google Drive link

        Returns:
            ServiceResult with success status
        """
        try:
            success = update_invoice(
                invoice_id=invoice_id,
                supplier=supplier,
                supplier_vat=supplier_vat,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                invoice_value=invoice_value,
                currency=currency,
                dedicated_to=dedicated_to,
                customer_vat=customer_vat,
                subtract_vat=subtract_vat,
                vat_rate_id=vat_rate_id,
                net_value=net_value,
                drive_link=drive_link,
            )

            if success:
                logger.info("Invoice updated", extra={'invoice_id': invoice_id})
                return ServiceResult(success=True)
            else:
                return ServiceResult(success=False, error="Failed to update invoice")

        except Exception as e:
            logger.error(f"Error updating invoice {invoice_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_allocations(
        self,
        invoice_id: int,
        allocations: List[Dict],
    ) -> ServiceResult:
        """
        Update allocations for an invoice.

        Args:
            invoice_id: Invoice ID
            allocations: List of allocation dicts

        Returns:
            ServiceResult with success status
        """
        try:
            success = update_invoice_allocations(invoice_id, allocations)

            if success:
                logger.info("Allocations updated", extra={'invoice_id': invoice_id})
                return ServiceResult(success=True)
            else:
                return ServiceResult(success=False, error="Failed to update allocations")

        except Exception as e:
            logger.error(f"Error updating allocations for {invoice_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_allocation_comment(
        self,
        allocation_id: int,
        comment: str,
    ) -> ServiceResult:
        """Update comment for a specific allocation."""
        try:
            success = update_allocation_comment(allocation_id, comment)

            if success:
                return ServiceResult(success=True)
            else:
                return ServiceResult(success=False, error="Failed to update comment")

        except Exception as e:
            logger.error(f"Error updating allocation comment: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Delete & Restore ==============

    def soft_delete(self, invoice_id: int) -> ServiceResult:
        """
        Soft delete an invoice (move to bin).

        Args:
            invoice_id: Invoice ID

        Returns:
            ServiceResult with success status
        """
        try:
            success = delete_invoice(invoice_id)

            if success:
                logger.info("Invoice soft deleted", extra={'invoice_id': invoice_id})
                return ServiceResult(success=True)
            else:
                return ServiceResult(success=False, error="Invoice not found")

        except Exception as e:
            logger.error(f"Error soft deleting invoice {invoice_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def restore(self, invoice_id: int) -> ServiceResult:
        """
        Restore a soft-deleted invoice.

        Args:
            invoice_id: Invoice ID

        Returns:
            ServiceResult with success status
        """
        try:
            success = restore_invoice(invoice_id)

            if success:
                logger.info("Invoice restored", extra={'invoice_id': invoice_id})
                return ServiceResult(success=True)
            else:
                return ServiceResult(success=False, error="Invoice not found")

        except Exception as e:
            logger.error(f"Error restoring invoice {invoice_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def permanent_delete(self, invoice_id: int) -> ServiceResult:
        """
        Permanently delete an invoice (cannot be restored).

        Args:
            invoice_id: Invoice ID

        Returns:
            ServiceResult with success status
        """
        try:
            success = permanently_delete_invoice(invoice_id)

            if success:
                logger.info("Invoice permanently deleted", extra={'invoice_id': invoice_id})
                return ServiceResult(success=True)
            else:
                return ServiceResult(success=False, error="Invoice not found")

        except Exception as e:
            logger.error(f"Error permanently deleting invoice {invoice_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Bulk Operations ==============

    def bulk_soft_delete(self, invoice_ids: List[int]) -> ServiceResult:
        """
        Soft delete multiple invoices.

        Args:
            invoice_ids: List of invoice IDs

        Returns:
            ServiceResult with count of deleted invoices
        """
        try:
            count = bulk_soft_delete_invoices(invoice_ids)
            logger.info(f"Bulk soft deleted {count} invoices")
            return ServiceResult(success=True, data={'deleted_count': count})

        except Exception as e:
            logger.error(f"Error bulk soft deleting: {e}")
            return ServiceResult(success=False, error=str(e))

    def bulk_restore(self, invoice_ids: List[int]) -> ServiceResult:
        """
        Restore multiple soft-deleted invoices.

        Args:
            invoice_ids: List of invoice IDs

        Returns:
            ServiceResult with count of restored invoices
        """
        try:
            count = bulk_restore_invoices(invoice_ids)
            logger.info(f"Bulk restored {count} invoices")
            return ServiceResult(success=True, data={'restored_count': count})

        except Exception as e:
            logger.error(f"Error bulk restoring: {e}")
            return ServiceResult(success=False, error=str(e))

    def bulk_permanent_delete(self, invoice_ids: List[int]) -> ServiceResult:
        """
        Permanently delete multiple invoices.

        Args:
            invoice_ids: List of invoice IDs

        Returns:
            ServiceResult with count of deleted invoices
        """
        try:
            count = bulk_permanently_delete_invoices(invoice_ids)
            logger.info(f"Bulk permanently deleted {count} invoices")
            return ServiceResult(success=True, data={'deleted_count': count})

        except Exception as e:
            logger.error(f"Error bulk permanent deleting: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Search ==============

    def search(
        self,
        query: str,
        filters: Optional[Dict] = None,
    ) -> ServiceResult:
        """
        Search invoices by query string.

        Args:
            query: Search query
            filters: Optional filters dict

        Returns:
            ServiceResult with list of matching invoices
        """
        try:
            invoices = search_invoices(query, filters)
            return ServiceResult(success=True, data=invoices)

        except Exception as e:
            logger.error(f"Error searching invoices: {e}")
            return ServiceResult(success=False, error=str(e))

    def check_invoice_number_exists(
        self,
        supplier_vat: str,
        invoice_number: str,
        exclude_id: Optional[int] = None,
    ) -> ServiceResult:
        """
        Check if an invoice number already exists for a supplier.

        Args:
            supplier_vat: Supplier VAT number
            invoice_number: Invoice number to check
            exclude_id: Invoice ID to exclude (for updates)

        Returns:
            ServiceResult with exists boolean
        """
        try:
            exists = check_invoice_number_exists(supplier_vat, invoice_number, exclude_id)
            return ServiceResult(success=True, data={'exists': exists})

        except Exception as e:
            logger.error(f"Error checking invoice number: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Summaries ==============

    def get_summary_by_company(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> ServiceResult:
        """Get invoice summary grouped by company."""
        try:
            summary = get_summary_by_company(start_date, end_date)
            return ServiceResult(success=True, data=summary)

        except Exception as e:
            logger.error(f"Error getting company summary: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_summary_by_department(
        self,
        company: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> ServiceResult:
        """Get invoice summary grouped by department."""
        try:
            summary = get_summary_by_department(company, start_date, end_date)
            return ServiceResult(success=True, data=summary)

        except Exception as e:
            logger.error(f"Error getting department summary: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_summary_by_brand(
        self,
        company: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> ServiceResult:
        """Get invoice summary grouped by brand."""
        try:
            summary = get_summary_by_brand(company, start_date, end_date)
            return ServiceResult(success=True, data=summary)

        except Exception as e:
            logger.error(f"Error getting brand summary: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_summary_by_supplier(
        self,
        company: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> ServiceResult:
        """Get invoice summary grouped by supplier."""
        try:
            summary = get_summary_by_supplier(company, start_date, end_date)
            return ServiceResult(success=True, data=summary)

        except Exception as e:
            logger.error(f"Error getting supplier summary: {e}")
            return ServiceResult(success=False, error=str(e))
