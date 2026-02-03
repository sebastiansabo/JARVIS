"""
RAG Document Repository

Database operations for RAG document storage and retrieval.
Supports both pgvector (semantic search) and text search fallback.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ..models import RAGDocument, RAGSourceType

logger = get_logger('jarvis.ai_agent.repo.rag_document')


class RAGDocumentRepository:
    """
    Repository for RAG documents.

    Supports:
    - Vector similarity search (pgvector)
    - Full-text search fallback
    - Document CRUD operations
    """

    def __init__(self):
        """Initialize repository and detect pgvector availability."""
        self._has_pgvector = None

    def _check_pgvector(self, cursor) -> bool:
        """Check if pgvector is available."""
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
        """
        Create a new RAG document.

        Args:
            document: RAGDocument to create

        Returns:
            Created RAGDocument with ID
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            has_pgvector = self._check_pgvector(cursor)

            if has_pgvector and document.embedding:
                # Insert with embedding
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
                    document.metadata,
                    document.company_id,
                    document.is_active,
                ))
            else:
                # Insert without embedding (text search fallback)
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
                    document.metadata,
                    document.company_id,
                    document.is_active,
                ))

            row = cursor.fetchone()
            conn.commit()

            document.id = row['id']
            document.created_at = row['created_at']
            document.updated_at = row['updated_at']

            logger.debug(f"Created RAG document {document.id}")
            return document

        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating RAG document: {e}")
            raise

        finally:
            release_db(conn)

    def update_embedding(
        self,
        doc_id: int,
        embedding: List[float],
        content_hash: Optional[str] = None,
    ) -> bool:
        """
        Update embedding for a document.

        Args:
            doc_id: Document ID
            embedding: New embedding vector
            content_hash: Optional new content hash

        Returns:
            True if updated
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
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

            row = cursor.fetchone()
            conn.commit()
            return row is not None

        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating embedding: {e}")
            raise

        finally:
            release_db(conn)

    def search_by_vector(
        self,
        embedding: List[float],
        limit: int = 5,
        company_id: Optional[int] = None,
        source_types: Optional[List[RAGSourceType]] = None,
        min_score: float = 0.0,
    ) -> List[RAGDocument]:
        """
        Search documents by vector similarity (cosine distance).

        Args:
            embedding: Query embedding vector
            limit: Maximum results
            company_id: Optional company filter for access control
            source_types: Optional source type filter
            min_score: Minimum similarity score (0-1)

        Returns:
            List of RAGDocuments with scores
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            if not self._check_pgvector(cursor):
                logger.warning("pgvector not available, falling back to text search")
                return []

            # Build query with filters
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
            params.append(limit)

            # Cosine similarity: 1 - cosine_distance
            cursor.execute(f"""
                SELECT id, source_type, source_id, source_table,
                       content, content_hash, metadata, company_id,
                       is_active, created_at, updated_at,
                       1 - (embedding <=> %s::vector) as score
                FROM ai_agent.rag_documents
                WHERE {where_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, [embedding] + params[1:-1] + [embedding, limit])

            documents = []
            for row in cursor.fetchall():
                if row['score'] >= min_score:
                    doc = self._row_to_document(row)
                    doc.score = row['score']
                    documents.append(doc)

            logger.debug(f"Vector search found {len(documents)} documents")
            return documents

        finally:
            release_db(conn)

    def search_by_text(
        self,
        query: str,
        limit: int = 5,
        company_id: Optional[int] = None,
        source_types: Optional[List[RAGSourceType]] = None,
    ) -> List[RAGDocument]:
        """
        Search documents by full-text search (fallback when pgvector unavailable).

        Args:
            query: Search query text
            limit: Maximum results
            company_id: Optional company filter
            source_types: Optional source type filter

        Returns:
            List of RAGDocuments with relevance scores
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            # Build query with filters
            filters = ["is_active = TRUE"]
            params = [query]

            if company_id:
                filters.append("(company_id = %s OR company_id IS NULL)")
                params.append(company_id)

            if source_types:
                placeholders = ', '.join(['%s'] * len(source_types))
                filters.append(f"source_type IN ({placeholders})")
                params.extend([st.value for st in source_types])

            where_clause = ' AND '.join(filters)
            params.append(limit)

            cursor.execute(f"""
                SELECT id, source_type, source_id, source_table,
                       content, content_hash, metadata, company_id,
                       is_active, created_at, updated_at,
                       ts_rank(to_tsvector('english', content), plainto_tsquery('english', %s)) as score
                FROM ai_agent.rag_documents
                WHERE {where_clause}
                  AND to_tsvector('english', content) @@ plainto_tsquery('english', %s)
                ORDER BY score DESC
                LIMIT %s
            """, [query] + params[1:-1] + [query, limit])

            documents = []
            for row in cursor.fetchall():
                doc = self._row_to_document(row)
                doc.score = float(row['score']) if row['score'] else 0.0
                documents.append(doc)

            logger.debug(f"Text search found {len(documents)} documents")
            return documents

        finally:
            release_db(conn)

    def get_by_source(
        self,
        source_type: RAGSourceType,
        source_id: int,
    ) -> Optional[RAGDocument]:
        """
        Get document by source.

        Args:
            source_type: Source type
            source_id: Source record ID

        Returns:
            RAGDocument or None
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                SELECT id, source_type, source_id, source_table,
                       content, content_hash, metadata, company_id,
                       is_active, created_at, updated_at
                FROM ai_agent.rag_documents
                WHERE source_type = %s AND source_id = %s AND is_active = TRUE
            """, (source_type.value, source_id))

            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_document(row)

        finally:
            release_db(conn)

    def get_documents_without_embedding(
        self,
        limit: int = 100,
    ) -> List[RAGDocument]:
        """
        Get documents that don't have embeddings yet.

        Used for batch embedding generation.

        Args:
            limit: Maximum documents to return

        Returns:
            List of RAGDocuments without embeddings
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
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

        finally:
            release_db(conn)

    def delete_by_source(
        self,
        source_type: RAGSourceType,
        source_id: int,
    ) -> bool:
        """
        Soft delete document by source.

        Args:
            source_type: Source type
            source_id: Source record ID

        Returns:
            True if deleted
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                UPDATE ai_agent.rag_documents
                SET is_active = FALSE, updated_at = NOW()
                WHERE source_type = %s AND source_id = %s
                RETURNING id
            """, (source_type.value, source_id))

            row = cursor.fetchone()
            conn.commit()
            return row is not None

        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting RAG document: {e}")
            raise

        finally:
            release_db(conn)

    def count_by_source_type(self) -> Dict[str, int]:
        """
        Count documents by source type.

        Returns:
            Dict mapping source_type to count
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                SELECT source_type, COUNT(*) as count
                FROM ai_agent.rag_documents
                WHERE is_active = TRUE
                GROUP BY source_type
            """)

            return {row['source_type']: row['count'] for row in cursor.fetchall()}

        finally:
            release_db(conn)

    def has_pgvector(self) -> bool:
        """Check if pgvector is available."""
        conn = get_db()
        cursor = get_cursor(conn)
        try:
            return self._check_pgvector(cursor)
        finally:
            release_db(conn)

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
