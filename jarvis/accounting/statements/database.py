"""Database operations for Bank Statement module.

This module handles all CRUD operations for:
- bank_statements (uploaded statement files)
- bank_statement_transactions
- vendor_mappings
"""
import logging
from datetime import datetime
from typing import Optional

from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.statements.database')


# ============== BANK STATEMENTS (FILE TRACKING) ==============

def create_statement(
    filename: str,
    file_hash: str,
    company_name: str = None,
    company_cui: str = None,
    account_number: str = None,
    period_from: str = None,
    period_to: str = None,
    total_transactions: int = 0,
    new_transactions: int = 0,
    duplicate_transactions: int = 0,
    uploaded_by: int = None
) -> int:
    """Create a new statement record. Returns the new ID."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            INSERT INTO bank_statements (
                filename, file_hash, company_name, company_cui, account_number,
                period_from, period_to, total_transactions, new_transactions,
                duplicate_transactions, uploaded_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            filename, file_hash, company_name, company_cui, account_number,
            period_from, period_to, total_transactions, new_transactions,
            duplicate_transactions, uploaded_by
        ))

        statement_id = cursor.fetchone()['id']
        conn.commit()
        logger.info(f'Created statement {statement_id}: {filename}')
        return statement_id
    finally:
        release_db(conn)


def get_statement(statement_id: int) -> Optional[dict]:
    """Get a single statement by ID."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT s.*, u.name as uploaded_by_name
            FROM bank_statements s
            LEFT JOIN users u ON s.uploaded_by = u.id
            WHERE s.id = %s
        ''', (statement_id,))

        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        release_db(conn)


def get_statements(limit: int = 100, offset: int = 0) -> list[dict]:
    """Get all statements with pagination."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT s.*, u.name as uploaded_by_name
            FROM bank_statements s
            LEFT JOIN users u ON s.uploaded_by = u.id
            ORDER BY s.uploaded_at DESC
            LIMIT %s OFFSET %s
        ''', (limit, offset))

        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_db(conn)


def get_statement_count() -> int:
    """Get total count of statements."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('SELECT COUNT(*) as count FROM bank_statements')
        return cursor.fetchone()['count']
    finally:
        release_db(conn)


def check_duplicate_statement(file_hash: str) -> Optional[dict]:
    """Check if a statement with this file hash already exists."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT id, filename, uploaded_at
            FROM bank_statements
            WHERE file_hash = %s
            LIMIT 1
        ''', (file_hash,))

        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        release_db(conn)


def update_statement(statement_id: int, **kwargs) -> bool:
    """Update a statement record."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        valid_columns = {
            'total_transactions', 'new_transactions', 'duplicate_transactions',
            'company_name', 'company_cui', 'account_number', 'period_from', 'period_to'
        }

        updates = []
        params = []

        for key, value in kwargs.items():
            if key in valid_columns:
                updates.append(f'{key} = %s')
                params.append(value)

        if not updates:
            return False

        params.append(statement_id)
        cursor.execute(f'''
            UPDATE bank_statements
            SET {', '.join(updates)}
            WHERE id = %s
        ''', tuple(params))

        conn.commit()
        return cursor.rowcount > 0
    finally:
        release_db(conn)


def delete_statement(statement_id: int) -> bool:
    """Delete a statement record only (keeps transactions for history tracking)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Only delete the statement record - transactions are kept for history
        # The FK constraint has ON DELETE SET NULL, so transactions will have statement_id = NULL
        cursor.execute('DELETE FROM bank_statements WHERE id = %s', (statement_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        if deleted:
            logger.info(f'Deleted statement {statement_id} (transactions preserved)')
        return deleted
    finally:
        release_db(conn)


# ============== VENDOR MAPPINGS ==============

def get_all_vendor_mappings(active_only: bool = True) -> list[dict]:
    """Get all vendor mappings, optionally filtered to active only."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        if active_only:
            cursor.execute('''
                SELECT id, pattern, supplier_name, supplier_vat, template_id, is_active, created_at
                FROM vendor_mappings
                WHERE is_active = TRUE
                ORDER BY supplier_name
            ''')
        else:
            cursor.execute('''
                SELECT id, pattern, supplier_name, supplier_vat, template_id, is_active, created_at
                FROM vendor_mappings
                ORDER BY supplier_name
            ''')

        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_db(conn)


def get_vendor_mapping(mapping_id: int) -> Optional[dict]:
    """Get a single vendor mapping by ID."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT id, pattern, supplier_name, supplier_vat, template_id, is_active, created_at
            FROM vendor_mappings
            WHERE id = %s
        ''', (mapping_id,))

        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        release_db(conn)


def create_vendor_mapping(pattern: str, supplier_name: str,
                          supplier_vat: str = None,
                          template_id: int = None) -> int:
    """Create a new vendor mapping. Returns the new ID."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            INSERT INTO vendor_mappings (pattern, supplier_name, supplier_vat, template_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (pattern, supplier_name, supplier_vat, template_id))

        mapping_id = cursor.fetchone()['id']
        conn.commit()
        logger.info(f'Created vendor mapping {mapping_id}: {pattern} -> {supplier_name}')
        return mapping_id
    finally:
        release_db(conn)


def update_vendor_mapping(mapping_id: int, pattern: str = None,
                          supplier_name: str = None, supplier_vat: str = None,
                          template_id: int = None, is_active: bool = None) -> bool:
    """Update a vendor mapping. Returns True if updated."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        updates = []
        params = []

        if pattern is not None:
            updates.append('pattern = %s')
            params.append(pattern)
        if supplier_name is not None:
            updates.append('supplier_name = %s')
            params.append(supplier_name)
        if supplier_vat is not None:
            updates.append('supplier_vat = %s')
            params.append(supplier_vat)
        if template_id is not None:
            updates.append('template_id = %s')
            params.append(template_id)
        if is_active is not None:
            updates.append('is_active = %s')
            params.append(is_active)

        if not updates:
            return False

        params.append(mapping_id)
        cursor.execute(f'''
            UPDATE vendor_mappings
            SET {', '.join(updates)}
            WHERE id = %s
        ''', tuple(params))

        conn.commit()
        return cursor.rowcount > 0
    finally:
        release_db(conn)


def delete_vendor_mapping(mapping_id: int) -> bool:
    """Delete a vendor mapping. Returns True if deleted."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('DELETE FROM vendor_mappings WHERE id = %s', (mapping_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        release_db(conn)


def seed_vendor_mappings():
    """Seed initial vendor mappings if table is empty."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('SELECT COUNT(*) as count FROM vendor_mappings')
        if cursor.fetchone()['count'] > 0:
            return  # Already seeded

        mappings = [
            (r'FACEBK\s*\*', 'Meta', None),
            (r'GOOGLE\s*\*\s*ADS', 'Google Ads', None),
            (r'GOOGLE\s*CLOUD', 'Google Cloud', None),
            (r'CLAUDE\.AI', 'Anthropic', None),
            (r'OPENAI\s*\*\s*CHATGPT', 'OpenAI', None),
            (r'DIGITALOCEAN', 'DigitalOcean', None),
            (r'DREAMSTIME', 'Dreamstime', None),
            (r'SHOPIFY\s*\*', 'Shopify', None),
            (r'Intuit\s*Mailchimp', 'Mailchimp', None),
            (r'ANCPI\s*NETOPIA', 'ANCPI', None),
            (r'tarom\.ro', 'Tarom', None),
            (r'ONRC', 'ONRC', None),
            (r'MPY\*hisky', 'Hisky', None),
        ]

        for pattern, supplier, vat in mappings:
            cursor.execute('''
                INSERT INTO vendor_mappings (pattern, supplier_name, supplier_vat)
                VALUES (%s, %s, %s)
            ''', (pattern, supplier, vat))

        conn.commit()
        logger.info(f'Seeded {len(mappings)} vendor mappings')
    finally:
        release_db(conn)


# ============== BANK STATEMENT TRANSACTIONS ==============

def save_transactions_with_dedup(
    transactions: list[dict],
    statement_id: int = None
) -> dict:
    """
    Save transactions with duplicate detection.
    Uses both application-level check AND database unique constraint.
    Returns dict with new_ids, duplicate_count, and new_count.
    """
    import psycopg2.errors

    conn = get_db()
    try:
        # Disable autocommit to enable transaction with SAVEPOINTs
        conn.autocommit = False
        cursor = get_cursor(conn)

        new_ids = []
        duplicate_count = 0

        for txn in transactions:
            # Check for duplicate using IS NOT DISTINCT FROM for NULL-safe comparison
            # Include account_number and currency to distinguish transactions across accounts/currencies
            cursor.execute('''
                SELECT id FROM bank_statement_transactions
                WHERE company_cui IS NOT DISTINCT FROM %s
                  AND account_number IS NOT DISTINCT FROM %s
                  AND transaction_date IS NOT DISTINCT FROM %s
                  AND amount IS NOT DISTINCT FROM %s
                  AND currency IS NOT DISTINCT FROM %s
                  AND description IS NOT DISTINCT FROM %s
                LIMIT 1
            ''', (
                txn.get('company_cui'),
                txn.get('account_number'),
                txn.get('transaction_date'),
                txn.get('amount'),
                txn.get('currency', 'RON'),
                txn.get('description')
            ))

            if cursor.fetchone():
                duplicate_count += 1
                continue

            # Insert new transaction with constraint violation handling
            # Use savepoint to allow partial rollback without losing other inserts
            try:
                cursor.execute('SAVEPOINT txn_insert')
                cursor.execute('''
                    INSERT INTO bank_statement_transactions (
                        statement_id, statement_file, company_name, company_cui, account_number,
                        transaction_date, value_date, description, vendor_name,
                        matched_supplier, amount, currency, original_amount,
                        original_currency, exchange_rate, auth_code, card_number,
                        transaction_type, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    statement_id,
                    txn.get('statement_file'),
                    txn.get('company_name'),
                    txn.get('company_cui'),
                    txn.get('account_number'),
                    txn.get('transaction_date'),
                    txn.get('value_date'),
                    txn.get('description'),
                    txn.get('vendor_name'),
                    txn.get('matched_supplier'),
                    txn.get('amount'),
                    txn.get('currency', 'RON'),
                    txn.get('original_amount'),
                    txn.get('original_currency'),
                    txn.get('exchange_rate'),
                    txn.get('auth_code'),
                    txn.get('card_number'),
                    txn.get('transaction_type'),
                    txn.get('status', 'pending')
                ))
                new_ids.append(cursor.fetchone()['id'])
                cursor.execute('RELEASE SAVEPOINT txn_insert')
            except psycopg2.errors.UniqueViolation:
                # Constraint caught a duplicate - rollback only this insert, not the whole batch
                cursor.execute('ROLLBACK TO SAVEPOINT txn_insert')
                duplicate_count += 1
                logger.debug(f'Duplicate caught by constraint: {txn.get("description")[:50]}...')
                continue

        conn.commit()
        logger.info(f'Saved {len(new_ids)} new transactions, {duplicate_count} duplicates skipped')
        return {
            'new_ids': new_ids,
            'new_count': len(new_ids),
            'duplicate_count': duplicate_count
        }
    except Exception as e:
        conn.rollback()
        logger.error(f'Error saving transactions: {e}')
        raise
    finally:
        release_db(conn)


def get_distinct_companies() -> list[dict]:
    """Get distinct companies from transactions for filter dropdown."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT DISTINCT company_name, company_cui
            FROM bank_statement_transactions
            WHERE company_name IS NOT NULL
            ORDER BY company_name
        ''')

        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_db(conn)


def get_distinct_suppliers() -> list[str]:
    """Get distinct suppliers from transactions for filter dropdown."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT DISTINCT matched_supplier
            FROM bank_statement_transactions
            WHERE matched_supplier IS NOT NULL
            ORDER BY matched_supplier
        ''')

        return [row['matched_supplier'] for row in cursor.fetchall()]
    finally:
        release_db(conn)


def get_transactions(
    status: str = None,
    company_cui: str = None,
    supplier: str = None,
    date_from: str = None,
    date_to: str = None,
    search: str = None,
    sort: str = None,
    limit: int = 500,
    offset: int = 0
) -> list[dict]:
    """Get transactions with optional filters. Includes linked invoice details.

    Args:
        search: Search term for description, vendor_name, or matched_supplier
        sort: Sort order - newest, oldest, amount_high, amount_low
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        conditions = []
        params = []

        if status:
            conditions.append('t.status = %s')
            params.append(status)
        if company_cui:
            conditions.append('t.company_cui = %s')
            params.append(company_cui)
        if supplier:
            conditions.append('t.matched_supplier = %s')
            params.append(supplier)
        if date_from:
            conditions.append('t.transaction_date >= %s')
            params.append(date_from)
        if date_to:
            conditions.append('t.transaction_date <= %s')
            params.append(date_to)
        if search:
            # Search in description, vendor_name, and matched_supplier (case-insensitive)
            conditions.append('(t.description ILIKE %s OR t.vendor_name ILIKE %s OR t.matched_supplier ILIKE %s)')
            search_pattern = f'%{search}%'
            params.extend([search_pattern, search_pattern, search_pattern])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''

        # Determine sort order
        order_clause = 't.transaction_date DESC, t.id DESC'  # default: newest
        if sort == 'oldest':
            order_clause = 't.transaction_date ASC, t.id ASC'
        elif sort == 'amount_high':
            order_clause = 't.amount DESC, t.transaction_date DESC'
        elif sort == 'amount_low':
            order_clause = 't.amount ASC, t.transaction_date DESC'

        params.extend([limit, offset])
        cursor.execute(f'''
            SELECT t.id, t.statement_file, t.company_name, t.company_cui, t.account_number,
                   t.transaction_date, t.value_date, t.description, t.vendor_name,
                   t.matched_supplier, t.amount, t.currency, t.original_amount,
                   t.original_currency, t.exchange_rate, t.auth_code, t.card_number,
                   t.transaction_type, t.invoice_id, t.status, t.created_at,
                   t.suggested_invoice_id, t.match_confidence, t.match_method,
                   t.merged_into_id, t.is_merged_result, t.merged_dates_display,
                   i.invoice_number, i.invoice_date as linked_invoice_date,
                   i.supplier as linked_invoice_supplier, i.invoice_value as linked_invoice_value,
                   i.currency as linked_invoice_currency, i.value_ron as linked_invoice_value_ron,
                   (SELECT company FROM allocations WHERE invoice_id = i.id LIMIT 1) as linked_invoice_company,
                   si.invoice_number as suggested_invoice_number, si.invoice_date as suggested_invoice_date,
                   si.supplier as suggested_invoice_supplier, si.invoice_value as suggested_invoice_value,
                   si.currency as suggested_invoice_currency, si.value_ron as suggested_invoice_value_ron,
                   (SELECT company FROM allocations WHERE invoice_id = si.id LIMIT 1) as suggested_invoice_company,
                   (SELECT COUNT(*) FROM bank_statement_transactions WHERE merged_into_id = t.id) as merged_count
            FROM bank_statement_transactions t
            LEFT JOIN invoices i ON t.invoice_id = i.id
            LEFT JOIN invoices si ON t.suggested_invoice_id = si.id
            {where_clause}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        ''', tuple(params))

        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_db(conn)


def get_transaction(transaction_id: int) -> Optional[dict]:
    """Get a single transaction by ID."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT id, statement_file, company_name, company_cui, account_number,
                   transaction_date, value_date, description, vendor_name,
                   matched_supplier, amount, currency, original_amount,
                   original_currency, exchange_rate, auth_code, card_number,
                   transaction_type, invoice_id, status, created_at,
                   suggested_invoice_id, match_confidence, match_method
            FROM bank_statement_transactions
            WHERE id = %s
        ''', (transaction_id,))

        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        release_db(conn)


def update_transaction(transaction_id: int, **kwargs) -> bool:
    """Update a transaction. Accepts any valid column as keyword argument.

    When setting status to 'ignored', also clears any invoice suggestions.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        valid_columns = {
            'vendor_name', 'matched_supplier', 'status', 'invoice_id',
            'transaction_type', 'amount', 'currency'
        }

        updates = []
        params = []

        for key, value in kwargs.items():
            if key in valid_columns:
                updates.append(f'{key} = %s')
                params.append(value)

        # If status is being set to 'ignored', also clear invoice suggestions
        if kwargs.get('status') == 'ignored':
            updates.extend([
                'suggested_invoice_id = NULL',
                'match_confidence = NULL',
                'match_method = NULL'
            ])

        if not updates:
            return False

        params.append(transaction_id)
        cursor.execute(f'''
            UPDATE bank_statement_transactions
            SET {', '.join(updates)}
            WHERE id = %s
        ''', tuple(params))

        conn.commit()
        return cursor.rowcount > 0
    finally:
        release_db(conn)


def bulk_update_status(transaction_ids: list[int], status: str) -> int:
    """Bulk update status for multiple transactions. Returns count updated.

    When setting status to 'ignored', also clears any invoice suggestions
    (suggested_invoice_id, match_confidence, match_method).
    """
    if not transaction_ids:
        return 0

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        placeholders = ','.join(['%s'] * len(transaction_ids))

        if status == 'ignored':
            # Clear invoice suggestions when ignoring transactions
            cursor.execute(f'''
                UPDATE bank_statement_transactions
                SET status = %s,
                    suggested_invoice_id = NULL,
                    match_confidence = NULL,
                    match_method = NULL
                WHERE id IN ({placeholders})
            ''', (status, *transaction_ids))
        else:
            cursor.execute(f'''
                UPDATE bank_statement_transactions
                SET status = %s
                WHERE id IN ({placeholders})
            ''', (status, *transaction_ids))

        conn.commit()
        return cursor.rowcount
    finally:
        release_db(conn)


def get_transaction_summary(company_cui: str = None, supplier: str = None,
                            status: str = None, date_from: str = None,
                            date_to: str = None) -> dict:
    """Get summary counts by status and supplier, with optional filters for cascading dropdowns.

    Args:
        company_cui: Filter by company CUI (for cascading supplier filter)
        supplier: Filter by supplier (for cascading company filter)
        status: Filter by status
        date_from: Filter by date range start
        date_to: Filter by date range end
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Build base conditions for all queries
        base_conditions = []
        base_params = []

        if company_cui:
            base_conditions.append('company_cui = %s')
            base_params.append(company_cui)
        if supplier:
            base_conditions.append('matched_supplier = %s')
            base_params.append(supplier)
        if status:
            base_conditions.append('status = %s')
            base_params.append(status)
        if date_from:
            base_conditions.append('transaction_date >= %s')
            base_params.append(date_from)
        if date_to:
            base_conditions.append('transaction_date <= %s')
            base_params.append(date_to)

        # By status (apply all filters except status itself)
        status_conditions = [c for c in base_conditions if 'status' not in c] if base_conditions else []
        status_params = [p for c, p in zip(base_conditions, base_params) if 'status' not in c] if base_conditions else []
        status_where = ' AND '.join(status_conditions) if status_conditions else '1=1'

        cursor.execute(f'''
            SELECT status, COUNT(*) as count, SUM(amount) as total
            FROM bank_statement_transactions
            WHERE {status_where}
            GROUP BY status
        ''', status_params)
        by_status = {row['status']: {'count': row['count'], 'total': row['total']}
                     for row in cursor.fetchall()}

        # By supplier - apply company filter (and other filters except supplier)
        # This enables: when company is selected, show only suppliers for that company
        supplier_conditions = ['matched_supplier IS NOT NULL', 'status != %s']
        supplier_params = ['ignored']

        if company_cui:
            supplier_conditions.append('company_cui = %s')
            supplier_params.append(company_cui)
        if date_from:
            supplier_conditions.append('transaction_date >= %s')
            supplier_params.append(date_from)
        if date_to:
            supplier_conditions.append('transaction_date <= %s')
            supplier_params.append(date_to)

        supplier_where = ' AND '.join(supplier_conditions)

        cursor.execute(f'''
            SELECT matched_supplier, COUNT(*) as count, SUM(amount) as total
            FROM bank_statement_transactions
            WHERE {supplier_where}
            GROUP BY matched_supplier
            ORDER BY total DESC
        ''', supplier_params)
        by_supplier = [dict(row) for row in cursor.fetchall()]

        # By company - apply supplier filter (and other filters except company)
        # This enables: when supplier is selected, show only companies for that supplier
        company_conditions = ['status != %s']
        company_params = ['ignored']

        if supplier:
            company_conditions.append('matched_supplier = %s')
            company_params.append(supplier)
        if date_from:
            company_conditions.append('transaction_date >= %s')
            company_params.append(date_from)
        if date_to:
            company_conditions.append('transaction_date <= %s')
            company_params.append(date_to)

        company_where = ' AND '.join(company_conditions)

        cursor.execute(f'''
            SELECT company_name, company_cui, COUNT(*) as count, SUM(amount) as total
            FROM bank_statement_transactions
            WHERE {company_where}
            GROUP BY company_name, company_cui
            ORDER BY company_name
        ''', company_params)
        by_company = [dict(row) for row in cursor.fetchall()]

        return {
            'by_status': by_status,
            'by_supplier': by_supplier,
            'by_company': by_company
        }
    finally:
        release_db(conn)


def check_duplicate_transaction(company_cui: str, transaction_date: str,
                                 amount: float, description: str) -> bool:
    """Check if a similar transaction already exists (NULL-safe)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT id FROM bank_statement_transactions
            WHERE company_cui IS NOT DISTINCT FROM %s
              AND transaction_date IS NOT DISTINCT FROM %s
              AND amount IS NOT DISTINCT FROM %s
              AND description IS NOT DISTINCT FROM %s
            LIMIT 1
        ''', (company_cui, transaction_date, amount, description))

        return cursor.fetchone() is not None
    finally:
        release_db(conn)


# ============== INVOICE MATCHING ==============

def get_candidate_invoices(supplier: str = None, amount: float = None,
                           amount_tolerance: float = 0.1, currency: str = 'RON',
                           date_from: str = None, date_to: str = None,
                           limit: int = 50) -> list[dict]:
    """
    Get candidate invoices for matching against a transaction.

    Args:
        supplier: Filter by supplier name (optional)
        amount: Transaction amount to match (optional)
        amount_tolerance: Percentage tolerance for amount matching (default 10%)
        currency: Transaction currency
        date_from: Start date for invoice date range
        date_to: End date for invoice date range
        limit: Max number of candidates

    Returns:
        List of invoice dicts with id, supplier, invoice_number, invoice_value, etc.
    """
    # Import here to avoid circular imports
    from database import get_db as main_get_db, get_cursor as main_get_cursor, release_db as main_release_db

    conn = main_get_db()
    try:
        cursor = main_get_cursor(conn)

        conditions = ['deleted_at IS NULL']
        params = []

        if supplier:
            conditions.append('LOWER(supplier) = LOWER(%s)')
            params.append(supplier)

        if amount:
            abs_amount = abs(amount)
            min_amount = abs_amount * (1 - amount_tolerance)
            max_amount = abs_amount * (1 + amount_tolerance)

            if currency == 'RON':
                conditions.append('(value_ron BETWEEN %s AND %s OR invoice_value BETWEEN %s AND %s)')
                params.extend([min_amount, max_amount, min_amount, max_amount])
            elif currency == 'EUR':
                conditions.append('(value_eur BETWEEN %s AND %s OR invoice_value BETWEEN %s AND %s)')
                params.extend([min_amount, max_amount, min_amount, max_amount])
            else:
                conditions.append('invoice_value BETWEEN %s AND %s')
                params.extend([min_amount, max_amount])

        if date_from:
            conditions.append('invoice_date >= %s')
            params.append(date_from)

        if date_to:
            conditions.append('invoice_date <= %s')
            params.append(date_to)

        where_clause = ' AND '.join(conditions) if conditions else 'TRUE'
        params.append(limit)

        cursor.execute(f'''
            SELECT id, supplier, invoice_number, invoice_date, invoice_value,
                   currency, value_ron, value_eur, exchange_rate, payment_status,
                   subtract_vat, net_value, comment
            FROM invoices
            WHERE {where_clause}
            ORDER BY invoice_date DESC
            LIMIT %s
        ''', tuple(params))

        invoices = []
        for row in cursor.fetchall():
            inv = dict(row)
            # Convert date to string for JSON
            if inv.get('invoice_date'):
                inv['invoice_date'] = str(inv['invoice_date'])
            invoices.append(inv)

        return invoices
    finally:
        main_release_db(conn)


def get_transactions_for_matching(status: str = 'pending', limit: int = 100) -> list[dict]:
    """
    Get transactions that need invoice matching.

    Args:
        status: Filter by status (default 'pending', can also be 'matched')
        limit: Max number of transactions

    Returns:
        List of transaction dicts ready for matching.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT id, transaction_date, value_date, description, vendor_name,
                   matched_supplier, amount, currency, original_amount,
                   original_currency, exchange_rate, status, invoice_id,
                   suggested_invoice_id, match_confidence, match_method
            FROM bank_statement_transactions
            WHERE status = %s AND invoice_id IS NULL
            ORDER BY transaction_date DESC
            LIMIT %s
        ''', (status, limit))

        transactions = []
        for row in cursor.fetchall():
            txn = dict(row)
            if txn.get('transaction_date'):
                txn['transaction_date'] = str(txn['transaction_date'])
            if txn.get('value_date'):
                txn['value_date'] = str(txn['value_date'])
            transactions.append(txn)

        return transactions
    finally:
        release_db(conn)


def update_transaction_match(transaction_id: int, invoice_id: int = None,
                             suggested_invoice_id: int = None,
                             match_confidence: float = None,
                             match_method: str = None,
                             status: str = None) -> bool:
    """
    Update a transaction with invoice match results.

    Args:
        transaction_id: Transaction to update
        invoice_id: Confirmed invoice link (sets status to 'resolved')
        suggested_invoice_id: Suggested invoice for review
        match_confidence: Confidence score (0.0-1.0)
        match_method: How the match was made ('rule', 'heuristic', 'ai', 'manual')
        status: Override status (optional)

    Returns:
        True if update succeeded.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        updates = []
        params = []

        if invoice_id is not None:
            updates.append('invoice_id = %s')
            params.append(invoice_id if invoice_id else None)
            # Auto-set status to resolved when linking
            if not status:
                status = 'resolved' if invoice_id else None

        if suggested_invoice_id is not None:
            updates.append('suggested_invoice_id = %s')
            params.append(suggested_invoice_id if suggested_invoice_id else None)

        if match_confidence is not None:
            updates.append('match_confidence = %s')
            params.append(match_confidence)

        if match_method is not None:
            updates.append('match_method = %s')
            params.append(match_method)

        if status is not None:
            updates.append('status = %s')
            params.append(status)

        if not updates:
            return False

        params.append(transaction_id)

        cursor.execute(f'''
            UPDATE bank_statement_transactions
            SET {', '.join(updates)}
            WHERE id = %s
        ''', tuple(params))

        conn.commit()
        return cursor.rowcount > 0
    finally:
        release_db(conn)


def bulk_update_transaction_matches(results: list[dict]) -> dict:
    """
    Bulk update transactions with match results.

    Args:
        results: List of match results from invoice_matcher.auto_match_transactions()
            Each dict should have: transaction_id, invoice_id, suggested_invoice_id,
            confidence, method, auto_accepted

    Returns:
        Summary dict with counts of updated transactions.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        linked_count = 0
        suggested_count = 0

        for result in results:
            txn_id = result.get('transaction_id')
            if not txn_id:
                continue

            if result.get('auto_accepted') and result.get('invoice_id'):
                # Auto-link confirmed match
                cursor.execute('''
                    UPDATE bank_statement_transactions
                    SET invoice_id = %s, match_confidence = %s, match_method = %s, status = 'resolved'
                    WHERE id = %s
                ''', (
                    result['invoice_id'],
                    result.get('confidence'),
                    result.get('method'),
                    txn_id
                ))
                if cursor.rowcount > 0:
                    linked_count += 1

            elif result.get('suggested_invoice_id'):
                # Store suggestion for review
                cursor.execute('''
                    UPDATE bank_statement_transactions
                    SET suggested_invoice_id = %s, match_confidence = %s, match_method = %s
                    WHERE id = %s
                ''', (
                    result['suggested_invoice_id'],
                    result.get('confidence'),
                    result.get('method'),
                    txn_id
                ))
                if cursor.rowcount > 0:
                    suggested_count += 1

        conn.commit()
        logger.info(f'Bulk match update: {linked_count} linked, {suggested_count} suggested')
        return {
            'linked_count': linked_count,
            'suggested_count': suggested_count
        }
    finally:
        release_db(conn)


def accept_suggested_match(transaction_id: int) -> bool:
    """
    Accept a suggested invoice match, moving it from suggested to confirmed.

    Args:
        transaction_id: Transaction with a suggested match

    Returns:
        True if accepted successfully.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Get the current suggested invoice
        cursor.execute('''
            SELECT suggested_invoice_id, match_confidence, match_method
            FROM bank_statement_transactions
            WHERE id = %s AND suggested_invoice_id IS NOT NULL
        ''', (transaction_id,))

        row = cursor.fetchone()
        if not row:
            return False

        # Move suggested to confirmed
        cursor.execute('''
            UPDATE bank_statement_transactions
            SET invoice_id = suggested_invoice_id,
                suggested_invoice_id = NULL,
                match_method = COALESCE(match_method, 'manual') || '_accepted',
                status = 'resolved'
            WHERE id = %s
        ''', (transaction_id,))

        conn.commit()
        return cursor.rowcount > 0
    finally:
        release_db(conn)


def reject_suggested_match(transaction_id: int) -> bool:
    """
    Reject a suggested invoice match.

    Args:
        transaction_id: Transaction with a suggested match

    Returns:
        True if rejected successfully.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            UPDATE bank_statement_transactions
            SET suggested_invoice_id = NULL,
                match_confidence = NULL,
                match_method = NULL
            WHERE id = %s AND suggested_invoice_id IS NOT NULL
        ''', (transaction_id,))

        conn.commit()
        return cursor.rowcount > 0
    finally:
        release_db(conn)


# ============== TRANSACTION MERGING ==============

def merge_transactions(transaction_ids: list[int]) -> dict:
    """
    Merge multiple transactions into a single new transaction.

    Requirements:
    - All transactions must exist and be pending (not already merged/resolved/ignored)
    - All transactions must have the same currency
    - All transactions must have the same matched_supplier (or vendor_name if no matched_supplier)

    Creates a new "merged result" transaction with:
    - amount = sum of all amounts
    - transaction_date = latest transaction_date
    - value_date = latest value_date
    - description = concatenated descriptions with " • "
    - status = 'pending'
    - is_merged_result = True

    Original transactions are updated with:
    - status = 'merged'
    - merged_into_id = new transaction id

    Args:
        transaction_ids: List of transaction IDs to merge (minimum 2)

    Returns:
        Dict with merged transaction data, or {'error': 'message'} on failure.
    """
    if len(transaction_ids) < 2:
        return {'error': 'At least 2 transactions required for merging'}

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Fetch all transactions
        placeholders = ','.join(['%s'] * len(transaction_ids))
        cursor.execute(f'''
            SELECT id, statement_file, company_name, company_cui, account_number,
                   transaction_date, value_date, description, vendor_name,
                   matched_supplier, amount, currency, original_amount,
                   original_currency, exchange_rate, auth_code, card_number,
                   transaction_type, status, is_merged_result, merged_into_id
            FROM bank_statement_transactions
            WHERE id IN ({placeholders})
        ''', tuple(transaction_ids))

        rows = cursor.fetchall()
        transactions = [dict(row) for row in rows]

        # Validate all transactions exist
        if len(transactions) != len(transaction_ids):
            found_ids = {t['id'] for t in transactions}
            missing = set(transaction_ids) - found_ids
            return {'error': f'Transactions not found: {missing}'}

        # Validate all are pending (not already merged/resolved/ignored)
        for txn in transactions:
            if txn['status'] != 'pending':
                return {'error': f"Transaction {txn['id']} has status '{txn['status']}', only pending transactions can be merged"}
            if txn['is_merged_result']:
                return {'error': f"Transaction {txn['id']} is already a merged result"}
            if txn['merged_into_id']:
                return {'error': f"Transaction {txn['id']} is already merged into another transaction"}

        # Validate same currency
        currencies = set(t['currency'] for t in transactions)
        if len(currencies) > 1:
            return {'error': f'Cannot merge transactions with different currencies: {currencies}'}

        # Validate same supplier (matched_supplier or vendor_name)
        def get_supplier(t):
            return t['matched_supplier'] or t['vendor_name'] or ''
        suppliers = set(get_supplier(t) for t in transactions)
        if len(suppliers) > 1:
            return {'error': f'Cannot merge transactions with different suppliers: {suppliers}'}

        # Calculate merged values
        first_txn = transactions[0]
        total_amount = sum(t['amount'] for t in transactions)
        latest_txn_date = max(t['transaction_date'] for t in transactions if t['transaction_date'])
        latest_val_date = max((t['value_date'] for t in transactions if t['value_date']), default=None)
        merged_description = ' • '.join(t['description'][:50] + '...' if len(t['description']) > 50 else t['description']
                                        for t in transactions if t['description'])

        # Compute merged dates display: "09/12/14.01.2026" format
        # Extract all dates, sort by day, format as "DD/DD/DD.MM.YYYY"
        dates = sorted([t['transaction_date'] for t in transactions if t['transaction_date']])
        if dates:
            days = [str(d.day).zfill(2) for d in dates]
            # Use the latest date's month and year
            month_year = latest_txn_date.strftime('%m.%Y')
            merged_dates_display = '/'.join(days) + '.' + month_year
        else:
            merged_dates_display = None

        # Create merged transaction
        cursor.execute('''
            INSERT INTO bank_statement_transactions (
                statement_file, company_name, company_cui, account_number,
                transaction_date, value_date, description, vendor_name,
                matched_supplier, amount, currency, transaction_type,
                status, is_merged_result, merged_dates_display
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            first_txn['statement_file'],
            first_txn['company_name'],
            first_txn['company_cui'],
            first_txn['account_number'],
            latest_txn_date,
            latest_val_date,
            merged_description,
            first_txn['vendor_name'],
            first_txn['matched_supplier'],
            total_amount,
            first_txn['currency'],
            first_txn['transaction_type'],
            'pending',
            True,
            merged_dates_display
        ))

        merged_id = cursor.fetchone()['id']

        # Update original transactions
        cursor.execute(f'''
            UPDATE bank_statement_transactions
            SET status = 'merged', merged_into_id = %s
            WHERE id IN ({placeholders})
        ''', (merged_id, *transaction_ids))

        conn.commit()

        logger.info(f'Merged {len(transaction_ids)} transactions into {merged_id}')

        # Return the merged transaction
        return {
            'id': merged_id,
            'amount': total_amount,
            'currency': first_txn['currency'],
            'transaction_date': str(latest_txn_date) if latest_txn_date else None,
            'value_date': str(latest_val_date) if latest_val_date else None,
            'description': merged_description,
            'vendor_name': first_txn['vendor_name'],
            'matched_supplier': first_txn['matched_supplier'],
            'company_name': first_txn['company_name'],
            'company_cui': first_txn['company_cui'],
            'status': 'pending',
            'is_merged_result': True,
            'merged_count': len(transaction_ids),
            'merged_from_ids': transaction_ids,
            'merged_dates_display': merged_dates_display
        }
    except Exception as e:
        logger.error(f'Error merging transactions: {e}')
        return {'error': str(e)}
    finally:
        release_db(conn)


def unmerge_transaction(merged_id: int) -> dict:
    """
    Unmerge a merged transaction, restoring the original transactions.

    Args:
        merged_id: ID of the merged result transaction

    Returns:
        Dict with 'success': True and 'restored_ids', or {'error': 'message'} on failure.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Verify the transaction is a merged result
        cursor.execute('''
            SELECT id, is_merged_result FROM bank_statement_transactions
            WHERE id = %s
        ''', (merged_id,))

        row = cursor.fetchone()
        if not row:
            return {'error': f'Transaction {merged_id} not found'}

        if not row['is_merged_result']:
            return {'error': f'Transaction {merged_id} is not a merged transaction'}

        # Find all original transactions
        cursor.execute('''
            SELECT id FROM bank_statement_transactions
            WHERE merged_into_id = %s
        ''', (merged_id,))

        original_ids = [r['id'] for r in cursor.fetchall()]

        if not original_ids:
            return {'error': f'No original transactions found for merged transaction {merged_id}'}

        # Restore original transactions to pending
        placeholders = ','.join(['%s'] * len(original_ids))
        cursor.execute(f'''
            UPDATE bank_statement_transactions
            SET status = 'pending', merged_into_id = NULL
            WHERE id IN ({placeholders})
        ''', tuple(original_ids))

        # Delete the merged transaction
        cursor.execute('DELETE FROM bank_statement_transactions WHERE id = %s', (merged_id,))

        conn.commit()
        logger.info(f'Unmerged transaction {merged_id}, restored {len(original_ids)} transactions')

        return {
            'success': True,
            'restored_ids': original_ids,
            'restored_count': len(original_ids)
        }
    except Exception as e:
        logger.error(f'Error unmerging transaction: {e}')
        return {'error': str(e)}
    finally:
        release_db(conn)


def get_merged_source_transactions(merged_id: int) -> list[dict]:
    """
    Get the original transactions that were merged into a merged transaction.

    Args:
        merged_id: ID of the merged result transaction

    Returns:
        List of original transaction dicts.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT id, transaction_date, value_date, description, vendor_name,
                   matched_supplier, amount, currency, status,
                   company_name, company_cui
            FROM bank_statement_transactions
            WHERE merged_into_id = %s
            ORDER BY transaction_date DESC
        ''', (merged_id,))

        transactions = []
        for row in cursor.fetchall():
            txn = dict(row)
            if txn.get('transaction_date'):
                txn['transaction_date'] = str(txn['transaction_date'])
            if txn.get('value_date'):
                txn['value_date'] = str(txn['value_date'])
            transactions.append(txn)

        return transactions
    finally:
        release_db(conn)
