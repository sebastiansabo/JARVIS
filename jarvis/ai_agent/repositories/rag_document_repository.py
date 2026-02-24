"""RAG Document Repository — storage and retrieval for RAG documents.

Supports both pgvector (semantic search) and text search fallback.
"""
from typing import Optional, List, Dict

from psycopg2.extras import Json
from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger
from ..models import RAGDocument, RAGSourceType

logger = get_logger('jarvis.ai_agent.repo.rag_document')


class RAGDocumentRepository(BaseRepository):
    """Repository for RAG documents with vector and text search."""

    def __init__(self):
        """Initialize repository and detect pgvector availability."""
        self._has_pgvector = None

    def _check_pgvector(self, cursor) -> bool:
        """Check if pgvector is available (cached after first call)."""
        if self._has_pgvector is None:
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_type WHERE typname = 'vector'
                    )
                """)
                self._has_pgvector = cursor.fetchone()['exists']
                logger.info(f"pgvector available: {self._has_pgvector}")
            except Exception:
                self._has_pgvector = False
        return self._has_pgvector

    def create(self, document: RAGDocument) -> RAGDocument:
        """Create a new RAG document."""
        def _work(cursor):
            has_pgvector = self._check_pgvector(cursor)

            if has_pgvector and document.embedding:
                cursor.execute("""
                    INSERT INTO ai_agent.rag_documents
                    (source_type, source_id, source_table, content, content_hash,
                     embedding, metadata, company_id, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s)
                    RETURNING id, created_at, updated_at
                """, (
                    document.source_type.value,
                    document.source_id,
                    document.source_table,
                    document.content,
                    document.content_hash,
                    document.embedding,
                    Json(document.metadata) if document.metadata else None,
                    document.company_id,
                    document.is_active,
                ))
            else:
                cursor.execute("""
                    INSERT INTO ai_agent.rag_documents
                    (source_type, source_id, source_table, content, content_hash,
                     metadata, company_id, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at, updated_at
                """, (
                    document.source_type.value,
                    document.source_id,
                    document.source_table,
                    document.content,
                    document.content_hash,
                    Json(document.metadata) if document.metadata else None,
                    document.company_id,
                    document.is_active,
                ))

            row = cursor.fetchone()
            document.id = row['id']
            document.created_at = row['created_at']
            document.updated_at = row['updated_at']
            logger.debug(f"Created RAG document {document.id}")
            return document
        return self.execute_many(_work)

    def update_embedding(self, doc_id: int, embedding: List[float],
                         content_hash: Optional[str] = None) -> bool:
        """Update embedding for a document."""
        def _work(cursor):
            if not self._check_pgvector(cursor):
                logger.warning("Cannot update embedding - pgvector not available")
                return False

            if content_hash:
                cursor.execute("""
                    UPDATE ai_agent.rag_documents
                    SET embedding = %s::vector, content_hash = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                """, (embedding, content_hash, doc_id))
            else:
                cursor.execute("""
                    UPDATE ai_agent.rag_documents
                    SET embedding = %s::vector, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                """, (embedding, doc_id))

            return cursor.fetchone() is not None
        return self.execute_many(_work)

    def search_by_vector(self, embedding: List[float], limit: int = 5,
                         company_id: Optional[int] = None,
                         source_types: Optional[List[RAGSourceType]] = None,
                         min_score: float = 0.0) -> List[RAGDocument]:
        """Search documents by vector similarity (cosine distance)."""
        def _work(cursor):
            if not self._check_pgvector(cursor):
                logger.warning("pgvector not available, falling back to text search")
                return []

            filters = ["is_active = TRUE"]
            params = [embedding]

            if company_id:
                filters.append("(company_id = %s OR company_id IS NULL)")
                params.append(company_id)

            if source_types:
                placeholders = ', '.join(['%s'] * len(source_types))
                filters.append(f"source_type IN ({placeholders})")
                params.extend([st.value for st in source_types])

            where_clause = ' AND '.join(filters)
            params.extend([embedding, limit])

            cursor.execute(f"""
                SELECT id, source_type, source_id, source_table,
                       content, content_hash, metadata, company_id,
                       is_active, created_at, updated_at,
                       1 - (embedding <=> %s::vector) as score
                FROM ai_agent.rag_documents
                WHERE {where_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, params)

            documents = []
            for row in cursor.fetchall():
                if row['score'] >= min_score:
                    doc = self._row_to_document(row)
                    doc.score = row['score']
                    documents.append(doc)

            logger.debug(f"Vector search found {len(documents)} documents")
            return documents
        return self.execute_many(_work)

    def search_by_text(self, query: str, limit: int = 5,
                       company_id: Optional[int] = None,
                       source_types: Optional[List[RAGSourceType]] = None) -> List[RAGDocument]:
        """Search documents by full-text search (fallback when pgvector unavailable)."""
        filters = ["is_active = TRUE"]
        params: list = [query]

        if company_id:
            filters.append("(company_id = %s OR company_id IS NULL)")
            params.append(company_id)

        if source_types:
            placeholders = ', '.join(['%s'] * len(source_types))
            filters.append(f"source_type IN ({placeholders})")
            params.extend([st.value for st in source_types])

        where_clause = ' AND '.join(filters)
        params.extend([query, limit])

        rows = self.query_all(f"""
            SELECT id, source_type, source_id, source_table,
                   content, content_hash, metadata, company_id,
                   is_active, created_at, updated_at,
                   ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', %s)) as score
            FROM ai_agent.rag_documents
            WHERE {where_clause}
              AND to_tsvector('simple', content) @@ plainto_tsquery('simple', %s)
            ORDER BY score DESC
            LIMIT %s
        """, params)

        documents = []
        for row in rows:
            doc = self._row_to_document(row)
            doc.score = float(row['score']) if row['score'] else 0.0
            documents.append(doc)

        logger.debug(f"Text search found {len(documents)} documents")
        return documents

    def get_by_source(self, source_type: RAGSourceType,
                      source_id: int) -> Optional[RAGDocument]:
        """Get document by source."""
        row = self.query_one("""
            SELECT id, source_type, source_id, source_table,
                   content, content_hash, metadata, company_id,
                   is_active, created_at, updated_at
            FROM ai_agent.rag_documents
            WHERE source_type = %s AND source_id = %s AND is_active = TRUE
        """, (source_type.value, source_id))
        return self._row_to_document(row) if row else None

    def get_documents_without_embedding(self, limit: int = 100) -> List[RAGDocument]:
        """Get documents that don't have embeddings yet (for batch embedding)."""
        def _work(cursor):
            if not self._check_pgvector(cursor):
                return []

            cursor.execute("""
                SELECT id, source_type, source_id, source_table,
                       content, content_hash, metadata, company_id,
                       is_active, created_at, updated_at
                FROM ai_agent.rag_documents
                WHERE embedding IS NULL AND is_active = TRUE
                LIMIT %s
            """, (limit,))
            return [self._row_to_document(row) for row in cursor.fetchall()]
        return self.execute_many(_work)

    def delete_by_source(self, source_type: RAGSourceType, source_id: int) -> bool:
        """Soft delete document by source."""
        return self.execute("""
            UPDATE ai_agent.rag_documents
            SET is_active = FALSE, updated_at = NOW()
            WHERE source_type = %s AND source_id = %s
        """, (source_type.value, source_id)) > 0

    def count_by_source_type(self) -> Dict[str, int]:
        """Count documents by source type."""
        rows = self.query_all("""
            SELECT source_type, COUNT(*) as count
            FROM ai_agent.rag_documents
            WHERE is_active = TRUE
            GROUP BY source_type
        """)
        return {row['source_type']: row['count'] for row in rows}

    def has_pgvector(self) -> bool:
        """Check if pgvector is available."""
        def _work(cursor):
            return self._check_pgvector(cursor)
        return self.execute_many(_work)

    def _row_to_document(self, row: dict) -> RAGDocument:
        """Convert database row to RAGDocument model."""
        return RAGDocument(
            id=row['id'],
            source_type=RAGSourceType(row['source_type']),
            source_id=row['source_id'],
            source_table=row['source_table'],
            content=row['content'],
            content_hash=row['content_hash'],
            metadata=row['metadata'] or {},
            company_id=row['company_id'],
            is_active=row['is_active'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
