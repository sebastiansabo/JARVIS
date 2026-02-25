"""Knowledge Repository — learned patterns from positive feedback."""

from typing import Optional, List
from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger

logger = get_logger('jarvis.ai_agent.repo.knowledge')


class KnowledgeRepository(BaseRepository):
    """Repository for learned knowledge patterns."""

    def create(self, pattern: str, category: str, embedding: Optional[list] = None) -> dict:
        """Create a new knowledge pattern."""
        def _work(cursor):
            if embedding:
                try:
                    cursor.execute("""
                        INSERT INTO ai_agent.learned_knowledge (pattern, category, embedding)
                        VALUES (%s, %s, %s::vector)
                        RETURNING id, pattern, category, source_count, confidence, is_active, created_at
                    """, (pattern, category, embedding))
                    return dict(cursor.fetchone())
                except Exception:
                    # embedding column may not exist (no pgvector), fallback
                    cursor.connection.rollback()
                    pass
            cursor.execute("""
                INSERT INTO ai_agent.learned_knowledge (pattern, category)
                VALUES (%s, %s)
                RETURNING id, pattern, category, source_count, confidence, is_active, created_at
            """, (pattern, category))
            return dict(cursor.fetchone())
        return self.execute_many(_work)

    def search_by_vector(self, embedding: list, limit: int = 5,
                         min_score: float = 0.0) -> List[dict]:
        """Search knowledge patterns by vector similarity."""
        def _work(cursor):
            # Check if vector column exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'ai_agent'
                      AND table_name = 'learned_knowledge'
                      AND column_name = 'embedding'
                )
            """)
            if not cursor.fetchone()['exists']:
                return []

            cursor.execute("""
                SELECT id, pattern, category, source_count, confidence,
                       1 - (embedding <=> %s::vector) AS score
                FROM ai_agent.learned_knowledge
                WHERE is_active = TRUE AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (embedding, embedding, limit))
            results = []
            for row in cursor.fetchall():
                if row['score'] >= min_score:
                    results.append(dict(row))
            return results
        return self.execute_many(_work)

    def find_similar(self, embedding: list, threshold: float = 0.92) -> Optional[dict]:
        """Find a knowledge pattern similar enough to merge with (>threshold similarity)."""
        results = self.search_by_vector(embedding, limit=1, min_score=threshold)
        return results[0] if results else None

    def increment_source_count(self, knowledge_id: int) -> bool:
        """Increment source_count and boost confidence for a merged pattern."""
        return self.execute("""
            UPDATE ai_agent.learned_knowledge
            SET source_count = source_count + 1,
                confidence = LEAST(confidence + 0.1, 1.0),
                updated_at = NOW()
            WHERE id = %s
        """, (knowledge_id,)) > 0

    def get_all_active(self, limit: int = 100) -> List[dict]:
        """Get all active knowledge patterns sorted by confidence."""
        return self.query_all("""
            SELECT id, pattern, category, source_count, confidence, is_active,
                   created_at, updated_at
            FROM ai_agent.learned_knowledge
            WHERE is_active = TRUE
            ORDER BY confidence DESC, source_count DESC
            LIMIT %s
        """, (limit,))

    def get_all(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """Get all knowledge patterns (admin view)."""
        return self.query_all("""
            SELECT id, pattern, category, source_count, confidence, is_active,
                   created_at, updated_at
            FROM ai_agent.learned_knowledge
            ORDER BY confidence DESC, created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

    def toggle_active(self, knowledge_id: int) -> Optional[dict]:
        """Toggle is_active flag."""
        return self.execute("""
            UPDATE ai_agent.learned_knowledge
            SET is_active = NOT is_active, updated_at = NOW()
            WHERE id = %s
            RETURNING id, is_active
        """, (knowledge_id,), returning=True)

    def delete_pattern(self, knowledge_id: int) -> bool:
        """Hard delete a knowledge pattern."""
        return self.execute("""
            DELETE FROM ai_agent.learned_knowledge WHERE id = %s
        """, (knowledge_id,)) > 0

    def update_embedding(self, knowledge_id: int, embedding: list) -> bool:
        """Update embedding for a pattern."""
        def _work(cursor):
            try:
                cursor.execute("""
                    UPDATE ai_agent.learned_knowledge
                    SET embedding = %s::vector, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                """, (embedding, knowledge_id))
                return cursor.fetchone() is not None
            except Exception:
                # embedding column may not exist (no pgvector)
                return False
        return self.execute_many(_work)

    def decay_confidence(self, decay_rate: float = 0.05) -> int:
        """Reduce confidence for patterns not recently reinforced. Returns count updated."""
        return self.execute("""
            UPDATE ai_agent.learned_knowledge
            SET confidence = GREATEST(confidence - %s, 0.1),
                updated_at = NOW()
            WHERE is_active = TRUE
              AND updated_at < NOW() - INTERVAL '30 days'
        """, (decay_rate,))

    def get_stats(self) -> dict:
        """Get knowledge base statistics."""
        row = self.query_one("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE is_active) AS active,
                AVG(confidence) FILTER (WHERE is_active) AS avg_confidence,
                SUM(source_count) FILTER (WHERE is_active) AS total_sources
            FROM ai_agent.learned_knowledge
        """)
        if row:
            row['avg_confidence'] = float(row['avg_confidence'] or 0)
            row['total_sources'] = int(row['total_sources'] or 0)
        return row or {'total': 0, 'active': 0, 'avg_confidence': 0, 'total_sources': 0}
