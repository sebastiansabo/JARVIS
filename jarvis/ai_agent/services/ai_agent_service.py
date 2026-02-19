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
from .analytics_service import AnalyticsService
from .query_parser import parse_query, classify_complexity

logger = get_logger('jarvis.ai_agent.service')


def estimate_tokens(text: str) -> int:
    """Approximate token count from text length.

    Uses ~4 chars per token heuristic (accurate within ~10-15% for English).
    Slightly conservative to avoid context window overflows.
    """
    return max(1, len(text) // 3)


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

        # Initialize analytics service
        self.analytics_service = AnalyticsService()

        # Initialize providers
        self._providers: Dict[str, BaseProvider] = {
            'claude': ClaudeProvider(),
            'openai': OpenAIProvider(),
            'groq': GroqProvider(),
            'gemini': GeminiProvider(),
        }

        self._settings_cache: Optional[Dict[str, str]] = None
        self._settings_cache_time: float = 0

        logger.info("AIAgentService initialized with RAG support and multi-provider")

    def _load_runtime_settings(self) -> None:
        """Load AI settings from DB and apply to config. Cached for 60s."""
        now = time.time()
        if self._settings_cache and (now - self._settings_cache_time) < 60:
            return

        try:
            from core.notifications.repositories.notification_repository import NotificationRepository
            repo = NotificationRepository()
            all_settings = repo.get_settings()

            if all_settings.get('ai_rag_enabled') is not None:
                self.config.RAG_ENABLED = all_settings['ai_rag_enabled'] != 'false'
            if all_settings.get('ai_analytics_enabled') is not None:
                self.config.ANALYTICS_ENABLED = all_settings['ai_analytics_enabled'] != 'false'
            if all_settings.get('ai_rag_top_k') is not None:
                self.config.RAG_TOP_K = int(all_settings['ai_rag_top_k'])
            if all_settings.get('ai_temperature') is not None:
                self.config.DEFAULT_TEMPERATURE = float(all_settings['ai_temperature'])
            if all_settings.get('ai_max_tokens') is not None:
                self.config.DEFAULT_MAX_TOKENS = int(all_settings['ai_max_tokens'])

            self._settings_cache = all_settings
            self._settings_cache_time = now
        except Exception as e:
            logger.warning(f"Failed to load runtime AI settings: {e}")

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

    def _select_model(self, user_message: str, default_config: ModelConfig) -> ModelConfig:
        """Select optimal model based on query complexity.

        Routes simple queries (greetings, short lookups) to the cheapest
        active model to reduce cost. Complex or analytics queries stay
        on the default (most capable) model.

        Args:
            user_message: The user's message text
            default_config: The conversation's default model config

        Returns:
            ModelConfig to use for this request
        """
        complexity = classify_complexity(user_message)

        if complexity != 'simple':
            return default_config

        # Find cheapest active model (by input cost)
        try:
            all_models = self.model_config_repo.get_all_active()
            if len(all_models) <= 1:
                return default_config

            cheapest = min(all_models, key=lambda m: m.cost_per_1k_input)

            # Only route if it's actually cheaper
            if cheapest.cost_per_1k_input < default_config.cost_per_1k_input:
                logger.debug(
                    f"Model routing: '{complexity}' query → {cheapest.display_name or cheapest.model_name} "
                    f"(was {default_config.display_name or default_config.model_name})"
                )
                return cheapest
        except Exception as e:
            logger.warning(f"Model routing failed, using default: {e}")

        return default_config

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

        # Load runtime settings from DB
        self._load_runtime_settings()

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

            # 2b. Route to optimal model based on complexity
            model_config = self._select_model(user_message, model_config)

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

            # 4b. Analytics context
            analytics_context = self._get_analytics_context(user_message)

            # 5. Build system prompt first (needed for token budgeting)
            system_prompt = self._build_system_prompt(
                rag_context=rag_context,
                analytics_context=analytics_context,
            )
            system_prompt_tokens = estimate_tokens(system_prompt)

            # 6. Build context messages (token-aware)
            context_messages = self._build_context_messages(
                conversation_id=conversation_id,
                current_message=user_message,
                model_config=model_config,
                system_prompt_tokens=system_prompt_tokens,
            )

            # 7. Get provider and generate response
            provider = self.get_provider(model_config.provider.value)

            llm_response = provider.generate(
                model_name=model_config.model_name,
                messages=context_messages,
                max_tokens=model_config.max_tokens,
                temperature=float(model_config.default_temperature),
                system=system_prompt,
            )

            # 8. Calculate cost
            cost = self._calculate_cost(
                model_config=model_config,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
            )

            # 9. Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)

            # 10. Format RAG sources for storage
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

    def chat_stream(
        self,
        conversation_id: int,
        user_id: int,
        user_message: str,
        model_config_id: Optional[int] = None,
    ):
        """
        Stream a chat response via SSE events.

        Yields SSE-formatted strings: token events during streaming,
        then a done event with metadata after completion.
        """
        import json
        start_time = time.time()

        # Load runtime settings from DB
        self._load_runtime_settings()

        try:
            # Steps 1-5: same as chat()
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
                return

            if conversation.user_id != user_id:
                yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
                return

            config_id = model_config_id or conversation.model_config_id
            model_config = None
            if config_id:
                model_config = self.model_config_repo.get_by_id(config_id)
            if not model_config:
                model_config = self.model_config_repo.get_default()
            if not model_config:
                yield f"event: error\ndata: {json.dumps({'error': 'No model configuration available'})}\n\n"
                return

            # Route to optimal model based on complexity
            model_config = self._select_model(user_message, model_config)

            # Save user message
            user_msg = Message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=user_message,
                model_config_id=model_config.id,
            )
            self.message_repo.create(user_msg)

            # RAG context
            rag_sources = []
            rag_context = None
            if self.config.RAG_ENABLED:
                try:
                    rag_sources = self.rag_service.search(
                        query=user_message,
                        limit=self.config.RAG_TOP_K,
                        company_id=None,
                    )
                    if rag_sources:
                        rag_context = self.rag_service.format_context(
                            rag_sources,
                            max_tokens=self.config.MAX_CONTEXT_TOKENS // 2,
                        )
                except Exception as e:
                    logger.warning(f"RAG retrieval failed: {e}")

            # Analytics context
            analytics_context = self._get_analytics_context(user_message)

            # Build system prompt first (needed for token budgeting)
            system_prompt = self._build_system_prompt(
                rag_context=rag_context,
                analytics_context=analytics_context,
            )
            system_prompt_tokens = estimate_tokens(system_prompt)

            # Build context messages (token-aware)
            context_messages = self._build_context_messages(
                conversation_id=conversation_id,
                current_message=user_message,
                model_config=model_config,
                system_prompt_tokens=system_prompt_tokens,
            )

            provider = self.get_provider(model_config.provider.value)

            # Stream tokens
            llm_response = None
            for text_chunk, final_response in provider.generate_stream(
                model_name=model_config.model_name,
                messages=context_messages,
                max_tokens=model_config.max_tokens,
                temperature=float(model_config.default_temperature),
                system=system_prompt,
            ):
                if text_chunk is not None:
                    yield f"event: token\ndata: {json.dumps({'content': text_chunk})}\n\n"
                if final_response is not None:
                    llm_response = final_response

            if not llm_response:
                yield f"event: error\ndata: {json.dumps({'error': 'No response from LLM'})}\n\n"
                return

            # Post-stream: save message, update stats
            cost = self._calculate_cost(
                model_config=model_config,
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
            )
            response_time_ms = int((time.time() - start_time) * 1000)

            rag_sources_data = [
                {
                    'doc_id': src.doc_id,
                    'score': src.score,
                    'snippet': src.snippet[:200],
                    'source_type': src.source_type,
                    'source_id': src.source_id,
                }
                for src in rag_sources
            ]

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
            saved_msg = self.message_repo.create(assistant_msg)

            total_tokens = llm_response.input_tokens + llm_response.output_tokens
            self.conversation_repo.update_stats(
                conversation_id=conversation_id,
                tokens=total_tokens,
                cost=cost,
                messages=2,
            )

            if conversation.message_count == 0:
                self._auto_title_conversation(conversation_id, user_message)

            # Final done event
            yield f"event: done\ndata: {json.dumps({'message_id': saved_msg.id, 'tokens_used': total_tokens, 'cost': str(cost), 'response_time_ms': response_time_ms, 'rag_sources': [{'doc_id': s.doc_id, 'score': s.score, 'snippet': s.snippet, 'source_type': s.source_type} for s in rag_sources]})}\n\n"

            logger.info(
                f"Chat stream completed: conv={conversation_id}, "
                f"tokens={total_tokens}, cost={cost}, time={response_time_ms}ms"
            )

        except LLMProviderError as e:
            logger.error(f"LLM provider error during stream: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            logger.error(f"Chat stream failed: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

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
        model_config: Optional[ModelConfig] = None,
        system_prompt_tokens: int = 0,
    ) -> List[Dict[str, str]]:
        """
        Build message context for LLM call with token-aware trimming.

        Fills the context window from newest to oldest messages, stopping
        when the token budget is exhausted.  Always includes the current
        user message.

        Args:
            conversation_id: Conversation ID
            current_message: Current user message
            model_config: Model config (for context_window budget)
            system_prompt_tokens: Estimated tokens used by system prompt + RAG

        Returns:
            List of message dicts for LLM
        """
        # Calculate token budget
        context_window = model_config.context_window if model_config else 200000
        reserved_output = model_config.max_tokens if model_config else self.config.DEFAULT_MAX_TOKENS
        available = context_window - reserved_output - system_prompt_tokens

        # Reserve tokens for current message
        current_tokens = estimate_tokens(current_message)
        available -= current_tokens

        # Safety margin (10%) to account for estimation error
        available = int(available * 0.9)

        # Get recent messages (newest first from DB, reversed to chronological)
        recent_messages = self.message_repo.get_recent_for_context(
            conversation_id=conversation_id,
            limit=self.config.MAX_CONTEXT_MESSAGES,
        )

        # Add messages from most recent backward, respecting budget
        selected = []
        used_tokens = 0
        for msg in reversed(recent_messages):
            msg_tokens = estimate_tokens(msg.content)
            if used_tokens + msg_tokens > available:
                logger.debug(
                    f"Context trimmed: {len(recent_messages) - len(selected)} messages dropped "
                    f"({used_tokens}/{available} tokens used)"
                )
                break
            selected.append(msg)
            used_tokens += msg_tokens

        selected.reverse()

        # Convert to LLM format
        context = [{'role': msg.role.value, 'content': msg.content} for msg in selected]
        context.append({'role': 'user', 'content': current_message})

        logger.debug(
            f"Context: {len(selected)} history + 1 current, "
            f"~{used_tokens + current_tokens} tokens "
            f"(budget: {context_window} - {reserved_output} output - {system_prompt_tokens} system)"
        )

        return context

    def _get_analytics_context(self, user_message: str) -> Optional[str]:
        """Run analytics queries if the user message has analytical intent."""
        if not self.config.ANALYTICS_ENABLED:
            return None

        try:
            known_entities = self.analytics_service.get_entity_names()
            parsed = parse_query(user_message, known_entities)

            if not parsed.is_analytics:
                return None

            results = []
            filters = parsed.filters

            for query_type in parsed.query_types:
                if query_type == 'monthly_trend':
                    results.append(self.analytics_service.get_monthly_trend(
                        company=filters.get('company'),
                        department=filters.get('department'),
                        brand=filters.get('brand'),
                        supplier=filters.get('supplier'),
                        start_date=filters.get('start_date'),
                        end_date=filters.get('end_date'),
                    ))
                elif query_type == 'top_suppliers':
                    results.append(self.analytics_service.get_top_suppliers(
                        limit=parsed.top_n or 10,
                        company=filters.get('company'),
                        department=filters.get('department'),
                        brand=filters.get('brand'),
                        start_date=filters.get('start_date'),
                        end_date=filters.get('end_date'),
                    ))
                elif query_type == 'transaction_summary':
                    results.append(self.analytics_service.get_transaction_summary(
                        company_cui=filters.get('company_cui'),
                        supplier=filters.get('supplier'),
                        date_from=filters.get('start_date'),
                        date_to=filters.get('end_date'),
                    ))
                elif query_type == 'efactura_summary':
                    results.append(self.analytics_service.get_efactura_summary())
                elif query_type == 'invoice_summary':
                    results.append(self.analytics_service.get_invoice_summary(
                        group_by=parsed.group_by or 'company',
                        company=filters.get('company'),
                        department=filters.get('department'),
                        brand=filters.get('brand'),
                        supplier=filters.get('supplier'),
                        start_date=filters.get('start_date'),
                        end_date=filters.get('end_date'),
                    ))

            context = self.analytics_service.format_as_context(results)
            if context:
                logger.debug(f"Analytics context: {len(parsed.query_types)} queries, {len(context)} chars")
            return context or None

        except Exception as e:
            logger.warning(f"Analytics context failed: {e}")
            return None

    def _build_system_prompt(
        self,
        rag_context: Optional[str] = None,
        analytics_context: Optional[str] = None,
    ) -> str:
        """
        Build system prompt for LLM.

        Args:
            rag_context: Optional RAG context to include
            analytics_context: Optional analytics data to include

        Returns:
            Complete system prompt
        """
        base_prompt = """You are JARVIS, an intelligent assistant for the JARVIS enterprise platform.

You help users with questions about:
- Invoices, transactions, and bank statements
- Companies, departments, and employees
- e-Factura (ANAF electronic invoices)
- HR events and bonuses
- Marketing projects (budgets, KPIs, teams, status)
- Approval workflows (requests, decisions, delegations)
- Tags and entity categorization

Guidelines:
- Be helpful, accurate, and concise
- If you don't have specific data, say so clearly
- When referencing data from context, cite the source
- Format currency values as "1.234,56 RON" or "1.234,56 EUR" (Romanian convention)
- Use DD.MM.YYYY date format when displaying dates
- When presenting financial data, use markdown tables with totals
- For trends, describe the direction (increasing, decreasing, or stable)"""

        sections = [base_prompt]

        if analytics_context:
            sections.append(f"""ANALYTICS DATA (live aggregations from JARVIS database):
{analytics_context}

Present this data clearly using markdown tables. Include totals where appropriate.""")

        if rag_context:
            sections.append(f"""CONTEXT FROM JARVIS DATABASE:
{rag_context}""")

        if not analytics_context and not rag_context:
            sections.append("Note: No specific context was retrieved for this query. For detailed data questions, try asking about specific invoices, suppliers, or dates.")

        return '\n\n'.join(sections)

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
