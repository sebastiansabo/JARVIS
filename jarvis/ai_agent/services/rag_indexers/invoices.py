"""
Invoice Indexer Mixin

Provides index_invoice, index_invoices_batch, _fetch_invoice_data,
and _build_invoice_content for RAGService.
"""

from typing import Optional, Dict, Any

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ...models import RAGDocument, RAGSourceType, ServiceResult

logger = get_logger('jarvis.ai_agent.services.rag')


class InvoiceIndexerMixin:
    """Mixin providing invoice indexing methods for RAGService."""

    def _fetch_invoice_data(self, invoice_id: int) -> Optional[Dict]:
        """Fetch invoice data with all allocations."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT * FROM invoices WHERE id = %s", (invoice_id,))
            invoice = cursor.fetchone()
            if not invoice:
                return None
            data = dict(invoice)
            # Fetch all allocations
            cursor.execute("""
                SELECT company, brand, department, subdepartment,
                       allocation_percent, allocation_value, responsible, comment
                FROM allocations WHERE invoice_id = %s ORDER BY allocation_value DESC
            """, (invoice_id,))
            data['allocations'] = [dict(r) for r in cursor.fetchall()]
            if data['allocations']:
                data['allocated_company'] = data['allocations'][0].get('company')
                data['allocated_brand'] = data['allocations'][0].get('brand')
                data['allocated_department'] = data['allocations'][0].get('department')
                data['allocated_subdepartment'] = data['allocations'][0].get('subdepartment')
            return data
        finally:
            release_db(conn)

    def _build_invoice_content(self, invoice_data: Dict) -> str:
        """Build searchable content from invoice data, enriched via Claude."""
        parts = []
        if invoice_data.get('supplier'):
            parts.append(f"Supplier: {invoice_data['supplier']}")
        if invoice_data.get('invoice_number'):
            parts.append(f"Invoice Number: {invoice_data['invoice_number']}")
        if invoice_data.get('invoice_date'):
            parts.append(f"Date: {invoice_data['invoice_date']}")
        if invoice_data.get('invoice_value'):
            currency = invoice_data.get('currency', 'RON')
            parts.append(f"Amount: {invoice_data['invoice_value']} {currency}")
        if invoice_data.get('type'):
            parts.append(f"Type: {invoice_data['type']}")
        if invoice_data.get('status'):
            parts.append(f"Status: {invoice_data['status']}")
        if invoice_data.get('payment_status'):
            parts.append(f"Payment: {invoice_data['payment_status']}")
        if invoice_data.get('supplier_vat'):
            parts.append(f"Supplier VAT: {invoice_data['supplier_vat']}")
        if invoice_data.get('customer_vat'):
            parts.append(f"Customer VAT: {invoice_data['customer_vat']}")
        # All allocations
        for alloc in invoice_data.get('allocations', []):
            line = f"Allocation: {alloc.get('company', '?')}"
            if alloc.get('brand'):
                line += f" / {alloc['brand']}"
            if alloc.get('department'):
                line += f" / {alloc['department']}"
            pct = alloc.get('allocation_percent', '')
            val = alloc.get('allocation_value', '')
            if pct or val:
                line += f" — {pct}% = {val} RON"
            if alloc.get('responsible'):
                line += f" (resp: {alloc['responsible']})"
            parts.append(line)

        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "invoice with allocations")

    def index_invoice(
        self,
        invoice_id: int,
        company_id: Optional[int] = None,
    ) -> ServiceResult:
        """
        Index an invoice for RAG search.

        Args:
            invoice_id: Invoice ID to index
            company_id: Company ID for access control

        Returns:
            ServiceResult with RAGDocument
        """
        try:
            # Fetch invoice data
            invoice_data = self._fetch_invoice_data(invoice_id)
            if not invoice_data:
                return ServiceResult(success=False, error="Invoice not found")

            # Build searchable content
            content = self._build_invoice_content(invoice_data)
            content_hash = self.embedding_service.compute_content_hash(content)

            # Check if already indexed
            existing = self.document_repo.get_by_source(
                RAGSourceType.INVOICE, invoice_id
            )

            if existing and existing.content_hash == content_hash:
                logger.debug(f"Invoice {invoice_id} already indexed, no changes")
                return ServiceResult(success=True, data=existing)

            # Build metadata
            metadata = {
                'invoice_number': invoice_data.get('invoice_number'),
                'supplier': invoice_data.get('supplier'),
                'date': str(invoice_data.get('invoice_date', '')),
                'amount': str(invoice_data.get('invoice_value', '')),
                'currency': invoice_data.get('currency', 'RON'),
            }

            # Generate embedding if available
            embedding = None
            if self._has_embeddings:
                try:
                    embedding = self.embedding_service.generate_embedding(content)
                except Exception as e:
                    logger.warning(f"Failed to generate embedding: {e}")

            # Create or update document
            document = RAGDocument(
                source_type=RAGSourceType.INVOICE,
                source_id=invoice_id,
                source_table='invoices',
                content=content,
                content_hash=content_hash,
                embedding=embedding,
                metadata=metadata,
                company_id=company_id or invoice_data.get('company_id'),
            )

            if existing:
                # Update existing
                if embedding:
                    self.document_repo.update_embedding(
                        existing.id, embedding, content_hash
                    )
                document.id = existing.id
            else:
                # Create new
                document = self.document_repo.create(document)

            logger.info(f"Indexed invoice {invoice_id}")
            return ServiceResult(success=True, data=document)

        except Exception as e:
            logger.error(f"Failed to index invoice {invoice_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_invoices_batch(
        self,
        limit: int = 100,
    ) -> ServiceResult:
        """
        Index multiple invoices in batch.

        Args:
            limit: Maximum invoices to process

        Returns:
            ServiceResult with count of indexed invoices
        """
        try:
            conn = get_db()
            cursor = get_cursor(conn)

            # Get invoices not yet indexed or with changed content
            cursor.execute("""
                SELECT i.id
                FROM invoices i
                LEFT JOIN ai_agent.rag_documents r
                    ON r.source_type = 'invoice'
                    AND r.source_id = i.id
                    AND r.is_active = TRUE
                WHERE (r.id IS NULL
                   OR r.updated_at < i.updated_at)
                  AND i.deleted_at IS NULL
                ORDER BY i.updated_at DESC
                LIMIT %s
            """, (limit,))

            invoices = cursor.fetchall()
            release_db(conn)

            indexed = 0
            for inv in invoices:
                result = self.index_invoice(inv['id'])
                if result.success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} invoices")
            return ServiceResult(success=True, data={'indexed': indexed})

        except Exception as e:
            logger.error(f"Batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))
