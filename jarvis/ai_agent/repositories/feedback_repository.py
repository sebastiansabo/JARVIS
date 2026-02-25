"""Feedback Repository — thumbs up/down on AI messages."""

from typing import Optional, Dict, List
from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger

logger = get_logger('jarvis.ai_agent.repo.feedback')


class FeedbackRepository(BaseRepository):
    """Repository for message feedback (positive/negative)."""

    def upsert(self, message_id: int, user_id: int, feedback_type: str) -> dict:
        """Create or update feedback. Returns the feedback row."""
        return self.execute("""
            INSERT INTO ai_agent.message_feedback (message_id, user_id, feedback_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (message_id, user_id)
            DO UPDATE SET feedback_type = EXCLUDED.feedback_type, created_at = NOW()
            RETURNING id, message_id, user_id, feedback_type, created_at
        """, (message_id, user_id, feedback_type), returning=True)

    def delete(self, message_id: int, user_id: int) -> bool:
        """Remove feedback for a message."""
        return self.execute("""
            DELETE FROM ai_agent.message_feedback
            WHERE message_id = %s AND user_id = %s
        """, (message_id, user_id)) > 0

    def get_by_message(self, message_id: int, user_id: int) -> Optional[dict]:
        """Get user's feedback for a specific message."""
        return self.query_one("""
            SELECT id, message_id, user_id, feedback_type, created_at
            FROM ai_agent.message_feedback
            WHERE message_id = %s AND user_id = %s
        """, (message_id, user_id))

    def get_unprocessed_positive(self, last_id: int, limit: int = 50) -> List[dict]:
        """Get positive-feedback messages not yet processed for knowledge extraction.

        Joins with messages to get the assistant response content and any tool usage metadata.
        """
        return self.query_all("""
            SELECT f.id AS feedback_id, f.message_id,
                   m.content AS assistant_content,
                   m.rag_sources,
                   prev.content AS user_query
            FROM ai_agent.message_feedback f
            JOIN ai_agent.messages m ON m.id = f.message_id
            LEFT JOIN LATERAL (
                SELECT content FROM ai_agent.messages m2
                WHERE m2.conversation_id = m.conversation_id
                  AND m2.id < m.id AND m2.role = 'user'
                ORDER BY m2.id DESC LIMIT 1
            ) prev ON true
            WHERE f.feedback_type = 'positive'
              AND f.id > %s
            ORDER BY f.id
            LIMIT %s
        """, (last_id, limit))

    def get_stats(self) -> Dict[str, int]:
        """Get feedback statistics."""
        row = self.query_one("""
            SELECT
                COUNT(*) FILTER (WHERE feedback_type = 'positive') AS positive,
                COUNT(*) FILTER (WHERE feedback_type = 'negative') AS negative,
                COUNT(*) AS total
            FROM ai_agent.message_feedback
        """)
        return row or {'positive': 0, 'negative': 0, 'total': 0}
