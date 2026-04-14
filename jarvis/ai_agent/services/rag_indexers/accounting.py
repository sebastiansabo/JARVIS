"""
Accounting Indexer Mixin

Provides accounting-related indexing methods for RAGService:
  - transaction:    index_transaction, index_transactions_batch, _fetch_transaction_data, _build_transaction_content
  - efactura:       index_efactura, index_efactura_batch, _fetch_efactura_data, _build_efactura_content
  - bank_statement: index_bank_statement, index_bank_statements_batch, _build_bank_statement_content
  - chart_account:  index_chart_account, index_chart_accounts_batch, _build_chart_account_content
  - bilant_report:  index_bilant_report, index_bilant_reports_batch, _build_bilant_content
"""

from typing import Optional, Dict, Any

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ...models import RAGSourceType, ServiceResult

logger = get_logger('jarvis.ai_agent.services.rag')


class AccountingIndexerMixin:
    """Mixin providing accounting-related indexing methods for RAGService."""

    # ============== Bank Transaction Indexing ==============

    def _fetch_transaction_data(self, txn_id: int) -> Optional[Dict]:
        """Fetch bank transaction data from database."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT t.*, c.id as company_id_lookup
                FROM bank_statement_transactions t
                LEFT JOIN companies c ON c.vat = t.company_cui
                WHERE t.id = %s AND t.merged_into_id IS NULL
            """, (txn_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_transaction_content(self, data: Dict) -> str:
        """Build searchable content from transaction data."""
        parts = []
        if data.get('description'):
            parts.append(f"Bank Transaction: {data['description']}")
        if data.get('vendor_name'):
            parts.append(f"Vendor: {data['vendor_name']}")
        if data.get('matched_supplier'):
            parts.append(f"Matched Supplier: {data['matched_supplier']}")
        if data.get('amount') is not None:
            currency = data.get('currency', 'RON')
            parts.append(f"Amount: {data['amount']} {currency}")
        if data.get('transaction_date'):
            parts.append(f"Date: {data['transaction_date']}")
        if data.get('company_name'):
            parts.append(f"Company: {data['company_name']}")
        if data.get('account_number'):
            parts.append(f"Account: {data['account_number']}")
        if data.get('status'):
            parts.append(f"Status: {data['status']}")
        return "\n".join(parts)

    def index_transaction(self, txn_id: int) -> ServiceResult:
        """Index a bank transaction for RAG search."""
        data = self._fetch_transaction_data(txn_id)
        if not data:
            return ServiceResult(success=False, error="Transaction not found")

        content = self._build_transaction_content(data)
        metadata = {
            'vendor_name': data.get('vendor_name') or data.get('matched_supplier'),
            'amount': str(data.get('amount', '')),
            'currency': data.get('currency', 'RON'),
            'date': str(data.get('transaction_date', '')),
            'status': data.get('status'),
        }
        company_id = data.get('company_id_lookup')
        return self._index_document(
            RAGSourceType.TRANSACTION, txn_id, 'bank_statement_transactions', content, metadata, company_id
        )

    def index_transactions_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index bank transactions."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT t.id FROM bank_statement_transactions t
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'transaction' AND r.source_id = t.id AND r.is_active = TRUE
                    WHERE t.merged_into_id IS NULL AND r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_transaction(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} transactions")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Transaction batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== e-Factura Indexing ==============

    def _fetch_efactura_data(self, ef_id: int) -> Optional[Dict]:
        """Fetch e-Factura invoice data from database."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT * FROM efactura_invoices
                WHERE id = %s AND deleted_at IS NULL
            """, (ef_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_efactura_content(self, data: Dict) -> str:
        """Build searchable content from e-Factura data."""
        parts = []
        if data.get('invoice_number'):
            series = data.get('invoice_series', '')
            num = data.get('invoice_number')
            parts.append(f"e-Factura Invoice: {series}{num}" if series else f"e-Factura Invoice: {num}")
        if data.get('partner_name'):
            parts.append(f"Supplier: {data['partner_name']}")
        if data.get('partner_cif'):
            parts.append(f"Supplier CIF: {data['partner_cif']}")
        if data.get('direction'):
            parts.append(f"Direction: {data['direction']}")
        if data.get('total_amount') is not None:
            currency = data.get('currency', 'RON')
            parts.append(f"Amount: {data['total_amount']} {currency}")
        if data.get('total_vat') is not None:
            parts.append(f"VAT: {data['total_vat']}")
        if data.get('issue_date'):
            parts.append(f"Date: {data['issue_date']}")
        if data.get('status'):
            parts.append(f"Status: {data['status']}")
        if data.get('cif_owner'):
            parts.append(f"Owner CIF: {data['cif_owner']}")

        # Allocation status
        if data.get('jarvis_invoice_id'):
            parts.append("Allocation: Allocated (sent to invoice module)")
        elif data.get('ignored'):
            parts.append("Allocation: Hidden")
        else:
            parts.append("Allocation: Unallocated")

        return "\n".join(parts)

    def index_efactura(self, ef_id: int) -> ServiceResult:
        """Index an e-Factura invoice for RAG search."""
        data = self._fetch_efactura_data(ef_id)
        if not data:
            return ServiceResult(success=False, error="e-Factura invoice not found")

        content = self._build_efactura_content(data)
        metadata = {
            'invoice_number': data.get('invoice_number'),
            'partner_name': data.get('partner_name'),
            'amount': str(data.get('total_amount', '')),
            'currency': data.get('currency', 'RON'),
            'date': str(data.get('issue_date', '')),
            'direction': data.get('direction'),
        }
        return self._index_document(
            RAGSourceType.EFACTURA, ef_id, 'efactura_invoices', content, metadata, data.get('company_id')
        )

    def index_efactura_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index e-Factura invoices."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT e.id FROM efactura_invoices e
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'efactura' AND r.source_id = e.id AND r.is_active = TRUE
                    WHERE e.deleted_at IS NULL
                      AND (r.id IS NULL OR r.updated_at < e.updated_at)
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_efactura(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} e-Factura invoices")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"e-Factura batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Bank Statements ==============

    def _build_bank_statement_content(self, data: dict) -> str:
        """Build content from bank statement with transaction summary."""
        parts = []
        parts.append(f"Bank Statement: {data.get('filename', '?')}")
        if data.get('company_name'):
            parts.append(f"Company: {data['company_name']}")
        if data.get('company_cui'):
            parts.append(f"CUI: {data['company_cui']}")
        if data.get('account_number'):
            parts.append(f"Account: {data['account_number']}")
        if data.get('period_from') and data.get('period_to'):
            parts.append(f"Period: {data['period_from']} — {data['period_to']}")
        parts.append(f"Transactions: {data.get('total_transactions', 0)} total, {data.get('new_transactions', 0)} new")
        if data.get('uploaded_at'):
            parts.append(f"Uploaded: {data['uploaded_at']}")
        for tx in data.get('transactions', []):
            line = f"Tx: {tx.get('vendor_name', '?')} — {tx.get('amount', 0)} {tx.get('currency', 'RON')}"
            if tx.get('transaction_date'):
                line += f" on {tx['transaction_date']}"
            if tx.get('description'):
                line += f" ({tx['description'][:80]})"
            parts.append(line)
        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "bank statement with transactions")

    def index_bank_statement(self, statement_id: int) -> ServiceResult:
        """Index a bank statement for RAG search."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("SELECT * FROM bank_statements WHERE id = %s", (statement_id,))
                data = cursor.fetchone()
                if not data:
                    return ServiceResult(success=False, error='Bank statement not found')
                data = dict(data)
                cursor.execute("""
                    SELECT vendor_name, amount, currency, transaction_date, description, status
                    FROM bank_statement_transactions
                    WHERE statement_id = %s ORDER BY transaction_date
                """, (statement_id,))
                data['transactions'] = [dict(r) for r in cursor.fetchall()]
            finally:
                release_db(conn)
            content = self._build_bank_statement_content(data)
            metadata = {
                'filename': data.get('filename'),
                'company': data.get('company_name'),
                'account': data.get('account_number'),
                'period': f"{data.get('period_from', '')} — {data.get('period_to', '')}",
                'tx_count': data.get('total_transactions', 0),
            }
            company_id = self._lookup_company_id(data.get('company_name'))
            return self._index_document(
                RAGSourceType.BANK_STATEMENT, statement_id, 'bank_statements',
                content, metadata, company_id
            )
        except Exception as e:
            logger.error(f"Bank statement indexing failed for {statement_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_bank_statements_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index bank statements."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT s.id FROM bank_statements s
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'bank_statement' AND r.source_id = s.id AND r.is_active = TRUE
                    WHERE r.id IS NULL OR r.updated_at < s.uploaded_at
                    ORDER BY s.uploaded_at DESC LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)
            indexed = 0
            for row in rows:
                if self.index_bank_statement(row['id']).success:
                    indexed += 1
            logger.info(f"Batch indexed {indexed} bank statements")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Bank statement batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Chart of Accounts ==============

    def _build_chart_account_content(self, data: dict) -> str:
        """Build content from chart of accounts entry."""
        parts = []
        parts.append(f"Account: {data.get('code', '?')} — {data.get('name', '?')}")
        parts.append(f"Class: {data.get('account_class', '?')}")
        parts.append(f"Type: {data.get('account_type', '?')}")
        if data.get('parent_code'):
            parts.append(f"Parent: {data['parent_code']}")
        if data.get('company_name'):
            parts.append(f"Company: {data['company_name']}")
        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "chart of accounts entry")

    def index_chart_account(self, account_id: int) -> ServiceResult:
        """Index a chart of accounts entry for RAG search."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT ca.*, c.company as company_name
                    FROM chart_of_accounts ca
                    LEFT JOIN companies c ON c.id = ca.company_id
                    WHERE ca.id = %s AND ca.is_active = TRUE
                """, (account_id,))
                data = cursor.fetchone()
            finally:
                release_db(conn)
            if not data:
                return ServiceResult(success=False, error='Account not found')
            content = self._build_chart_account_content(dict(data))
            metadata = {
                'code': data.get('code'),
                'name': data.get('name'),
                'class': data.get('account_class'),
                'type': data.get('account_type'),
            }
            return self._index_document(
                RAGSourceType.CHART_ACCOUNT, account_id, 'chart_of_accounts',
                content, metadata, data.get('company_id')
            )
        except Exception as e:
            logger.error(f"Chart account indexing failed for {account_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_chart_accounts_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index chart of accounts."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT ca.id FROM chart_of_accounts ca
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'chart_account' AND r.source_id = ca.id AND r.is_active = TRUE
                    WHERE ca.is_active = TRUE AND (r.id IS NULL OR r.updated_at < ca.updated_at)
                    ORDER BY ca.code LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)
            indexed = 0
            for row in rows:
                if self.index_chart_account(row['id']).success:
                    indexed += 1
            logger.info(f"Batch indexed {indexed} chart accounts")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Chart account batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Bilant / Financial Reports ==============

    def _build_bilant_content(self, data: dict) -> str:
        """Build content from financial report generation with results."""
        parts = []
        parts.append(f"Financial Report: {data.get('template_name', 'Bilant')}")
        if data.get('generation_date'):
            parts.append(f"Generated: {data['generation_date']}")
        if data.get('company_name'):
            parts.append(f"Company: {data['company_name']}")
        if data.get('period'):
            parts.append(f"Period: {data['period']}")
        for r in data.get('results', []):
            line = f"Row {r.get('nr_rd', '?')}: {r.get('description', '?')} = {r.get('value', 0)}"
            parts.append(line)
        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "financial report (bilant)")

    def index_bilant_report(self, generation_id: int) -> ServiceResult:
        """Index a bilant generation (with results) for RAG search."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT g.*, t.name as template_name
                    FROM bilant_generations g
                    LEFT JOIN bilant_templates t ON t.id = g.template_id
                    WHERE g.id = %s
                """, (generation_id,))
                gen = cursor.fetchone()
                if not gen:
                    return ServiceResult(success=False, error='Bilant generation not found')
                data = dict(gen)
                cursor.execute("""
                    SELECT nr_rd, description, value, sort_order
                    FROM bilant_results
                    WHERE generation_id = %s AND value IS NOT NULL AND value != 0
                    ORDER BY sort_order
                """, (generation_id,))
                data['results'] = [dict(r) for r in cursor.fetchall()]
            finally:
                release_db(conn)
            content = self._build_bilant_content(data)
            metadata = {
                'template': data.get('template_name'),
                'period': data.get('period'),
                'result_count': len(data.get('results', [])),
            }
            return self._index_document(
                RAGSourceType.BILANT_REPORT, generation_id, 'bilant_generations',
                content, metadata, None
            )
        except Exception as e:
            logger.error(f"Bilant report indexing failed for {generation_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_bilant_reports_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index bilant reports."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT g.id FROM bilant_generations g
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'bilant_report' AND r.source_id = g.id AND r.is_active = TRUE
                    WHERE r.id IS NULL OR r.updated_at < g.created_at
                    ORDER BY g.created_at DESC LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)
            indexed = 0
            for row in rows:
                if self.index_bilant_report(row['id']).success:
                    indexed += 1
            logger.info(f"Batch indexed {indexed} bilant reports")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Bilant report batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))
