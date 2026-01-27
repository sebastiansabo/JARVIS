"""Statement Repository - Data access for bank statements.

Wraps the existing database functions in a repository pattern.
"""
from typing import Optional, List, Dict, Any

from ..database import (
    create_statement,
    get_statement,
    get_statements,
    get_statement_count,
    check_duplicate_statement,
    update_statement,
    delete_statement,
)


class StatementRepository:
    """Repository for bank statement data access operations."""

    def create(
        self,
        filename: str,
        file_hash: str,
        company_name: str = None,
        company_cui: str = None,
        account_number: str = None,
        period_from: str = None,
        period_to: str = None,
        total_transactions: int = 0,
        uploaded_by: int = None
    ) -> int:
        """Create a new statement record.

        Args:
            filename: Original filename
            file_hash: MD5 hash for duplicate detection
            company_name: Company name from statement
            company_cui: Company CUI/VAT
            account_number: Bank account number
            period_from: Period start date
            period_to: Period end date
            total_transactions: Number of transactions
            uploaded_by: User ID who uploaded

        Returns:
            The new statement ID
        """
        return create_statement(
            filename=filename,
            file_hash=file_hash,
            company_name=company_name,
            company_cui=company_cui,
            account_number=account_number,
            period_from=period_from,
            period_to=period_to,
            total_transactions=total_transactions,
            uploaded_by=uploaded_by
        )

    def get_by_id(self, statement_id: int) -> Optional[Dict[str, Any]]:
        """Get a single statement by ID.

        Args:
            statement_id: The statement ID

        Returns:
            Statement dict or None if not found
        """
        return get_statement(statement_id)

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all statements with pagination.

        Args:
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of statement dictionaries
        """
        return get_statements(limit=limit, offset=offset)

    def get_count(self) -> int:
        """Get total count of statements.

        Returns:
            Total count
        """
        return get_statement_count()

    def check_duplicate(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Check if a statement with this hash already exists.

        Args:
            file_hash: MD5 hash of the file

        Returns:
            Existing statement dict or None
        """
        return check_duplicate_statement(file_hash)

    def update(
        self,
        statement_id: int,
        new_transactions: int = None,
        duplicate_transactions: int = None
    ) -> bool:
        """Update a statement record.

        Args:
            statement_id: The statement ID
            new_transactions: Count of new transactions saved
            duplicate_transactions: Count of duplicate transactions skipped

        Returns:
            True if successful
        """
        return update_statement(
            statement_id,
            new_transactions=new_transactions,
            duplicate_transactions=duplicate_transactions
        )

    def delete(self, statement_id: int) -> bool:
        """Delete a statement and all its transactions.

        Args:
            statement_id: The statement ID

        Returns:
            True if successful
        """
        return delete_statement(statement_id)
