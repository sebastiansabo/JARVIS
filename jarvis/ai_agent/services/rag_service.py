"""
RAG Service

Retrieval Augmented Generation service for semantic search and context retrieval.
Indexes JARVIS data (invoices, transactions, etc.) for AI queries.
"""

from typing import Optional, List, Dict, Any
from decimal import Decimal

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ..models import RAGDocument, RAGSourceType, RAGSource, ServiceResult
from ..config import AIAgentConfig
from ..exceptions import RAGError
from ..repositories import RAGDocumentRepository
from .embedding_service import EmbeddingService

logger = get_logger('jarvis.ai_agent.services.rag')


class RAGService:
    """
    RAG service for document indexing and retrieval.

    Handles:
    - Indexing JARVIS data (invoices, transactions, companies)
    - Semantic search using embeddings
    - Text search fallback when pgvector unavailable
    - Context formatting for LLM prompts
    """

    def __init__(self, config: Optional[AIAgentConfig] = None):
        """
        Initialize RAG service.

        Args:
            config: Optional AIAgentConfig
        """
        self.config = config or AIAgentConfig()
        self.embedding_service = EmbeddingService(config)
        self.document_repo = RAGDocumentRepository()

        # Check capabilities
        self._has_embeddings = self.embedding_service.is_available()
        self._has_pgvector = None

        logger.info(f"RAG Service initialized (embeddings: {self._has_embeddings})")

    def search(
        self,
        query: str,
        limit: int = 5,
        company_id: Optional[int] = None,
        source_types: Optional[List[RAGSourceType]] = None,
    ) -> List[RAGSource]:
        """
        Search for relevant documents.

        Uses vector similarity if available, otherwise text search.

        Args:
            query: Search query
            limit: Maximum results
            company_id: Optional company filter for access control
            source_types: Optional source type filter

        Returns:
            List of RAGSource results with scores
        """
        if not query or not query.strip():
            return []

        try:
            # Check pgvector availability
            if self._has_pgvector is None:
                self._has_pgvector = self.document_repo.has_pgvector()

            documents = []

            # Try vector search first
            if self._has_pgvector and self._has_embeddings:
                try:
                    query_embedding = self.embedding_service.generate_embedding(query)
                    documents = self.document_repo.search_by_vector(
                        embedding=query_embedding,
                        limit=limit,
                        company_id=company_id,
                        source_types=source_types,
                        min_score=self.config.rag_min_similarity,
                    )
                    logger.debug(f"Vector search returned {len(documents)} results")
                except Exception as e:
                    logger.warning(f"Vector search failed, falling back to text: {e}")
                    documents = []

            # Fallback to text search
            if not documents:
                documents = self.document_repo.search_by_text(
                    query=query,
                    limit=limit,
                    company_id=company_id,
                    source_types=source_types,
                )
                logger.debug(f"Text search returned {len(documents)} results")

            # Convert to RAGSource format
            return [
                RAGSource(
                    doc_id=doc.id,
                    score=doc.score,
                    snippet=self._create_snippet(doc.content),
                    source_type=doc.source_type.value,
                    source_id=doc.source_id,
                    metadata=doc.metadata,
                )
                for doc in documents
            ]

        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return []

    def format_context(
        self,
        sources: List[RAGSource],
        max_tokens: int = 2000,
    ) -> str:
        """
        Format RAG sources into context string for LLM prompt.

        Args:
            sources: List of RAG sources
            max_tokens: Maximum approximate tokens for context

        Returns:
            Formatted context string
        """
        if not sources:
            return ""

        context_parts = []
        approx_tokens = 0

        for i, source in enumerate(sources, 1):
            # Build source context
            header = f"[Source {i}: {source.source_type}]"

            # Add metadata if useful
            meta_parts = []
            if source.metadata:
                if 'supplier' in source.metadata:
                    meta_parts.append(f"Supplier: {source.metadata['supplier']}")
                if 'invoice_number' in source.metadata:
                    meta_parts.append(f"Invoice: {source.metadata['invoice_number']}")
                if 'date' in source.metadata:
                    meta_parts.append(f"Date: {source.metadata['date']}")
                if 'amount' in source.metadata:
                    meta_parts.append(f"Amount: {source.metadata['amount']}")

            meta_str = " | ".join(meta_parts) if meta_parts else ""

            # Build entry
            entry = f"{header}\n"
            if meta_str:
                entry += f"{meta_str}\n"
            entry += f"{source.snippet}\n"

            # Rough token estimate (4 chars per token)
            entry_tokens = len(entry) // 4

            if approx_tokens + entry_tokens > max_tokens:
                break

            context_parts.append(entry)
            approx_tokens += entry_tokens

        return "\n".join(context_parts)

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
                SELECT i.id, i.company_id
                FROM invoices i
                LEFT JOIN ai_agent.rag_documents r
                    ON r.source_type = 'invoice'
                    AND r.source_id = i.id
                    AND r.is_active = TRUE
                WHERE r.id IS NULL
                   OR r.updated_at < i.updated_at
                ORDER BY i.updated_at DESC
                LIMIT %s
            """, (limit,))

            invoices = cursor.fetchall()
            release_db(conn)

            indexed = 0
            for inv in invoices:
                result = self.index_invoice(inv['id'], inv['company_id'])
                if result.success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} invoices")
            return ServiceResult(success=True, data={'indexed': indexed})

        except Exception as e:
            logger.error(f"Batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_stats(self) -> Dict[str, Any]:
        """
        Get RAG statistics.

        Returns:
            Dict with document counts and capabilities
        """
        counts = self.document_repo.count_by_source_type()

        return {
            'total_documents': sum(counts.values()),
            'by_source_type': counts,
            'has_pgvector': self.document_repo.has_pgvector(),
            'has_embeddings': self._has_embeddings,
        }

    def _fetch_invoice_data(self, invoice_id: int) -> Optional[Dict]:
        """Fetch invoice data from database."""
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                SELECT i.*, c.id as company_id
                FROM invoices i
                LEFT JOIN companies c ON c.company = i.dedicated_to
                WHERE i.id = %s
            """, (invoice_id,))

            return cursor.fetchone()

        finally:
            release_db(conn)

    def _build_invoice_content(self, invoice_data: Dict) -> str:
        """Build searchable content from invoice data."""
        parts = []

        # Core fields
        if invoice_data.get('supplier'):
            parts.append(f"Supplier: {invoice_data['supplier']}")

        if invoice_data.get('invoice_number'):
            parts.append(f"Invoice Number: {invoice_data['invoice_number']}")

        if invoice_data.get('invoice_date'):
            parts.append(f"Date: {invoice_data['invoice_date']}")

        if invoice_data.get('invoice_value'):
            currency = invoice_data.get('currency', 'RON')
            parts.append(f"Amount: {invoice_data['invoice_value']} {currency}")

        if invoice_data.get('dedicated_to'):
            parts.append(f"Company: {invoice_data['dedicated_to']}")

        if invoice_data.get('type'):
            parts.append(f"Type: {invoice_data['type']}")

        if invoice_data.get('status'):
            parts.append(f"Status: {invoice_data['status']}")

        if invoice_data.get('payment_status'):
            parts.append(f"Payment: {invoice_data['payment_status']}")

        # Additional context
        if invoice_data.get('supplier_vat'):
            parts.append(f"Supplier VAT: {invoice_data['supplier_vat']}")

        if invoice_data.get('customer_vat'):
            parts.append(f"Customer VAT: {invoice_data['customer_vat']}")

        return "\n".join(parts)

    def _create_snippet(self, content: str, max_length: int = 300) -> str:
        """Create a snippet from content."""
        if len(content) <= max_length:
            return content

        # Try to break at sentence
        snippet = content[:max_length]
        last_period = snippet.rfind('.')
        if last_period > max_length // 2:
            return snippet[:last_period + 1]

        # Break at word
        last_space = snippet.rfind(' ')
        if last_space > 0:
            return snippet[:last_space] + "..."

        return snippet + "..."
