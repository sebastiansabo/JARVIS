"""
RAG Service

Retrieval Augmented Generation service for semantic search and context retrieval.
Indexes JARVIS data (invoices, transactions, etc.) for AI queries.

Domain-specific indexing methods are provided by mixin classes in rag_indexers/.
"""

import os
from typing import Optional, List, Dict, Any
from decimal import Decimal

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ..models import RAGDocument, RAGSourceType, RAGSource, ServiceResult
from ..config import AIAgentConfig
from ..exceptions import RAGError
from ..repositories import RAGDocumentRepository
from .embedding_service import EmbeddingService
from .quasar_patterns import dropped_critical_values
from .rag_indexers.invoices import InvoiceIndexerMixin
from .rag_indexers.entities import EntityIndexerMixin
from .rag_indexers.accounting import AccountingIndexerMixin
from .rag_indexers.events import EventIndexerMixin
from .rag_indexers.crm import CRMIndexerMixin
from .rag_indexers.marketing import MarketingIndexerMixin

logger = get_logger('jarvis.ai_agent.services.rag')


class RAGService(
    InvoiceIndexerMixin,
    EntityIndexerMixin,
    AccountingIndexerMixin,
    EventIndexerMixin,
    CRMIndexerMixin,
    MarketingIndexerMixin,
):
    """
    RAG service for document indexing and retrieval.

    Handles:
    - Indexing JARVIS data (invoices, transactions, companies)
    - Semantic search using embeddings
    - Text search fallback when pgvector unavailable
    - Context formatting for LLM prompts

    Domain-specific indexing is provided by mixins:
      InvoiceIndexerMixin, EntityIndexerMixin, AccountingIndexerMixin,
      EventIndexerMixin, CRMIndexerMixin, MarketingIndexerMixin
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

        # Ensure vector column dimensions match provider
        if self._has_embeddings and self.embedding_service.dimensions:
            try:
                if self.document_repo.has_pgvector():
                    self.document_repo.ensure_column_dimensions(
                        self.embedding_service.dimensions
                    )
            except Exception as e:
                logger.warning(f"Could not verify column dimensions: {e}")

        logger.info(
            f"RAG Service initialized "
            f"(embeddings: {self._has_embeddings}, "
            f"provider: {self.embedding_service.provider_name})"
        )

    # ── Claude enrichment ──────────────────────────────────────

    def _enrich_with_claude(self, raw_text: str, context: str = "business record") -> str:
        """Use Claude Haiku to generate a rich natural-language summary for RAG.

        Falls back to raw_text if Claude is unavailable or fails.
        """
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            try:
                from ..repositories import ModelConfigRepository
                from ..models import LLMProvider
                repo = ModelConfigRepository()
                for cfg in repo.get_by_provider(LLMProvider.CLAUDE):
                    if cfg.api_key_encrypted:
                        api_key = cfg.api_key_encrypted
                        break
            except Exception:
                pass
        if not api_key:
            return raw_text

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                temperature=0.0,
                system=(
                    "You are a data indexing assistant. Given structured data about a "
                    f"{context}, write a concise natural-language summary in 2-4 sentences. "
                    "Include all key facts (names, dates, amounts, status). "
                    "Write in the same language as the data. No markdown, no bullet points."
                ),
                messages=[{"role": "user", "content": raw_text}],
            )
            summary = resp.content[0].text.strip()
            if summary:
                return summary
        except Exception as e:
            logger.debug(f"Claude enrichment failed, using raw text: {e}")

        return raw_text

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
            sources = [
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

            # Rerank with recency boost
            return self._rerank_sources(sources)

        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return []

    @staticmethod
    def _rerank_sources(sources: List['RAGSource']) -> List['RAGSource']:
        """Rerank RAG sources with recency boost.

        Combines similarity score (85%) with a recency factor (15%)
        so recent invoices/events rank higher for queries like "ultima factura".

        Sources with a 'date' in metadata get a recency boost based on how
        recent the date is (within the last 365 days = max boost).
        """
        from datetime import date, datetime

        if not sources or len(sources) <= 1:
            return sources

        today = date.today()

        for src in sources:
            recency = 0.0
            meta = src.metadata or {}

            # Try to extract a date from metadata
            date_str = meta.get('date') or meta.get('start_date') or meta.get('issue_date')
            if date_str:
                try:
                    if isinstance(date_str, str):
                        d = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
                    elif isinstance(date_str, date):
                        d = date_str
                    else:
                        d = None

                    if d:
                        days_ago = (today - d).days
                        # Linear decay: 1.0 for today, 0.0 for 365+ days ago
                        recency = max(0.0, 1.0 - days_ago / 365.0)
                except (ValueError, TypeError):
                    pass

            # Blend: 85% similarity + 15% recency
            src.score = src.score * 0.85 + recency * 0.15

        sources.sort(key=lambda s: s.score, reverse=True)
        return sources

    # Metadata keys to display per source type
    METADATA_DISPLAY_KEYS = {
        'invoice': [
            ('supplier', 'Supplier'), ('invoice_number', 'Invoice'), ('date', 'Date'),
            ('amount', 'Amount'), ('currency', 'Currency'),
        ],
        'transaction': [
            ('vendor_name', 'Vendor'), ('amount', 'Amount'), ('currency', 'Currency'),
            ('date', 'Date'), ('status', 'Status'),
        ],
        'company': [('name', 'Company'), ('cui', 'CUI')],
        'department': [('name', 'Department'), ('company', 'Company'), ('brand', 'Brand')],
        'employee': [('name', 'Employee'), ('department', 'Department'), ('company', 'Company'), ('role', 'Role')],
        'event': [('name', 'Event'), ('company', 'Company'), ('start_date', 'Start'), ('end_date', 'End')],
        'efactura': [
            ('invoice_number', 'Invoice'), ('partner_name', 'Supplier'), ('amount', 'Amount'),
            ('currency', 'Currency'), ('date', 'Date'), ('direction', 'Direction'),
        ],
        'marketing': [
            ('name', 'Project'), ('status', 'Status'), ('type', 'Type'),
            ('company', 'Company'), ('owner', 'Owner'), ('budget', 'Budget'),
        ],
        'approval': [
            ('flow', 'Flow'), ('entity_type', 'Entity'), ('status', 'Status'),
            ('priority', 'Priority'), ('requester', 'Requester'),
        ],
        'tag': [('name', 'Tag'), ('group', 'Group'), ('usage_count', 'Used')],
        'crm_client': [
            ('name', 'Client'), ('type', 'Type'), ('phone', 'Phone'),
            ('email', 'Email'), ('responsible', 'Responsible'),
        ],
        'car_dossier': [
            ('dossier_number', 'Dossier'), ('model', 'Model'), ('brand', 'Brand'),
            ('client', 'Client'), ('status', 'Status'), ('price', 'Price'),
            ('dossier_type', 'Type'),
        ],
        'dms_document': [
            ('doc_number', 'Nr. Doc'), ('category', 'Categorie'), ('company', 'Companie'),
            ('status', 'Status'), ('expiry_date', 'Expira'), ('parties', 'Parti'),
        ],
    }

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
            header = f"[Source {i}: {source.source_type}]"

            # Build metadata using source-type-aware keys
            meta_parts = []
            if source.metadata:
                display_keys = self.METADATA_DISPLAY_KEYS.get(source.source_type, [])
                for key, label in display_keys:
                    val = source.metadata.get(key)
                    if val:
                        meta_parts.append(f"{label}: {val}")

            meta_str = " | ".join(meta_parts) if meta_parts else ""

            entry = f"{header}\n"
            if meta_str:
                entry += f"{meta_str}\n"
            entry += f"{source.snippet}\n"

            entry_tokens = max(1, len(entry) // 3)  # ~3 chars/token (conservative)
            if approx_tokens + entry_tokens > max_tokens:
                break

            context_parts.append(entry)
            approx_tokens += entry_tokens

        return "\n".join(context_parts)

    def _create_snippet(self, content: str, max_length: int = 300) -> str:
        """Create a snippet from content.

        Truncates to ~max_length, but preserves high-criticality values (IBANs,
        VINs, VATs, reg-com) that fall past the cutoff so they stay visible to
        the LLM. Without this, the 300-char cut silently dropped real IBANs from
        10 bank_statement/transaction docs and 341 VINs from car dossiers on
        every query (see scripts/quasar_snippet_report.py).
        """
        if len(content) <= max_length:
            return content

        # Try to break at sentence, else at a word boundary.
        window = content[:max_length]
        last_period = window.rfind('.')
        if last_period > max_length // 2:
            snippet = window[:last_period + 1]
        else:
            last_space = window.rfind(' ')
            snippet = (window[:last_space] + "...") if last_space > 0 else (window + "...")

        # Re-attach critical values the truncation would otherwise drop.
        dropped = dropped_critical_values(content, snippet)
        if dropped:
            snippet = f"{snippet} [key values: {', '.join(dropped)}]"
        return snippet

    # ============== Generic Index Helper ==============

    def _index_document(
        self,
        source_type: RAGSourceType,
        source_id: int,
        source_table: str,
        content: str,
        metadata: Dict[str, Any],
        company_id: Optional[int] = None,
    ) -> ServiceResult:
        """
        Generic document indexing — hash check, upsert, embed.

        Used by all source-type-specific index methods to avoid duplication.
        """
        try:
            content_hash = self.embedding_service.compute_content_hash(content)

            existing = self.document_repo.get_by_source(source_type, source_id)
            if existing and existing.content_hash == content_hash:
                # Content unchanged — but backfill embedding if missing
                if self._has_embeddings and not getattr(existing, 'has_embedding', True):
                    try:
                        emb = self.embedding_service.generate_embedding(content)
                        self.document_repo.update_embedding(existing.id, emb)
                    except Exception as e:
                        logger.warning(f"Backfill embedding failed for {source_type.value} {source_id}: {e}")
                return ServiceResult(success=True, data=existing)

            embedding = None
            if self._has_embeddings:
                try:
                    embedding = self.embedding_service.generate_embedding(content)
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for {source_type.value} {source_id}: {e}")

            document = RAGDocument(
                source_type=source_type,
                source_id=source_id,
                source_table=source_table,
                content=content,
                content_hash=content_hash,
                embedding=embedding,
                metadata=metadata,
                company_id=company_id,
            )

            if existing:
                if embedding:
                    self.document_repo.update_embedding(existing.id, embedding, content_hash)
                document.id = existing.id
            else:
                document = self.document_repo.create(document)

            return ServiceResult(success=True, data=document)

        except Exception as e:
            logger.error(f"Failed to index {source_type.value} {source_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def _lookup_company_id(self, company_name: Optional[str]) -> Optional[int]:
        """Look up company ID from company name."""
        if not company_name:
            return None
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT id FROM companies WHERE company = %s", (company_name,))
            row = cursor.fetchone()
            return row['id'] if row else None
        finally:
            release_db(conn)

    # ============== Company Indexing ==============

    def _fetch_company_data(self, company_id: int) -> Optional[Dict]:
        """Fetch company data from database."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT * FROM companies WHERE id = %s", (company_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_company_content(self, data: Dict) -> str:
        """Build searchable content from company data."""
        parts = []
        if data.get('company'):
            parts.append(f"Company: {data['company']}")
        if data.get('vat'):
            parts.append(f"VAT/CUI: {data['vat']}")
        if data.get('brands'):
            parts.append(f"Brands: {data['brands']}")
        return "\n".join(parts)

    def index_company(self, company_id: int) -> ServiceResult:
        """Index a company for RAG search."""
        data = self._fetch_company_data(company_id)
        if not data:
            return ServiceResult(success=False, error="Company not found")

        content = self._build_company_content(data)
        metadata = {
            'name': data.get('company'),
            'cui': data.get('vat'),
        }
        return self._index_document(
            RAGSourceType.COMPANY, company_id, 'companies', content, metadata, company_id
        )

    def index_companies_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index companies."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT c.id FROM companies c
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'company' AND r.source_id = c.id AND r.is_active = TRUE
                    WHERE r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_company(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} companies")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Company batch indexing failed: {e}")
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
            'embedding_provider': self.embedding_service.provider_name,
            'embedding_dimensions': self.embedding_service.dimensions,
        }

    # ============== Orchestration ==============

    def index_all_sources(self, limit: int = 500) -> ServiceResult:
        """Reindex all source types."""
        results = {}
        total = 0

        batch_methods = [
            ('invoices', self.index_invoices_batch),
            ('companies', self.index_companies_batch),
            ('departments', self.index_departments_batch),
            ('employees', self.index_employees_batch),
            ('transactions', self.index_transactions_batch),
            ('efactura', self.index_efactura_batch),
            ('events', self.index_events_batch),
            ('marketing', self.index_marketing_batch),
            ('approvals', self.index_approvals_batch),
            ('tags', self.index_tags_batch),
            ('crm_clients', self.index_crm_clients_batch),
            ('car_dossiers', self.index_car_dossiers_batch),
            ('bank_statements', self.index_bank_statements_batch),
            ('chart_accounts', self.index_chart_accounts_batch),
            ('bilant_reports', self.index_bilant_reports_batch),
            ('dms_documents', self.index_dms_documents_batch),
        ]

        for name, method in batch_methods:
            try:
                result = method(limit=limit)
                count = result.data.get('indexed', 0) if result.success else 0
                results[name] = count
                total += count
            except Exception as e:
                logger.error(f"Failed to index {name}: {e}")
                results[name] = 0

        logger.info(f"Total indexed across all sources: {total}")
        return ServiceResult(success=True, data={'by_source': results, 'total': total})
