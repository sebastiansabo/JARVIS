"""
RAG Service

Retrieval Augmented Generation service for semantic search and context retrieval.
Indexes JARVIS data (invoices, transactions, etc.) for AI queries.
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

    # ============== Department Indexing ==============

    def _fetch_department_data(self, dept_id: int) -> Optional[Dict]:
        """Fetch department structure data from database."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT * FROM department_structure WHERE id = %s", (dept_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_department_content(self, data: Dict) -> str:
        """Build searchable content from department data."""
        parts = []
        if data.get('department'):
            parts.append(f"Department: {data['department']}")
        if data.get('subdepartment'):
            parts.append(f"Subdepartment: {data['subdepartment']}")
        if data.get('company'):
            parts.append(f"Company: {data['company']}")
        if data.get('brand'):
            parts.append(f"Brand: {data['brand']}")
        if data.get('manager'):
            parts.append(f"Manager: {data['manager']}")
        return "\n".join(parts)

    def index_department(self, dept_id: int) -> ServiceResult:
        """Index a department for RAG search."""
        data = self._fetch_department_data(dept_id)
        if not data:
            return ServiceResult(success=False, error="Department not found")

        content = self._build_department_content(data)
        metadata = {
            'name': data.get('department'),
            'subdepartment': data.get('subdepartment'),
            'company': data.get('company'),
            'brand': data.get('brand'),
        }
        company_id = self._lookup_company_id(data.get('company'))
        return self._index_document(
            RAGSourceType.DEPARTMENT, dept_id, 'department_structure', content, metadata, company_id
        )

    def index_departments_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index departments."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT d.id FROM department_structure d
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'department' AND r.source_id = d.id AND r.is_active = TRUE
                    WHERE r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_department(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} departments")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Department batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Employee Indexing ==============

    def _fetch_employee_data(self, user_id: int) -> Optional[Dict]:
        """Fetch employee/user data from database with org unit and permissions."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT u.*, r.name as role_name,
                       ds.company as org_company, ds.brand as org_brand,
                       ds.department as org_department, ds.subdepartment as org_subdepartment,
                       ds.manager as org_manager
                FROM users u
                LEFT JOIN roles r ON r.id = u.role_id
                LEFT JOIN department_structure ds ON ds.id = u.org_unit_id
                WHERE u.id = %s AND u.is_active = TRUE
            """, (user_id,))
            row = cursor.fetchone()
            if not row:
                return None

            # Fetch permission labels
            cursor.execute("""
                SELECT p.module_label, p.entity_label, p.action_label
                FROM permissions_v2 p
                JOIN role_permissions_v2 rp ON rp.permission_id = p.id
                WHERE rp.role_id = %s
                ORDER BY p.module_label, p.entity_label
            """, (row.get('role_id'),))
            row['permissions'] = [
                f"{r2['module_label']}/{r2['entity_label']}: {r2['action_label']}"
                for r2 in cursor.fetchall()
            ]
            return row
        finally:
            release_db(conn)

    def _build_employee_content(self, data: Dict) -> str:
        """Build searchable content from employee data with Claude enrichment."""
        parts = []
        if data.get('name'):
            parts.append(f"Employee: {data['name']}")
        if data.get('email'):
            parts.append(f"Email: {data['email']}")
        if data.get('phone'):
            parts.append(f"Phone: {data['phone']}")
        # Prefer org unit fields over direct user fields
        company = data.get('org_company') or data.get('company')
        department = data.get('org_department') or data.get('department')
        subdepartment = data.get('org_subdepartment') or data.get('subdepartment')
        brand = data.get('org_brand') or data.get('brand')
        manager = data.get('org_manager')
        if company:
            parts.append(f"Company: {company}")
        if department:
            parts.append(f"Department: {department}")
        if subdepartment:
            parts.append(f"Subdepartment: {subdepartment}")
        if brand:
            parts.append(f"Brand: {brand}")
        if manager:
            parts.append(f"Manager: {manager}")
        if data.get('role_name'):
            parts.append(f"Role: {data['role_name']}")
        # Permissions
        perms = data.get('permissions', [])
        if perms:
            parts.append(f"Permissions: {', '.join(perms)}")
        # Access flags
        access = []
        if data.get('can_access_accounting'):
            access.append('Accounting')
        if data.get('can_add_invoices'):
            access.append('Add Invoices')
        if data.get('can_delete_invoices'):
            access.append('Delete Invoices')
        if data.get('can_access_settings'):
            access.append('Settings')
        if data.get('can_access_connectors'):
            access.append('Connectors')
        if access:
            parts.append(f"Access: {', '.join(access)}")
        # Dates
        if data.get('created_at'):
            parts.append(f"Hire date (account created): {data['created_at']}")
        if data.get('last_login'):
            parts.append(f"Last login: {data['last_login']}")

        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "employee profile")

    def index_employee(self, user_id: int) -> ServiceResult:
        """Index an employee for RAG search."""
        data = self._fetch_employee_data(user_id)
        if not data:
            return ServiceResult(success=False, error="Employee not found")

        content = self._build_employee_content(data)
        metadata = {
            'name': data.get('name'),
            'department': data.get('department'),
            'company': data.get('company'),
            'role': data.get('role_name'),
        }
        company_id = self._lookup_company_id(data.get('company'))
        return self._index_document(
            RAGSourceType.EMPLOYEE, user_id, 'users', content, metadata, company_id
        )

    def index_employees_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index employees."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT u.id FROM users u
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'employee' AND r.source_id = u.id AND r.is_active = TRUE
                    WHERE u.is_active = TRUE AND r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_employee(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} employees")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Employee batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

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

    # ============== HR Event Indexing ==============

    def _fetch_event_data(self, event_id: int) -> Optional[Dict]:
        """Fetch HR event data with individual bonus details."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT e.*,
                       COUNT(b.id) as bonus_count,
                       COALESCE(SUM(b.bonus_net), 0) as total_bonus_net
                FROM hr.events e
                LEFT JOIN hr.event_bonuses b ON b.event_id = e.id
                WHERE e.id = %s
                GROUP BY e.id
            """, (event_id,))
            event = cursor.fetchone()
            if not event:
                return None
            data = dict(event)
            # Fetch individual bonuses
            cursor.execute("""
                SELECT u.name as employee, b.year, b.month,
                       b.bonus_days, b.bonus_net, b.details,
                       b.participation_start, b.participation_end
                FROM hr.event_bonuses b
                LEFT JOIN users u ON u.id = b.user_id
                WHERE b.event_id = %s
                ORDER BY u.name
            """, (event_id,))
            data['bonuses'] = [dict(r) for r in cursor.fetchall()]
            return data
        finally:
            release_db(conn)

    def _build_event_content(self, data: Dict) -> str:
        """Build searchable content from HR event data, enriched via Claude."""
        parts = []
        if data.get('name'):
            parts.append(f"HR Event: {data['name']}")
        if data.get('company'):
            parts.append(f"Company: {data['company']}")
        if data.get('brand'):
            parts.append(f"Brand: {data['brand']}")
        if data.get('start_date'):
            parts.append(f"Start: {data['start_date']}")
        if data.get('end_date'):
            parts.append(f"End: {data['end_date']}")
        if data.get('description'):
            parts.append(f"Description: {data['description']}")
        if data.get('bonus_count'):
            parts.append(f"Bonuses: {data['bonus_count']} entries, Total: {data.get('total_bonus_net', 0)} RON")
        for b in data.get('bonuses', []):
            line = f"Bonus: {b.get('employee', '?')} — {b.get('bonus_net', 0)} RON"
            if b.get('bonus_days'):
                line += f", {b['bonus_days']} days"
            if b.get('year') and b.get('month'):
                line += f" ({b['year']}/{b['month']:02d})"
            parts.append(line)
        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "HR event with employee bonuses")

    def index_event(self, event_id: int) -> ServiceResult:
        """Index an HR event for RAG search."""
        data = self._fetch_event_data(event_id)
        if not data:
            return ServiceResult(success=False, error="HR event not found")

        content = self._build_event_content(data)
        metadata = {
            'name': data.get('name'),
            'company': data.get('company'),
            'brand': data.get('brand'),
            'start_date': str(data.get('start_date', '')),
            'end_date': str(data.get('end_date', '')),
            'bonus_count': data.get('bonus_count', 0),
        }
        company_id = self._lookup_company_id(data.get('company'))
        return self._index_document(
            RAGSourceType.EVENT, event_id, 'hr.events', content, metadata, company_id
        )

    def index_events_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index HR events."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT e.id FROM hr.events e
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'event' AND r.source_id = e.id AND r.is_active = TRUE
                    WHERE r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_event(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} HR events")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"HR event batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Marketing Project Indexing ==============

    def _fetch_marketing_data(self, project_id: int) -> Optional[Dict]:
        """Fetch marketing project data with budget lines, KPIs, and team."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT p.*,
                       u.name as owner_name,
                       c.company as company_name,
                       COALESCE(SUM(bl.planned_amount), 0) as total_planned,
                       COALESCE(SUM(bl.spent_amount), 0) as total_spent,
                       COUNT(DISTINCT pk.id) as kpi_count
                FROM mkt_projects p
                LEFT JOIN users u ON u.id = p.owner_id
                LEFT JOIN companies c ON c.id = p.company_id
                LEFT JOIN mkt_budget_lines bl ON bl.project_id = p.id
                LEFT JOIN mkt_project_kpis pk ON pk.project_id = p.id
                WHERE p.id = %s AND p.deleted_at IS NULL
                GROUP BY p.id, u.name, c.company
            """, (project_id,))
            project = cursor.fetchone()
            if not project:
                return None
            data = dict(project)
            # Budget lines
            cursor.execute("""
                SELECT channel, description, planned_amount, spent_amount, currency, agency_name
                FROM mkt_budget_lines WHERE project_id = %s ORDER BY planned_amount DESC
            """, (project_id,))
            data['budget_lines'] = [dict(r) for r in cursor.fetchall()]
            # KPIs
            cursor.execute("""
                SELECT kd.name as kpi_name, kd.unit, pk.target_value, pk.current_value, pk.channel, pk.status
                FROM mkt_project_kpis pk
                JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
                WHERE pk.project_id = %s
            """, (project_id,))
            data['kpis'] = [dict(r) for r in cursor.fetchall()]
            # Team members
            cursor.execute("""
                SELECT u.name, pm.role FROM mkt_project_members pm
                JOIN users u ON u.id = pm.user_id
                WHERE pm.project_id = %s
            """, (project_id,))
            data['members'] = [dict(r) for r in cursor.fetchall()]
            return data
        finally:
            release_db(conn)

    def _build_marketing_content(self, data: Dict) -> str:
        """Build searchable content from marketing project data, enriched via Claude."""
        parts = []
        if data.get('name'):
            parts.append(f"Marketing Project: {data['name']}")
        if data.get('status'):
            parts.append(f"Status: {data['status']}")
        if data.get('project_type'):
            parts.append(f"Type: {data['project_type']}")
        if data.get('company_name'):
            parts.append(f"Company: {data['company_name']}")
        if data.get('owner_name'):
            parts.append(f"Owner: {data['owner_name']}")
        if data.get('description'):
            parts.append(f"Description: {data['description'][:500]}")
        if data.get('objective'):
            parts.append(f"Objective: {data['objective'][:300]}")
        if data.get('target_audience'):
            parts.append(f"Target Audience: {data['target_audience'][:200]}")
        if data.get('start_date'):
            parts.append(f"Start: {data['start_date']}")
        if data.get('end_date'):
            parts.append(f"End: {data['end_date']}")
        if data.get('total_planned'):
            parts.append(f"Planned Budget: {data['total_planned']}")
        if data.get('total_spent'):
            parts.append(f"Spent Budget: {data['total_spent']}")
        for bl in data.get('budget_lines', []):
            line = f"Budget: {bl.get('channel', '?')} — planned {bl.get('planned_amount', 0)}, spent {bl.get('spent_amount', 0)} {bl.get('currency', 'RON')}"
            if bl.get('agency_name'):
                line += f" (agency: {bl['agency_name']})"
            parts.append(line)
        for kpi in data.get('kpis', []):
            parts.append(f"KPI: {kpi.get('kpi_name', '?')} — target {kpi.get('target_value', '?')}, current {kpi.get('current_value', 0)} {kpi.get('unit', '')} [{kpi.get('status', '')}]")
        for m in data.get('members', []):
            parts.append(f"Team: {m.get('name', '?')} ({m.get('role', '?')})")
        raw = "\n".join(parts)
        return self._enrich_with_claude(raw, "marketing project with budget and KPIs")

    def index_marketing(self, project_id: int) -> ServiceResult:
        """Index a marketing project for RAG search."""
        data = self._fetch_marketing_data(project_id)
        if not data:
            return ServiceResult(success=False, error="Marketing project not found")

        content = self._build_marketing_content(data)
        metadata = {
            'name': data.get('name'),
            'status': data.get('status'),
            'type': data.get('project_type'),
            'company': data.get('company_name'),
            'owner': data.get('owner_name'),
            'budget': str(data.get('total_planned', 0)),
        }
        return self._index_document(
            RAGSourceType.MARKETING, project_id, 'mkt_projects', content, metadata, data.get('company_id')
        )

    def index_marketing_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index marketing projects."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT p.id FROM mkt_projects p
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'marketing' AND r.source_id = p.id AND r.is_active = TRUE
                    WHERE p.deleted_at IS NULL
                      AND (r.id IS NULL OR r.updated_at < p.updated_at)
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_marketing(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} marketing projects")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Marketing batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Approval Request Indexing ==============

    def _fetch_approval_data(self, request_id: int) -> Optional[Dict]:
        """Fetch approval request data with flow and decision info."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT ar.*,
                       af.name as flow_name,
                       af.entity_type,
                       u.name as requester_name,
                       (SELECT COUNT(*) FROM approval_decisions ad WHERE ad.request_id = ar.id) as decision_count
                FROM approval_requests ar
                LEFT JOIN approval_flows af ON af.id = ar.flow_id
                LEFT JOIN users u ON u.id = ar.requested_by
                WHERE ar.id = %s
            """, (request_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_approval_content(self, data: Dict) -> str:
        """Build searchable content from approval request data."""
        parts = []
        if data.get('flow_name'):
            parts.append(f"Approval Flow: {data['flow_name']}")
        if data.get('entity_type'):
            parts.append(f"Entity Type: {data['entity_type']}")
        if data.get('entity_id'):
            parts.append(f"Entity ID: {data['entity_id']}")
        if data.get('status'):
            parts.append(f"Status: {data['status']}")
        if data.get('priority'):
            parts.append(f"Priority: {data['priority']}")
        if data.get('requester_name'):
            parts.append(f"Requested By: {data['requester_name']}")
        if data.get('requested_at'):
            parts.append(f"Requested: {data['requested_at']}")
        if data.get('resolved_at'):
            parts.append(f"Resolved: {data['resolved_at']}")
        if data.get('resolution_note'):
            parts.append(f"Resolution: {data['resolution_note'][:300]}")
        if data.get('decision_count'):
            parts.append(f"Decisions: {data['decision_count']}")
        # Include context snapshot summary
        ctx = data.get('context_snapshot')
        if ctx and isinstance(ctx, dict):
            for key in ('name', 'title', 'supplier', 'amount', 'invoice_number'):
                if ctx.get(key):
                    parts.append(f"Context {key}: {ctx[key]}")
        return "\n".join(parts)

    def index_approval(self, request_id: int) -> ServiceResult:
        """Index an approval request for RAG search."""
        data = self._fetch_approval_data(request_id)
        if not data:
            return ServiceResult(success=False, error="Approval request not found")

        content = self._build_approval_content(data)
        metadata = {
            'flow': data.get('flow_name'),
            'entity_type': data.get('entity_type'),
            'status': data.get('status'),
            'priority': data.get('priority'),
            'requester': data.get('requester_name'),
        }
        return self._index_document(
            RAGSourceType.APPROVAL, request_id, 'approval_requests', content, metadata
        )

    def index_approvals_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index approval requests."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT ar.id FROM approval_requests ar
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'approval' AND r.source_id = ar.id AND r.is_active = TRUE
                    WHERE r.id IS NULL OR r.updated_at < ar.updated_at
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_approval(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} approval requests")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Approval batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Tag Indexing ==============

    def _fetch_tag_data(self, tag_id: int) -> Optional[Dict]:
        """Fetch tag data with group and usage count."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("""
                SELECT t.*,
                       tg.name as group_name,
                       tg.color as group_color,
                       COUNT(et.id) as usage_count
                FROM tags t
                LEFT JOIN tag_groups tg ON tg.id = t.group_id
                LEFT JOIN entity_tags et ON et.tag_id = t.id
                WHERE t.id = %s AND t.is_active = TRUE
                GROUP BY t.id, tg.name, tg.color
            """, (tag_id,))
            return cursor.fetchone()
        finally:
            release_db(conn)

    def _build_tag_content(self, data: Dict) -> str:
        """Build searchable content from tag data."""
        parts = []
        if data.get('name'):
            parts.append(f"Tag: {data['name']}")
        if data.get('group_name'):
            parts.append(f"Group: {data['group_name']}")
        if data.get('color'):
            parts.append(f"Color: {data['color']}")
        if data.get('usage_count'):
            parts.append(f"Used on: {data['usage_count']} entities")
        return "\n".join(parts)

    def index_tag(self, tag_id: int) -> ServiceResult:
        """Index a tag for RAG search."""
        data = self._fetch_tag_data(tag_id)
        if not data:
            return ServiceResult(success=False, error="Tag not found")

        content = self._build_tag_content(data)
        metadata = {
            'name': data.get('name'),
            'group': data.get('group_name'),
            'color': data.get('color'),
            'usage_count': data.get('usage_count', 0),
        }
        return self._index_document(
            RAGSourceType.TAG, tag_id, 'tags', content, metadata
        )

    def index_tags_batch(self, limit: int = 500) -> ServiceResult:
        """Batch index tags."""
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT t.id FROM tags t
                    LEFT JOIN ai_agent.rag_documents r
                        ON r.source_type = 'tag' AND r.source_id = t.id AND r.is_active = TRUE
                    WHERE t.is_active = TRUE AND r.id IS NULL
                    LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)

            indexed = 0
            for row in rows:
                if self.index_tag(row['id']).success:
                    indexed += 1

            logger.info(f"Batch indexed {indexed} tags")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Tag batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== CRM Source Indexing ==============

    def _build_crm_client_content(self, data: dict) -> str:
        parts = [f"Client CRM: {data.get('display_name', '')}"]
        if data.get('client_type'):
            parts.append(f"Tip: {'Persoana fizica' if data['client_type'] == 'person' else 'Persoana juridica'}")
        for key, label in [('phone', 'Telefon'), ('email', 'Email'), ('street', 'Adresa'),
                           ('city', 'Oras'), ('region', 'Judet'), ('responsible', 'Responsabil')]:
            if data.get(key):
                parts.append(f"{label}: {data[key]}")
        return '\n'.join(parts)

    def index_crm_client(self, client_id: int) -> ServiceResult:
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute('SELECT * FROM crm_clients WHERE id = %s', (client_id,))
                data = cursor.fetchone()
            finally:
                release_db(conn)
            if not data:
                return ServiceResult(success=False, error='Client not found')
            if data.get('is_blacklisted'):
                return ServiceResult(success=False, error='Client is blacklisted — skipping indexing')
            content = self._build_crm_client_content(data)
            metadata = {
                'name': data.get('display_name'), 'type': data.get('client_type'),
                'phone': data.get('phone'), 'email': data.get('email'),
                'responsible': data.get('responsible'),
            }
            return self._index_document(
                RAGSourceType.CRM_CLIENT, client_id, 'crm_clients',
                content, metadata, company_id=None,
            )
        except Exception as e:
            logger.error(f"CRM client indexing failed for {client_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_crm_clients_batch(self, limit: int = 500) -> ServiceResult:
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute("""
                    SELECT c.id FROM crm_clients c
                    WHERE c.merged_into_id IS NULL
                      AND (c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL)
                      AND NOT EXISTS (
                        SELECT 1 FROM ai_agent.rag_documents r
                        WHERE r.source_type = 'crm_client'
                          AND r.source_id = c.id
                          AND r.is_active = TRUE
                          AND r.updated_at >= c.updated_at
                      )
                    ORDER BY c.updated_at DESC LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)
            indexed = 0
            for row in rows:
                if self.index_crm_client(row['id']).success:
                    indexed += 1
            logger.info(f"Batch indexed {indexed} CRM clients")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"CRM client batch indexing failed: {e}")
            return ServiceResult(success=False, error=str(e))

    def _build_car_dossier_content(self, data: dict) -> str:
        dtype = 'noua' if data.get('source') == 'nw' else 'second-hand'
        parts = [f"Dosar masina {dtype} Nr. {data.get('dossier_number', '')}"]
        for key, label in [('model_name', 'Model'), ('brand', 'Marca'),
                           ('dossier_status', 'Status dosar'), ('buyer_name', 'Client'),
                           ('owner_name', 'Proprietar'), ('fuel_type', 'Combustibil'),
                           ('color', 'Culoare'), ('vin', 'VIN'),
                           ('dealer_name', 'Dealer'), ('sales_person', 'Vanzator'),
                           ('customer_group', 'Grup client')]:
            if data.get(key):
                parts.append(f"{label}: {data[key]}")
        # Financials
        for key, label in [('list_price', 'Pret lista'), ('sale_price_net', 'Pret vanzare net'),
                           ('purchase_price_net', 'Pret achizitie net'), ('gross_profit', 'Profit brut'),
                           ('gw_gross_value', 'PV brut')]:
            val = data.get(key)
            if val is not None and val != 0:
                parts.append(f"{label}: {val}")
        # Dates
        for key, label in [('contract_date', 'Data contract'), ('delivery_date', 'Data livrare'),
                           ('registration_date', 'Data inmatriculare')]:
            if data.get(key):
                parts.append(f"{label}: {data[key]}")
        return '\n'.join(parts)

    def index_car_dossier(self, dossier_id: int) -> ServiceResult:
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute('SELECT * FROM crm_deals WHERE id = %s', (dossier_id,))
                data = cursor.fetchone()
            finally:
                release_db(conn)
            if not data:
                return ServiceResult(success=False, error='Dossier not found')
            content = self._build_car_dossier_content(data)
            price = data.get('sale_price_net') or data.get('list_price') or data.get('gw_gross_value')
            metadata = {
                'dossier_number': data.get('dossier_number'), 'model': data.get('model_name'),
                'brand': data.get('brand'), 'client': data.get('buyer_name'),
                'status': data.get('dossier_status'), 'price': str(price) if price else None,
                'dossier_type': data.get('source'),
                'date': str(data.get('contract_date') or data.get('delivery_date') or ''),
            }
            return self._index_document(
                RAGSourceType.CAR_DOSSIER, dossier_id, 'crm_deals',
                content, metadata, company_id=None,
            )
        except Exception as e:
            logger.error(f"Car dossier indexing failed for {dossier_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def index_car_dossiers_batch(self, limit: int = 500) -> ServiceResult:
        try:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                # Use NOT EXISTS to avoid duplicates from LEFT JOIN
                # when multiple RAG docs exist for the same source_id
                cursor.execute("""
                    SELECT d.id FROM crm_deals d
                    WHERE (d.client_id IS NULL OR d.client_id NOT IN (
                        SELECT id FROM crm_clients WHERE is_blacklisted = TRUE
                    ))
                    AND NOT EXISTS (
                        SELECT 1 FROM ai_agent.rag_documents r
                        WHERE r.source_type = 'car_dossier'
                          AND r.source_id = d.id
                          AND r.is_active = TRUE
                          AND r.updated_at >= d.updated_at
                    )
                    ORDER BY d.updated_at DESC LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
            finally:
                release_db(conn)
            indexed = 0
            for row in rows:
                if self.index_car_dossier(row['id']).success:
                    indexed += 1
            logger.info(f"Batch indexed {indexed} car dossiers")
            return ServiceResult(success=True, data={'indexed': indexed})
        except Exception as e:
            logger.error(f"Car dossier batch indexing failed: {e}")
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
