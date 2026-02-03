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
from ..invoice_matcher import auto_match_transactions, score_candidates

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

            # Auto-match new transactions to invoices
            invoice_matched_count = self._auto_match_new_transactions(save_result['new_ids'])

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
                    'invoice_matched_count': invoice_matched_count,
                    'period': period,
                    'summary': parsed.get('summary')
                }
            )

        except Exception as e:
            logger.exception(f'Error processing statement {filename}')
            return ServiceResult(success=False, error=str(e))

    def _auto_match_new_transactions(self, new_ids: List[int]) -> int:
        """Auto-match newly saved transactions to invoices.

        Args:
            new_ids: List of new transaction IDs

        Returns:
            Number of transactions matched to invoices
        """
        if not new_ids:
            return 0

        try:
            # Get the newly saved transactions for matching
            new_txns = [self.transaction_repo.get_by_id(txn_id) for txn_id in new_ids]
            new_txns = [t for t in new_txns if t and t.get('status') not in ('ignored',)]

            if not new_txns:
                return 0

            # Get candidate invoices
            invoices = self.transaction_repo.get_candidate_invoices(limit=200)
            if not invoices:
                return 0

            # Run auto-match
            match_results = auto_match_transactions(
                transactions=new_txns,
                invoices=invoices,
                use_ai=False,
                min_confidence=0.5
            )

            # Save match results
            if match_results['results']:
                self.transaction_repo.bulk_update_matches(match_results['results'])

            matched_count = match_results.get('matched', 0) + match_results.get('suggested', 0)
            logger.info(f'Auto-matched {matched_count} transactions to invoices')
            return matched_count

        except Exception as e:
            logger.warning(f'Auto-match failed: {e}')
            return 0

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
        """Update a transaction."""
        success = self.transaction_repo.update(
            transaction_id,
            matched_supplier=matched_supplier,
            status=status,
            vendor_name=vendor_name,
            invoice_id=invoice_id
        )
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
        from database import get_invoice_with_allocations
        invoice = get_invoice_with_allocations(invoice_id)
        if not invoice:
            return ServiceResult(success=False, error='Invoice not found')

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

    # ============== Auto-Match ==============

    def auto_match_invoices(
        self,
        transaction_ids: List[int] = None,
        use_ai: bool = True,
        min_confidence: float = 0.7
    ) -> ServiceResult:
        """Run automatic invoice matching on transactions."""
        try:
            # Get transactions to match
            if transaction_ids:
                transactions = []
                for txn_id in transaction_ids:
                    txn = self.transaction_repo.get_by_id(txn_id)
                    if txn and txn.get('status') not in ('resolved', 'ignored'):
                        transactions.append(txn)
            else:
                transactions = self.transaction_repo.get_for_matching(status='pending', limit=100)

            if not transactions:
                return ServiceResult(success=True, data={
                    'matched': 0,
                    'suggested': 0,
                    'unmatched': 0,
                    'results': [],
                    'message': 'No transactions to match'
                })

            # Get candidate invoices
            invoices = self.transaction_repo.get_candidate_invoices(limit=200)

            if not invoices:
                return ServiceResult(success=True, data={
                    'matched': 0,
                    'suggested': 0,
                    'unmatched': len(transactions),
                    'results': [],
                    'message': 'No invoices available for matching'
                })

            # Run the matching algorithm
            match_results = auto_match_transactions(
                transactions=transactions,
                invoices=invoices,
                use_ai=use_ai,
                min_confidence=min_confidence
            )

            # Save results to database
            if match_results['results']:
                self.transaction_repo.bulk_update_matches(match_results['results'])

            return ServiceResult(success=True, data=match_results)

        except Exception as e:
            logger.exception('Error in auto-match')
            return ServiceResult(success=False, error=str(e))

    def get_invoice_suggestions(self, transaction_id: int) -> ServiceResult:
        """Get invoice suggestions for a transaction."""
        txn = self.transaction_repo.get_by_id(transaction_id)
        if not txn:
            return ServiceResult(success=False, error='Transaction not found')

        try:
            amount = abs(txn.get('amount', 0))
            currency = txn.get('currency', 'RON')

            # Get candidate invoices
            invoices = self.transaction_repo.get_candidate_invoices(
                supplier=None,
                amount=amount,
                amount_tolerance=0.2,
                currency=currency,
                limit=50
            )

            # Score candidates
            candidates = score_candidates(txn, invoices, limit=5)

            # Format for response
            suggestions = []
            for c in candidates:
                inv = c['invoice']
                suggestions.append({
                    'invoice_id': inv.get('id'),
                    'invoice_number': inv.get('invoice_number'),
                    'supplier': inv.get('supplier'),
                    'amount': inv.get('invoice_value'),
                    'currency': inv.get('currency'),
                    'date': inv.get('invoice_date'),
                    'score': c['score'],
                    'confidence': c['confidence'],
                    'reasons': c['reasons']
                })

            return ServiceResult(success=True, data={
                'transaction': {
                    'id': txn.get('id'),
                    'amount': txn.get('amount'),
                    'currency': txn.get('currency'),
                    'date': str(txn.get('transaction_date')) if txn.get('transaction_date') else None,
                    'vendor': txn.get('vendor_name'),
                    'supplier': txn.get('matched_supplier'),
                    'description': txn.get('description')
                },
                'suggestions': suggestions
            })

        except Exception as e:
            logger.exception(f'Error getting suggestions for transaction {transaction_id}')
            return ServiceResult(success=False, error=str(e))

    def accept_match(self, transaction_id: int, override_invoice_id: int = None) -> ServiceResult:
        """Accept a suggested match."""
        txn = self.transaction_repo.get_by_id(transaction_id)
        if not txn:
            return ServiceResult(success=False, error='Transaction not found')

        try:
            if override_invoice_id:
                success = self.transaction_repo.update_match(
                    transaction_id,
                    invoice_id=override_invoice_id,
                    match_method='manual',
                    status='resolved'
                )
            else:
                success = self.transaction_repo.accept_match(transaction_id)

            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error='No suggestion to accept or update failed')

        except Exception as e:
            logger.exception(f'Error accepting match for transaction {transaction_id}')
            return ServiceResult(success=False, error=str(e))

    def reject_match(self, transaction_id: int) -> ServiceResult:
        """Reject a suggested match."""
        txn = self.transaction_repo.get_by_id(transaction_id)
        if not txn:
            return ServiceResult(success=False, error='Transaction not found')

        try:
            success = self.transaction_repo.reject_match(transaction_id)
            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error='No suggestion to reject')

        except Exception as e:
            logger.exception(f'Error rejecting match for transaction {transaction_id}')
            return ServiceResult(success=False, error=str(e))

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
