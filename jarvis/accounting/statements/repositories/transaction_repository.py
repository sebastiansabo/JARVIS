"""Transaction Repository - Data access for bank transactions.

Wraps the existing database functions in a repository pattern.
"""
from typing import Optional, List, Dict, Any

from ..database import (
    save_transactions_with_dedup,
    get_transactions,
    get_transaction,
    update_transaction,
    bulk_update_status,
    get_transaction_summary,
    get_distinct_companies,
    get_distinct_suppliers,
    merge_transactions,
    unmerge_transaction,
    get_merged_source_transactions,
    get_transactions_for_matching,
    get_candidate_invoices,
    bulk_update_transaction_matches,
    accept_suggested_match,
    reject_suggested_match,
    update_transaction_match,
)


class TransactionRepository:
    """Repository for bank transaction data access operations."""

    def save_with_dedup(
        self,
        transactions: List[Dict[str, Any]],
        statement_id: int
    ) -> Dict[str, Any]:
        """Save transactions with duplicate detection.

        Args:
            transactions: List of transaction dictionaries
            statement_id: The statement ID

        Returns:
            Dict with new_count, duplicate_count, new_ids
        """
        return save_transactions_with_dedup(transactions, statement_id)

    def get_all(
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
        """Get transactions with optional filters.

        Args:
            status: Filter by status (pending, matched, ignored, invoiced)
            company_cui: Filter by company CUI
            supplier: Filter by matched supplier
            date_from: Filter by date range start
            date_to: Filter by date range end
            search: Search in description, vendor, supplier
            sort: Sort order (newest, oldest, amount_high, amount_low)
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of transaction dictionaries
        """
        return get_transactions(
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

    def get_by_id(self, transaction_id: int) -> Optional[Dict[str, Any]]:
        """Get a single transaction by ID.

        Args:
            transaction_id: The transaction ID

        Returns:
            Transaction dict or None if not found
        """
        return get_transaction(transaction_id)

    def update(
        self,
        transaction_id: int,
        matched_supplier: str = None,
        status: str = None,
        vendor_name: str = None,
        invoice_id: int = None
    ) -> bool:
        """Update a transaction.

        Args:
            transaction_id: The transaction ID
            matched_supplier: Matched supplier name
            status: Transaction status
            vendor_name: Vendor name
            invoice_id: Linked invoice ID

        Returns:
            True if successful
        """
        return update_transaction(
            transaction_id,
            matched_supplier=matched_supplier,
            status=status,
            vendor_name=vendor_name,
            invoice_id=invoice_id
        )

    def bulk_update_status(self, transaction_ids: List[int], status: str) -> int:
        """Bulk update status for multiple transactions.

        Args:
            transaction_ids: List of transaction IDs
            status: New status

        Returns:
            Number of updated transactions
        """
        return bulk_update_status(transaction_ids, status)

    def get_summary(
        self,
        company_cui: str = None,
        supplier: str = None,
        date_from: str = None,
        date_to: str = None
    ) -> Dict[str, Any]:
        """Get summary statistics for transactions.

        Args:
            company_cui: Filter by company
            supplier: Filter by supplier
            date_from: Filter by date range start
            date_to: Filter by date range end

        Returns:
            Summary statistics dictionary
        """
        return get_transaction_summary(
            company_cui=company_cui,
            supplier=supplier,
            date_from=date_from,
            date_to=date_to
        )

    def get_distinct_companies(self) -> List[Dict[str, Any]]:
        """Get distinct company names and CUIs.

        Returns:
            List of company dictionaries
        """
        return get_distinct_companies()

    def get_distinct_suppliers(self) -> List[str]:
        """Get distinct supplier names.

        Returns:
            List of supplier names
        """
        return get_distinct_suppliers()

    # ============== Merging ==============

    def merge(self, transaction_ids: List[int]) -> Dict[str, Any]:
        """Merge multiple transactions into one.

        Args:
            transaction_ids: List of transaction IDs to merge

        Returns:
            Result dict with merged transaction or error
        """
        return merge_transactions(transaction_ids)

    def unmerge(self, transaction_id: int) -> Dict[str, Any]:
        """Unmerge a merged transaction.

        Args:
            transaction_id: The merged transaction ID

        Returns:
            Result dict with restored IDs or error
        """
        return unmerge_transaction(transaction_id)

    def get_merged_sources(self, transaction_id: int) -> List[Dict[str, Any]]:
        """Get source transactions that were merged.

        Args:
            transaction_id: The merged transaction ID

        Returns:
            List of source transaction dictionaries
        """
        return get_merged_source_transactions(transaction_id)

    # ============== Invoice Matching ==============

    def get_for_matching(self, status: str = 'pending', limit: int = 100) -> List[Dict[str, Any]]:
        """Get transactions for invoice matching.

        Args:
            status: Filter by status
            limit: Maximum results

        Returns:
            List of transaction dictionaries
        """
        return get_transactions_for_matching(status=status, limit=limit)

    def get_candidate_invoices(
        self,
        supplier: str = None,
        amount: float = None,
        amount_tolerance: float = 0.05,
        currency: str = 'RON',
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Get candidate invoices for matching.

        Args:
            supplier: Filter by supplier name
            amount: Filter by amount
            amount_tolerance: Amount tolerance percentage
            currency: Filter by currency
            limit: Maximum results

        Returns:
            List of invoice dictionaries
        """
        return get_candidate_invoices(
            supplier=supplier,
            amount=amount,
            amount_tolerance=amount_tolerance,
            currency=currency,
            limit=limit
        )

    def bulk_update_matches(self, results: List[Dict[str, Any]]) -> int:
        """Bulk update transaction match results.

        Args:
            results: List of match result dictionaries

        Returns:
            Number of updated transactions
        """
        return bulk_update_transaction_matches(results)

    def accept_match(self, transaction_id: int) -> bool:
        """Accept a suggested match.

        Args:
            transaction_id: The transaction ID

        Returns:
            True if successful
        """
        return accept_suggested_match(transaction_id)

    def reject_match(self, transaction_id: int) -> bool:
        """Reject a suggested match.

        Args:
            transaction_id: The transaction ID

        Returns:
            True if successful
        """
        return reject_suggested_match(transaction_id)

    def update_match(
        self,
        transaction_id: int,
        invoice_id: int = None,
        match_method: str = None,
        status: str = None
    ) -> bool:
        """Update transaction match.

        Args:
            transaction_id: The transaction ID
            invoice_id: The invoice ID to link
            match_method: Match method (auto, manual)
            status: New status

        Returns:
            True if successful
        """
        return update_transaction_match(
            transaction_id,
            invoice_id=invoice_id,
            match_method=match_method,
            status=status
        )
