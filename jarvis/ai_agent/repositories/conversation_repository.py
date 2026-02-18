"""Conversation Repository — AI Agent conversations."""
import json
from decimal import Decimal
from typing import Optional, List

from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger
from ..models import Conversation, ConversationStatus

logger = get_logger('jarvis.ai_agent.repo.conversation')


class ConversationRepository(BaseRepository):
    """Repository for Conversation entities."""

    def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation."""
        def _work(cursor):
            cursor.execute("""
                INSERT INTO ai_agent.conversations (
                    user_id, title, model_config_id, status,
                    total_tokens, total_cost, message_count,
                    metadata, created_at, updated_at
                ) VALUES (
                    %(user_id)s, %(title)s, %(model_config_id)s, %(status)s,
                    %(total_tokens)s, %(total_cost)s, %(message_count)s,
                    %(metadata)s, NOW(), NOW()
                )
                RETURNING id, created_at, updated_at
            """, {
                'user_id': conversation.user_id,
                'title': conversation.title or 'New Conversation',
                'model_config_id': conversation.model_config_id,
                'status': conversation.status.value,
                'total_tokens': conversation.total_tokens,
                'total_cost': str(conversation.total_cost),
                'message_count': conversation.message_count,
                'metadata': json.dumps(conversation.metadata or {}),
            })
            row = cursor.fetchone()
            conversation.id = row['id']
            conversation.created_at = row['created_at']
            conversation.updated_at = row['updated_at']
            return conversation
        return self.execute_many(_work)

    def get_by_id(self, conversation_id: int) -> Optional[Conversation]:
        """Get a conversation by ID."""
        row = self.query_one("""
            SELECT id, user_id, title, model_config_id, status,
                   total_tokens, total_cost, message_count,
                   metadata, created_at, updated_at, archived_at
            FROM ai_agent.conversations
            WHERE id = %s
        """, (conversation_id,))
        return self._row_to_conversation(row) if row else None

    def list_by_user(self, user_id: int, status: Optional[ConversationStatus] = None,
                     limit: int = 20, offset: int = 0) -> List[Conversation]:
        """List conversations for a user."""
        query = """
            SELECT id, user_id, title, model_config_id, status,
                   total_tokens, total_cost, message_count,
                   metadata, created_at, updated_at, archived_at
            FROM ai_agent.conversations
            WHERE user_id = %s
        """
        params = [user_id]
        if status:
            query += " AND status = %s"
            params.append(status.value)
        query += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return [self._row_to_conversation(row) for row in self.query_all(query, params)]

    def update_status(self, conversation_id: int, status: ConversationStatus) -> bool:
        """Update conversation status."""
        return self.execute("""
            UPDATE ai_agent.conversations
            SET status = %s,
                updated_at = NOW(),
                archived_at = CASE WHEN %s = 'archived' THEN NOW() ELSE archived_at END
            WHERE id = %s
        """, (status.value, status.value, conversation_id)) > 0

    def update_stats(self, conversation_id: int, tokens: int = 0,
                     cost: Decimal = Decimal("0"), messages: int = 1) -> bool:
        """Update conversation statistics after a message."""
        return self.execute("""
            UPDATE ai_agent.conversations
            SET total_tokens = total_tokens + %s,
                total_cost = total_cost + %s,
                message_count = message_count + %s,
                updated_at = NOW()
            WHERE id = %s
        """, (tokens, str(cost), messages, conversation_id)) > 0

    def update_title(self, conversation_id: int, title: str) -> bool:
        """Update conversation title."""
        return self.execute("""
            UPDATE ai_agent.conversations
            SET title = %s, updated_at = NOW()
            WHERE id = %s
        """, (title, conversation_id)) > 0

    def delete(self, conversation_id: int) -> bool:
        """Permanently delete a conversation and its messages."""
        return self.execute(
            'DELETE FROM ai_agent.conversations WHERE id = %s', (conversation_id,)
        ) > 0

    def _row_to_conversation(self, row: dict) -> Conversation:
        """Convert database row to Conversation model."""
        return Conversation(
            id=row['id'],
            user_id=row['user_id'],
            title=row['title'],
            model_config_id=row['model_config_id'],
            status=ConversationStatus(row['status']),
            total_tokens=row['total_tokens'] or 0,
            total_cost=Decimal(str(row['total_cost'])) if row['total_cost'] else Decimal("0"),
            message_count=row['message_count'] or 0,
            metadata=row['metadata'] or {},
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            archived_at=row['archived_at'],
        )
