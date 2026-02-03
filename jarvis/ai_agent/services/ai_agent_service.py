"""
AI Agent Service

Main orchestration service for AI Agent conversations.
Handles chat requests, context management, and provider coordination.
"""

import time
from decimal import Decimal
from typing import Optional, List, Dict, Any

from core.utils.logging_config import get_logger
from ..models import (
    Conversation, Message, MessageRole, ConversationStatus,
    ModelConfig, LLMProvider, ChatResponse, ServiceResult,
    RAGSource,
)
from ..config import AIAgentConfig
from ..exceptions import (
    AIAgentError, ConversationNotFoundError, LLMProviderError,
    ConfigurationError,
)
from ..repositories import (
    ConversationRepository, MessageRepository, ModelConfigRepository
)
from ..providers import BaseProvider, ClaudeProvider, OpenAIProvider, GroqProvider, GeminiProvider
from .rag_service import RAGService

logger = get_logger('jarvis.ai_agent.service')


class AIAgentService:
    """
    Main AI Agent service for handling conversations.

    Orchestrates:
    - Conversation lifecycle management
    - Message history and context
    - LLM provider selection and calls
    - RAG retrieval for context
    - Cost tracking
    """

    def __init__(self, config: Optional[AIAgentConfig] = None):
        """
        Initialize AI Agent service.

        Args:
            config: Optional AIAgentConfig, uses defaults if not provided
        """
        self.config = config or AIAgentConfig()

        # Initialize repositories
        self.conversation_repo = ConversationRepository()
        self.message_repo = MessageRepository()
        self.model_config_repo = ModelConfigRepository()

        # Initialize RAG service
        self.rag_service = RAGService(config)

        # Initialize providers
        self._providers: Dict[str, BaseProvider] = {
            'claude': ClaudeProvider(),
            'openai': OpenAIProvider(),
            'groq': GroqProvider(),
            'gemini': GeminiProvider(),
        }

        logger.info("AIAgentService initialized with RAG support and multi-provider")

    def get_provider(self, provider_name: str) -> BaseProvider:
        """
        Get LLM provider by name.

        Args:
            provider_name: Provider identifier (claude, openai, etc.)

        Returns:
            BaseProvider instance

        Raises:
            ConfigurationError: If provider not found
        """
        provider = self._providers.get(provider_name)
        if not provider:
            raise ConfigurationError(f"Provider '{provider_name}' not available")
        return provider

    def create_conversation(
        self,
        user_id: int,
        title: Optional[str] = None,
        model_config_id: Optional[int] = None,
    ) -> ServiceResult:
        """
        Create a new conversation.

        Args:
            user_id: User creating the conversation
            title: Optional conversation title
            model_config_id: Optional model configuration ID

        Returns:
            ServiceResult with Conversation on success
        """
        try:
            # Get default model config if not specified
            if model_config_id is None:
                default_config = self.model_config_repo.get_default()
                if default_config:
                    model_config_id = default_config.id

            conversation = Conversation(
                user_id=user_id,
                title=title or "New Conversation",
                model_config_id=model_config_id,
                status=ConversationStatus.ACTIVE,
            )

            created = self.conversation_repo.create(conversation)
            logger.info(f"Created conversation {created.id} for user {user_id}")

            return ServiceResult(success=True, data=created)

        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_conversation(
        self,
        conversation_id: int,
        user_id: int,
    ) -> ServiceResult:
        """
        Get a conversation with messages.

        Args:
            conversation_id: Conversation ID
            user_id: User ID (for access control)

        Returns:
            ServiceResult with conversation dict including messages
        """
        try:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                raise ConversationNotFoundError(conversation_id)

            # Access control
            if conversation.user_id != user_id:
                raise ConversationNotFoundError(conversation_id)

            # Get messages
            messages = self.message_repo.get_by_conversation(conversation_id)

            return ServiceResult(
                success=True,
                data={
                    'conversation': conversation,
                    'messages': messages,
                }
            )

        except ConversationNotFoundError:
            return ServiceResult(success=False, error="Conversation not found")
        except Exception as e:
            logger.error(f"Failed to get conversation {conversation_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def list_conversations(
        self,
        user_id: int,
        status: Optional[ConversationStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ServiceResult:
        """
        List conversations for a user.

        Args:
            user_id: User ID
            status: Optional status filter
            limit: Max results
            offset: Pagination offset

        Returns:
            ServiceResult with list of conversations
        """
        try:
            conversations = self.conversation_repo.list_by_user(
                user_id=user_id,
                status=status,
                limit=limit,
                offset=offset,
            )

            return ServiceResult(success=True, data=conversations)

        except Exception as e:
            logger.error(f"Failed to list conversations for user {user_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def chat(
        self,
        conversation_id: int,
        user_id: int,
        user_message: str,
        model_config_id: Optional[int] = None,
    ) -> ServiceResult:
        """
        Send a message and get AI response.

        This is the main chat method that:
        1. Validates conversation access
        2. Saves user message
        3. Builds context from history
        4. Calls LLM provider
        5. Saves assistant response
        6. Updates conversation stats

        Args:
            conversation_id: Conversation ID
            user_id: User ID (for access control)
            user_message: User's message text
            model_config_id: Optional model override

        Returns:
            ServiceResult with ChatResponse
        """
        start_time = time.time()

        try:
            # 1. Get and validate conversation
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                raise ConversationNotFoundError(conversation_id)

            if conversation.user_id != user_id:
                raise ConversationNotFoundError(conversation_id)

            # 2. Get model configuration
            config_id = model_config_id or conversation.model_config_id
            model_config = None
            if config_id:
                model_config = self.model_config_repo.get_by_id(config_id)

            if not model_config:
                model_config = self.model_config_repo.get_default()

            if not model_config:
                raise ConfigurationError("No model configuration available")

            # 3. Save user message
            user_msg = Message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=user_message,
                model_config_id=model_config.id,
            )
            saved_user_msg = self.message_repo.create(user_msg)

            # 4. Retrieve RAG context if enabled
            rag_sources = []
            rag_context = None
            if self.config.RAG_ENABLED:
                try:
                    rag_sources = self.rag_service.search(
                        query=user_message,
                        limit=self.config.RAG_TOP_K,
                        company_id=None,  # TODO: Get user's company for filtering
                    )
                    if rag_sources:
                        rag_context = self.rag_service.format_context(
                            rag_sources,
                            max_tokens=self.config.MAX_CONTEXT_TOKENS // 2,
                        )
                        logger.debug(f"RAG found {len(rag_sources)} sources")
                except Exception as e:
                    logger.warning(f"RAG retrieval failed: {e}")

            # 5. Build context messages
            context_messages = self._build_context_messages(
                conversation_id=conversation_id,
                current_message=user_message,
            )

            # 6. Get provider and generate response
            provider = self.get_provider(model_config.provider.value)

            # Build system prompt with RAG context
            system_prompt = self._build_system_prompt(rag_context=rag_context)

            llm_response = provider.generate(
                model_name=model_config.model_name,
                messages=context_messages,
                max_tokens=model_config.max_tokens,
                temperature=float(model_config.default_temperature),
                system=system_prompt,
            )

            # 7. Calculate cost
            cost = self._calculate_cost(
                model_config=model_config,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
            )

            # 8. Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)

            # 9. Format RAG sources for storage
            rag_sources_data = [
                {
                    'doc_id': src.doc_id,
                    'score': src.score,
                    'snippet': src.snippet[:200],  # Truncate for storage
                    'source_type': src.source_type,
                    'source_id': src.source_id,
                }
                for src in rag_sources
            ]

            # 10. Save assistant message
            assistant_msg = Message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=llm_response.content,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                cost=cost,
                model_config_id=model_config.id,
                response_time_ms=response_time_ms,
                rag_sources=rag_sources_data,
            )
            saved_assistant_msg = self.message_repo.create(assistant_msg)

            # 11. Update conversation stats
            total_tokens = llm_response.input_tokens + llm_response.output_tokens
            self.conversation_repo.update_stats(
                conversation_id=conversation_id,
                tokens=total_tokens,
                cost=cost,
                messages=2,  # User + assistant messages
            )

            # 12. Auto-generate title if first message
            if conversation.message_count == 0:
                self._auto_title_conversation(conversation_id, user_message)

            logger.info(
                f"Chat completed: conv={conversation_id}, "
                f"tokens={total_tokens}, cost={cost}, time={response_time_ms}ms, "
                f"rag_sources={len(rag_sources)}"
            )

            # 13. Build response
            chat_response = ChatResponse(
                message=saved_assistant_msg,
                rag_sources=rag_sources,
                tokens_used=total_tokens,
                cost=cost,
                response_time_ms=response_time_ms,
            )

            return ServiceResult(success=True, data=chat_response)

        except ConversationNotFoundError:
            return ServiceResult(success=False, error="Conversation not found")
        except LLMProviderError as e:
            logger.error(f"LLM provider error: {e}")
            return ServiceResult(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Chat failed: {e}", exc_info=True)
            return ServiceResult(success=False, error=str(e))

    def archive_conversation(
        self,
        conversation_id: int,
        user_id: int,
    ) -> ServiceResult:
        """
        Archive a conversation.

        Args:
            conversation_id: Conversation to archive
            user_id: User ID (for access control)

        Returns:
            ServiceResult with success status
        """
        try:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                raise ConversationNotFoundError(conversation_id)

            if conversation.user_id != user_id:
                raise ConversationNotFoundError(conversation_id)

            self.conversation_repo.update_status(
                conversation_id=conversation_id,
                status=ConversationStatus.ARCHIVED,
            )

            logger.info(f"Archived conversation {conversation_id}")
            return ServiceResult(success=True)

        except ConversationNotFoundError:
            return ServiceResult(success=False, error="Conversation not found")
        except Exception as e:
            logger.error(f"Failed to archive conversation {conversation_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def delete_conversation(
        self,
        conversation_id: int,
        user_id: int,
    ) -> ServiceResult:
        """
        Delete a conversation (soft delete).

        Args:
            conversation_id: Conversation to delete
            user_id: User ID (for access control)

        Returns:
            ServiceResult with success status
        """
        try:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                raise ConversationNotFoundError(conversation_id)

            if conversation.user_id != user_id:
                raise ConversationNotFoundError(conversation_id)

            self.conversation_repo.delete(conversation_id)

            logger.info(f"Deleted conversation {conversation_id}")
            return ServiceResult(success=True)

        except ConversationNotFoundError:
            return ServiceResult(success=False, error="Conversation not found")
        except Exception as e:
            logger.error(f"Failed to delete conversation {conversation_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_available_models(self) -> ServiceResult:
        """
        Get all available LLM models.

        Returns:
            ServiceResult with list of ModelConfig
        """
        try:
            models = self.model_config_repo.get_all_active()
            return ServiceResult(success=True, data=models)
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            return ServiceResult(success=False, error=str(e))

    def _build_context_messages(
        self,
        conversation_id: int,
        current_message: str,
    ) -> List[Dict[str, str]]:
        """
        Build message context for LLM call.

        Includes recent conversation history up to token limit.

        Args:
            conversation_id: Conversation ID
            current_message: Current user message

        Returns:
            List of message dicts for LLM
        """
        # Get recent messages for context
        recent_messages = self.message_repo.get_recent_for_context(
            conversation_id=conversation_id,
            limit=self.config.MAX_CONTEXT_MESSAGES,
        )

        # Convert to LLM format
        context = []
        for msg in recent_messages:
            context.append({
                'role': msg.role.value,
                'content': msg.content,
            })

        # Add current message
        context.append({
            'role': 'user',
            'content': current_message,
        })

        return context

    def _build_system_prompt(
        self,
        rag_context: Optional[str] = None,
    ) -> str:
        """
        Build system prompt for LLM.

        Args:
            rag_context: Optional RAG context to include

        Returns:
            Complete system prompt
        """
        base_prompt = """You are JARVIS, an intelligent assistant for the JARVIS enterprise platform.

You help users with questions about invoices, transactions, company data, and general business operations.

Guidelines:
- Be helpful, accurate, and concise
- If you don't have specific data, say so clearly
- When referencing data from context, cite the source
- Use Romanian language conventions for dates and numbers when appropriate
- Format currency values with appropriate symbols (RON, EUR, USD)"""

        if rag_context:
            return f"""{base_prompt}

CONTEXT FROM JARVIS DATABASE:
{rag_context}

Use the above context to answer questions. If the context doesn't contain relevant information, say so and provide general guidance."""

        return f"""{base_prompt}

Note: No specific context was retrieved for this query. For detailed data questions, try asking about specific invoices, suppliers, or dates."""

    def _calculate_cost(
        self,
        model_config: ModelConfig,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """
        Calculate cost for a request.

        Args:
            model_config: Model configuration with pricing
            input_tokens: Input token count
            output_tokens: Output token count

        Returns:
            Total cost as Decimal
        """
        input_cost = (Decimal(input_tokens) / 1000) * model_config.cost_per_1k_input
        output_cost = (Decimal(output_tokens) / 1000) * model_config.cost_per_1k_output
        return input_cost + output_cost

    def _auto_title_conversation(
        self,
        conversation_id: int,
        first_message: str,
    ) -> None:
        """
        Auto-generate conversation title from first message.

        Args:
            conversation_id: Conversation to title
            first_message: First user message
        """
        try:
            # Simple title extraction: first ~50 chars or first sentence
            title = first_message.strip()

            # Truncate at first sentence boundary
            for sep in ['.', '?', '!', '\n']:
                if sep in title:
                    title = title[:title.index(sep)]
                    break

            # Truncate to max length
            if len(title) > 50:
                title = title[:47] + "..."

            if title:
                self.conversation_repo.update_title(conversation_id, title)
                logger.debug(f"Auto-titled conversation {conversation_id}: {title}")

        except Exception as e:
            # Non-critical, just log
            logger.warning(f"Failed to auto-title conversation: {e}")
