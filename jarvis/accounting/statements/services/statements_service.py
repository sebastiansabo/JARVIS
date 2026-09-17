"""Statements Service - Business logic for Bank Statements module.

This module contains all business logic related to bank statements.
Routes should call these methods instead of accessing the database directly.
"""
import hashlib
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from ..repositories import (
    StatementRepository,
    TransactionRepository,
    VendorMappingRepository,
)
from ..parser import parse_statement
from ..vendors import match_transactions, reload_patterns

logger = logging.getLogger('jarvis.statements.service')


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class StatementsService:
    """Service for bank statements business logic.

    Coordinates all statement operations through the repository layer.
    """

    def __init__(self):
        self.statement_repo = StatementRepository()
        self.transaction_repo = TransactionRepository()
        self.mapping_repo = VendorMappingRepository()

    # ============== Statement Processing ==============

    def process_statement(self, pdf_bytes: bytes, filename: str, user_id: int) -> ServiceResult:
        """Process a single PDF statement file.

        Args:
            pdf_bytes: Raw PDF content
            filename: Original filename
            user_id: ID of the uploading user

        Returns:
            ServiceResult with processing details
        """
        try:
            # Calculate file hash for duplicate detection
            file_hash = hashlib.md5(pdf_bytes).hexdigest()

            # Check if this exact file was already uploaded
            existing = self.statement_repo.check_duplicate(file_hash)
            if existing:
                return ServiceResult(
                    success=True,
                    data={
                        'filename': filename,
                        'error': f'This file was already uploaded on {existing["uploaded_at"]}',
                        'existing_statement_id': existing['id'],
                        'skipped': True
                    }
                )

            # Ensure vendor mappings are seeded
            self.mapping_repo.seed_defaults()

            # Parse the statement
            parsed = parse_statement(pdf_bytes, filename)

            # Match transactions to vendors
            transactions = match_transactions(parsed['transactions'])

            # Create statement record
            period = parsed.get('period', {})
            statement_id = self.statement_repo.create(
                filename=filename,
                file_hash=file_hash,
                company_name=parsed.get('company_name'),
                company_cui=parsed.get('company_cui'),
                account_number=parsed.get('account_number'),
                period_from=period.get('from'),
                period_to=period.get('to'),
                total_transactions=len(transactions),
                uploaded_by=user_id
            )

            # Save transactions with duplicate detection
            save_result = self.transaction_repo.save_with_dedup(transactions, statement_id)

            # Update statement with actual counts
            self.statement_repo.update(
                statement_id,
                new_transactions=save_result['new_count'],
                duplicate_transactions=save_result['duplicate_count']
            )

            # Count vendor-matched (has supplier) - for reporting
            vendor_matched_count = sum(1 for t in transactions if t.get('matched_supplier'))

            return ServiceResult(
                success=True,
                data={
                    'filename': filename,
                    'statement_id': statement_id,
                    'company_name': parsed.get('company_name'),
                    'company_cui': parsed.get('company_cui'),
                    'total_transactions': len(transactions),
                    'new_transactions': save_result['new_count'],
                    'duplicate_transactions': save_result['duplicate_count'],
                    'vendor_matched_count': vendor_matched_count,
                    'invoice_matched_count': 0,  # auto-match removed; invoices are linked manually
                    'period': period,
                    'summary': parsed.get('summary')
                }
            )

        except Exception as e:
            logger.exception(f'Error processing statement {filename}')
            return ServiceResult(success=False, error=str(e))

    # ============== Statements ==============

    def get_all_statements(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get all statements with pagination.

        Args:
            limit: Maximum results
            offset: Pagination offset

        Returns:
            Dict with statements list and total count
        """
        statements = self.statement_repo.get_all(limit=limit, offset=offset)
        total = self.statement_repo.get_count()

        # Convert dates to strings for JSON
        for stmt in statements:
            if stmt.get('period_from'):
                stmt['period_from'] = str(stmt['period_from'])
            if stmt.get('period_to'):
                stmt['period_to'] = str(stmt['period_to'])
            if stmt.get('uploaded_at'):
                stmt['uploaded_at'] = str(stmt['uploaded_at'])

        return {
            'statements': statements,
            'total': total,
            'limit': limit,
            'offset': offset
        }

    def get_statement(self, statement_id: int) -> Optional[Dict[str, Any]]:
        """Get a single statement by ID."""
        stmt = self.statement_repo.get_by_id(statement_id)
        if stmt:
            # Convert dates to strings
            if stmt.get('period_from'):
                stmt['period_from'] = str(stmt['period_from'])
            if stmt.get('period_to'):
                stmt['period_to'] = str(stmt['period_to'])
            if stmt.get('uploaded_at'):
                stmt['uploaded_at'] = str(stmt['uploaded_at'])
        return stmt

    def delete_statement(self, statement_id: int) -> ServiceResult:
        """Delete a statement and all its transactions."""
        stmt = self.statement_repo.get_by_id(statement_id)
        if not stmt:
            return ServiceResult(success=False, error='Statement not found')

        success = self.statement_repo.delete(statement_id)
        if success:
            logger.info(f'Deleted statement {statement_id}: {stmt["filename"]}')
            return ServiceResult(success=True)
        return ServiceResult(success=False, error='Failed to delete statement')

    # ============== Transactions ==============

    def get_all_transactions(
        self,
        status: str = None,
        company_cui: str = None,
        supplier: str = None,
        date_from: str = None,
        date_to: str = None,
        search: str = None,
        sort: str = None,
        limit: int = 500,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get transactions with optional filters."""
        transactions = self.transaction_repo.get_all(
            status=status,
            company_cui=company_cui,
            supplier=supplier,
            date_from=date_from,
            date_to=date_to,
            search=search,
            sort=sort,
            limit=limit,
            offset=offset
        )

        # Convert dates to ISO strings for JSON
        for txn in transactions:
            if txn.get('transaction_date'):
                txn['transaction_date'] = str(txn['transaction_date'])
            if txn.get('value_date'):
                txn['value_date'] = str(txn['value_date'])
            if txn.get('created_at'):
                txn['created_at'] = str(txn['created_at'])
            if txn.get('linked_invoice_date'):
                txn['linked_invoice_date'] = str(txn['linked_invoice_date'])
            if txn.get('suggested_invoice_date'):
                txn['suggested_invoice_date'] = str(txn['suggested_invoice_date'])

        return transactions

    def count_transactions(
        self,
        status: str = None,
        company_cui: str = None,
        supplier: str = None,
        date_from: str = None,
        date_to: str = None,
        search: str = None,
    ) -> int:
        """Total transactions matching the filters, ignoring limit/offset."""
        return self.transaction_repo.count(
            status=status,
            company_cui=company_cui,
            supplier=supplier,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )

    def get_transaction(self, transaction_id: int) -> Optional[Dict[str, Any]]:
        """Get a single transaction by ID."""
        txn = self.transaction_repo.get_by_id(transaction_id)
        if txn:
            if txn.get('transaction_date'):
                txn['transaction_date'] = str(txn['transaction_date'])
            if txn.get('value_date'):
                txn['value_date'] = str(txn['value_date'])
        return txn

    def update_transaction(
        self,
        transaction_id: int,
        matched_supplier: str = None,
        status: str = None,
        vendor_name: str = None,
        invoice_id: int = None
    ) -> ServiceResult:
        """Update a transaction.

        Only fields the caller actually provided (non-None) are forwarded, so an
        unrelated column is never overwritten. A None here means "not provided"
        (the PUT route sends data.get(...) for absent keys); to clear a column
        pass an empty string.
        """
        fields = {
            key: value
            for key, value in (
                ('matched_supplier', matched_supplier),
                ('status', status),
                ('vendor_name', vendor_name),
                ('invoice_id', invoice_id),
            )
            if value is not None
        }
        if not fields:
            return ServiceResult(success=False, error='No fields to update')

        success = self.transaction_repo.update(transaction_id, **fields)
        if success:
            return ServiceResult(success=True)
        return ServiceResult(success=False, error='Transaction not found or no changes made')

    def bulk_ignore_transactions(self, transaction_ids: List[int]) -> ServiceResult:
        """Bulk ignore transactions."""
        count = self.transaction_repo.bulk_update_status(transaction_ids, 'ignored')
        return ServiceResult(success=True, data={'updated_count': count})

    def bulk_update_status(self, transaction_ids: List[int], status: str) -> ServiceResult:
        """Bulk update status for transactions."""
        count = self.transaction_repo.bulk_update_status(transaction_ids, status)
        return ServiceResult(success=True, data={'updated_count': count})

    def get_transaction_summary(
        self,
        company_cui: str = None,
        supplier: str = None,
        date_from: str = None,
        date_to: str = None
    ) -> Dict[str, Any]:
        """Get summary statistics for transactions."""
        return self.transaction_repo.get_summary(
            company_cui=company_cui,
            supplier=supplier,
            date_from=date_from,
            date_to=date_to
        )

    def get_filter_options(self) -> Dict[str, Any]:
        """Get available filter options."""
        return {
            'companies': self.transaction_repo.get_distinct_companies(),
            'suppliers': self.transaction_repo.get_distinct_suppliers()
        }

    # ============== Invoice Linking ==============

    def link_invoice(self, transaction_id: int, invoice_id: int) -> ServiceResult:
        """Link an invoice to a transaction."""
        txn = self.transaction_repo.get_by_id(transaction_id)
        if not txn:
            return ServiceResult(success=False, error='Transaction not found')

        if txn.get('invoice_id'):
            return ServiceResult(
                success=False,
                error='Transaction is already linked to an invoice',
                data={'existing_invoice_id': txn['invoice_id']}
            )

        # Verify invoice exists
        from accounting.invoices.repositories import InvoiceRepository
        invoice = InvoiceRepository().get_with_allocations(invoice_id)
        if not invoice:
            return ServiceResult(success=False, error='Invoice not found')

        # Only set the link + status. Keep the transaction's own vendor_name and
        # matched_supplier (the parsed/normalized values, e.g. "Meta") so linking
        # an invoice doesn't erase the on-screen Vendor/Supplier columns.
        success = self.transaction_repo.update(
            transaction_id,
            invoice_id=invoice_id,
            status='resolved'
        )

        if success:
            logger.info(f'Linked transaction {transaction_id} to invoice {invoice_id}')
            return ServiceResult(success=True, data={
                'transaction_id': transaction_id,
                'invoice_id': invoice_id
            })
        return ServiceResult(success=False, error='Failed to update transaction')

    def unlink_invoice(self, transaction_id: int) -> ServiceResult:
        """Remove the invoice link from a transaction."""
        txn = self.transaction_repo.get_by_id(transaction_id)
        if not txn:
            return ServiceResult(success=False, error='Transaction not found')

        if not txn.get('invoice_id'):
            return ServiceResult(success=False, error='Transaction is not linked to any invoice')

        success = self.transaction_repo.update(
            transaction_id,
            invoice_id=None,
            status='pending'
        )

        if success:
            logger.info(f'Unlinked invoice from transaction {transaction_id}')
            return ServiceResult(success=True, data={
                'transaction_id': transaction_id,
                'new_status': 'pending'
            })
        return ServiceResult(success=False, error='Failed to update transaction')

    # ============== Transaction Merging ==============

    def merge_transactions(self, transaction_ids: List[int]) -> ServiceResult:
        """Merge multiple transactions into one."""
        if len(transaction_ids) < 2:
            return ServiceResult(success=False, error='At least 2 transactions required for merging')

        result = self.transaction_repo.merge(transaction_ids)

        if result.get('error'):
            return ServiceResult(success=False, error=result['error'])

        logger.info(f'Merged transactions {transaction_ids} into {result["id"]}')
        return ServiceResult(success=True, data=result)

    def unmerge_transaction(self, transaction_id: int) -> ServiceResult:
        """Unmerge a merged transaction."""
        result = self.transaction_repo.unmerge(transaction_id)

        if result.get('error'):
            return ServiceResult(success=False, error=result['error'])

        logger.info(f'Unmerged transaction {transaction_id}, restored {result["restored_count"]} transactions')
        return ServiceResult(success=True, data=result)

    def get_merged_sources(self, transaction_id: int) -> ServiceResult:
        """Get source transactions that were merged."""
        txn = self.transaction_repo.get_by_id(transaction_id)
        if not txn:
            return ServiceResult(success=False, error='Transaction not found')

        sources = self.transaction_repo.get_merged_sources(transaction_id)
        return ServiceResult(success=True, data={'sources': sources})

    # ============== Vendor Mappings ==============

    def get_all_mappings(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all vendor mappings."""
        return self.mapping_repo.get_all(active_only=active_only)

    def get_mapping(self, mapping_id: int) -> Optional[Dict[str, Any]]:
        """Get a single vendor mapping by ID."""
        return self.mapping_repo.get_by_id(mapping_id)

    def create_mapping(
        self,
        pattern: str,
        supplier_name: str,
        supplier_vat: str = None,
        template_id: int = None
    ) -> ServiceResult:
        """Create a new vendor mapping."""
        try:
            mapping_id = self.mapping_repo.create(
                pattern=pattern,
                supplier_name=supplier_name,
                supplier_vat=supplier_vat,
                template_id=template_id
            )
            # Reload patterns cache
            reload_patterns()
            return ServiceResult(success=True, data={'mapping_id': mapping_id})
        except Exception as e:
            logger.exception(f'Failed to create mapping: {e}')
            return ServiceResult(success=False, error=str(e))

    def update_mapping(
        self,
        mapping_id: int,
        pattern: str = None,
        supplier_name: str = None,
        supplier_vat: str = None,
        template_id: int = None,
        is_active: bool = None
    ) -> ServiceResult:
        """Update a vendor mapping."""
        try:
            success = self.mapping_repo.update(
                mapping_id,
                pattern=pattern,
                supplier_name=supplier_name,
                supplier_vat=supplier_vat,
                template_id=template_id,
                is_active=is_active
            )
            if success:
                # Reload patterns cache
                reload_patterns()
                return ServiceResult(success=True)
            return ServiceResult(success=False, error='Mapping not found or no changes made')
        except Exception as e:
            logger.exception(f'Failed to update mapping {mapping_id}: {e}')
            return ServiceResult(success=False, error=str(e))

    def delete_mapping(self, mapping_id: int) -> ServiceResult:
        """Delete a vendor mapping."""
        success = self.mapping_repo.delete(mapping_id)
        if success:
            # Reload patterns cache
            reload_patterns()
            return ServiceResult(success=True)
        return ServiceResult(success=False, error='Delete failed')
