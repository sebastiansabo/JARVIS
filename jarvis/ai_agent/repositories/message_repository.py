"""Message Repository — AI Agent messages."""
import json
from decimal import Decimal
from typing import Optional, List

from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger
from ..models import Message, MessageRole

logger = get_logger('jarvis.ai_agent.repo.message')


class MessageRepository(BaseRepository):
    """Repository for Message entities."""

    def create(self, message: Message) -> Message:
        """Create a new message."""
        def _work(cursor):
            cursor.execute("""
                INSERT INTO ai_agent.messages (
                    conversation_id, role, content,
                    input_tokens, output_tokens, cost,
                    rag_sources, model_config_id, response_time_ms,
                    created_at
                ) VALUES (
                    %(conversation_id)s, %(role)s, %(content)s,
                    %(input_tokens)s, %(output_tokens)s, %(cost)s,
                    %(rag_sources)s, %(model_config_id)s, %(response_time_ms)s,
                    NOW()
                )
                RETURNING id, created_at
            """, {
                'conversation_id': message.conversation_id,
                'role': message.role.value,
                'content': message.content,
                'input_tokens': message.input_tokens,
                'output_tokens': message.output_tokens,
                'cost': str(message.cost),
                'rag_sources': json.dumps(message.rag_sources) if message.rag_sources else '[]',
                'model_config_id': message.model_config_id,
                'response_time_ms': message.response_time_ms,
            })
            row = cursor.fetchone()
            message.id = row['id']
            message.created_at = row['created_at']
            return message
        return self.execute_many(_work)

    def get_by_id(self, message_id: int) -> Optional[Message]:
        """Get a message by ID."""
        row = self.query_one("""
            SELECT id, conversation_id, role, content,
                   input_tokens, output_tokens, cost,
                   rag_sources, model_config_id, response_time_ms,
                   created_at
            FROM ai_agent.messages
            WHERE id = %s
        """, (message_id,))
        return self._row_to_message(row) if row else None

    def get_by_conversation(self, conversation_id: int, limit: int = 50,
                            offset: int = 0, order: str = 'asc') -> List[Message]:
        """Get messages for a conversation."""
        order_dir = 'ASC' if order == 'asc' else 'DESC'
        rows = self.query_all(f"""
            SELECT id, conversation_id, role, content,
                   input_tokens, output_tokens, cost,
                   rag_sources, model_config_id, response_time_ms,
                   created_at
            FROM ai_agent.messages
            WHERE conversation_id = %s
            ORDER BY created_at {order_dir}
            LIMIT %s OFFSET %s
        """, (conversation_id, limit, offset))
        return [self._row_to_message(row) for row in rows]

    def get_recent_for_context(self, conversation_id: int, limit: int = 10) -> List[Message]:
        """Get recent messages for building context (chronological order)."""
        rows = self.query_all("""
            SELECT id, conversation_id, role, content,
                   input_tokens, output_tokens, cost,
                   rag_sources, model_config_id, response_time_ms,
                   created_at
            FROM ai_agent.messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (conversation_id, limit))
        messages = [self._row_to_message(row) for row in rows]
        messages.reverse()
        return messages

    def count_by_conversation(self, conversation_id: int) -> int:
        """Count messages in a conversation."""
        row = self.query_one(
            'SELECT COUNT(*) as count FROM ai_agent.messages WHERE conversation_id = %s',
            (conversation_id,))
        return row['count'] if row else 0

    def delete_by_conversation(self, conversation_id: int) -> int:
        """Delete all messages in a conversation. Returns count deleted."""
        return self.execute(
            'DELETE FROM ai_agent.messages WHERE conversation_id = %s', (conversation_id,))

    def _row_to_message(self, row: dict) -> Message:
        """Convert database row to Message model."""
        rag_sources = row.get('rag_sources')
        if isinstance(rag_sources, str):
            rag_sources = json.loads(rag_sources)
        elif rag_sources is None:
            rag_sources = []

        return Message(
            id=row['id'],
            conversation_id=row['conversation_id'],
            role=MessageRole(row['role']),
            content=row['content'],
            input_tokens=row['input_tokens'] or 0,
            output_tokens=row['output_tokens'] or 0,
            cost=Decimal(str(row['cost'])) if row['cost'] else Decimal("0"),
            rag_sources=rag_sources,
            model_config_id=row['model_config_id'],
            response_time_ms=row['response_time_ms'],
            created_at=row['created_at'],
        )
