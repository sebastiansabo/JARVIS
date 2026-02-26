"""
AI Agent Service

Main orchestration service for AI Agent conversations.
Handles chat requests, context management, and provider coordination.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Optional, List, Dict, Any

from core.utils.logging_config import get_logger
from ..models import (
    Conversation, Message, MessageRole, ConversationStatus,
    ModelConfig, LLMProvider, ChatResponse, ServiceResult,
    RAGSource, RAGSourceType,
)
from ..config import AIAgentConfig
from ..exceptions import (
    AIAgentError, ConversationNotFoundError, LLMProviderError,
    ConfigurationError,
)
from ..repositories import (
    ConversationRepository, MessageRepository, ModelConfigRepository
)
from ..providers import BaseProvider, ClaudeProvider, OpenAIProvider, GroqProvider, GeminiProvider, GrokProvider
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
            'grok': GrokProvider(),
        }

        self._settings_cache: Optional[Dict[str, str]] = None
        self._settings_cache_time: float = 0

        self._rag_source_perms_cache: Dict[int, List[RAGSourceType]] = {}
        self._rag_source_perms_cache_time: Dict[int, float] = {}

        # Model config cache (rarely changes)
        self._active_models_cache: Optional[List[ModelConfig]] = None
        self._active_models_cache_time: float = 0

        # Thread pool for parallel RAG + analytics
        self._executor = ThreadPoolExecutor(max_workers=3)

        logger.info("AIAgentService initialized with RAG support and multi-provider")

    def _load_runtime_settings(self) -> None:
        """Load AI settings from DB and apply to config. Cached for 300s."""
        now = time.time()
        if self._settings_cache and (now - self._settings_cache_time) < 300:
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

    def get_allowed_rag_sources(self, user_id: int) -> Optional[List[RAGSourceType]]:
        """Get RAG source types allowed for a user based on role permissions.

        Returns None if all sources are allowed (optimization to skip filtering).
        Cached per user_id for 600 seconds (permissions rarely change mid-session).
        """
        now = time.time()
        cached_time = self._rag_source_perms_cache_time.get(user_id, 0)
        if user_id in self._rag_source_perms_cache and (now - cached_time) < 600:
            return self._rag_source_perms_cache[user_id]

        try:
            from database import get_db, release_db

            conn = get_db()
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT role_id FROM users WHERE id = %s', (user_id,))
                row = cursor.fetchone()
                if not row or not row.get('role_id'):
                    return None  # No role = allow all (backward compat)

                role_id = row['role_id']

                # Single batch query instead of looping 10 times
                cursor.execute('''
                    SELECT p.action_key
                    FROM role_permissions_v2 rp
                    JOIN permissions_v2 p ON p.id = rp.permission_id
                    WHERE rp.role_id = %s
                      AND p.module_key = 'ai_agent'
                      AND p.entity_key = 'rag_source'
                      AND rp.scope != 'deny'
                ''', (role_id,))
                granted_actions = {r['action_key'] for r in cursor.fetchall()}

                all_sources = list(RAGSourceType)
                allowed = [src for src in all_sources if src.value in granted_actions]

                # If all sources allowed, return None (no filtering needed)
                if len(allowed) == len(all_sources):
                    result_val = None
                else:
                    result_val = allowed if allowed else []

                self._rag_source_perms_cache[user_id] = result_val
                self._rag_source_perms_cache_time[user_id] = now
                return result_val
            finally:
                release_db(conn)
        except Exception as e:
            logger.warning(f"Failed to check RAG source permissions for user {user_id}: {e}")
            return None  # Fail open — allow all on error

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

    def _get_active_models(self) -> List[ModelConfig]:
        """Get all active model configs, cached for 300s."""
        now = time.time()
        if self._active_models_cache and (now - self._active_models_cache_time) < 300:
            return self._active_models_cache
        try:
            models = self.model_config_repo.get_all_active()
            self._active_models_cache = models
            self._active_models_cache_time = now
            return models
        except Exception:
            return self._active_models_cache or []

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
            all_models = self._get_active_models()
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
            saved_user_msg = self.message_repo.create(user_msg)  # noqa: F841

            # 4. Retrieve RAG + analytics + knowledge context (parallel, skip for simple queries)
            rag_sources = []
            rag_context = None
            analytics_context = None
            learned_patterns = []
            complexity = classify_complexity(user_message)

            if complexity != 'simple':
                # Run RAG, analytics, and knowledge retrieval in PARALLEL
                rag_future = None
                analytics_future = None
                knowledge_future = self._executor.submit(
                    self._get_learned_patterns, user_message
                )

                if self.config.RAG_ENABLED:
                    def _do_rag():
                        allowed = self.get_allowed_rag_sources(user_id)
                        sources = self.rag_service.search(
                            query=user_message,
                            limit=self.config.RAG_TOP_K,
                            company_id=None,
                            source_types=allowed,
                        )
                        ctx = None
                        if sources:
                            ctx = self.rag_service.format_context(
                                sources,
                                max_tokens=self.config.MAX_CONTEXT_TOKENS // 2,
                            )
                        return sources, ctx

                    rag_future = self._executor.submit(_do_rag)

                if self.config.ANALYTICS_ENABLED:
                    analytics_future = self._executor.submit(
                        self._get_analytics_context, user_message
                    )

                if rag_future:
                    try:
                        rag_sources, rag_context = rag_future.result(timeout=5)
                        if rag_sources:
                            logger.debug(f"RAG found {len(rag_sources)} sources")
                    except Exception as e:
                        logger.warning(f"RAG retrieval failed: {e}")

                if analytics_future:
                    try:
                        analytics_context = analytics_future.result(timeout=5)
                    except Exception as e:
                        logger.warning(f"Analytics context failed: {e}")

                try:
                    learned_patterns = knowledge_future.result(timeout=2)
                except Exception as e:
                    logger.debug(f"Knowledge retrieval failed: {e}")

            # 5. Get provider and load tools
            provider = self.get_provider(model_config.provider.value)

            # Load tools for all providers (skip only for simple queries)
            tool_schemas = None
            if complexity != 'simple':
                try:
                    from ai_agent.tools import tool_registry
                    raw_schemas = tool_registry.get_schemas()
                    if raw_schemas:
                        tool_schemas = provider.format_tool_schemas(raw_schemas)
                except Exception as e:
                    logger.warning(f"Failed to load tool schemas: {e}")

            # 6. Build system prompt (needs has_tools flag)
            system_prompt = self._build_system_prompt(
                rag_context=rag_context,
                analytics_context=analytics_context,
                has_tools=bool(tool_schemas),
                learned_patterns=learned_patterns,
            )
            system_prompt_tokens = estimate_tokens(system_prompt)

            # 7. Build context messages (token-aware)
            context_messages = self._build_context_messages(
                conversation_id=conversation_id,
                current_message=user_message,
                model_config=model_config,
                system_prompt_tokens=system_prompt_tokens,
            )

            llm_response = provider.generate(
                model_name=model_config.model_name,
                messages=context_messages,
                max_tokens=model_config.max_tokens,
                temperature=float(model_config.default_temperature),
                api_key=model_config.api_key_encrypted,
                system=system_prompt,
                tools=tool_schemas,
            )

            # 7b. Tool call loop — execute tools and re-query LLM (provider-agnostic)
            total_input_tokens = llm_response.input_tokens
            total_output_tokens = llm_response.output_tokens
            tool_results_log = []
            max_tool_iterations = 5

            while llm_response.tool_calls and max_tool_iterations > 0:
                max_tool_iterations -= 1
                from ai_agent.tools import tool_registry

                # Build assistant message with tool calls (provider-specific format)
                context_messages.append(provider.build_tool_call_message(llm_response))

                # Execute each tool
                tool_results = []
                for tc in llm_response.tool_calls:
                    result = tool_registry.execute(
                        name=tc['name'],
                        params=tc['input'],
                        user_id=user_id,
                    )
                    tool_results_log.append({
                        'tool': tc['name'],
                        'input': tc['input'],
                        'output_preview': str(result)[:500],
                    })
                    import json
                    tool_results.append({
                        'tool_call_id': tc['id'],
                        'name': tc['name'],
                        'content': json.dumps(result, default=str),
                    })

                # Build tool result messages (provider-specific format)
                context_messages.extend(provider.build_tool_result_messages(tool_results))

                # Call LLM again with tool results
                llm_response = provider.generate(
                    model_name=model_config.model_name,
                    messages=context_messages,
                    max_tokens=model_config.max_tokens,
                    temperature=float(model_config.default_temperature),
                    api_key=model_config.api_key_encrypted,
                    system=system_prompt,
                    tools=tool_schemas,
                )
                total_input_tokens += llm_response.input_tokens
                total_output_tokens += llm_response.output_tokens

            if tool_results_log:
                logger.info(f"Tool calls in conv {conversation_id}: {[t['tool'] for t in tool_results_log]}")

            # 8. Calculate cost
            cost = self._calculate_cost(
                model_config=model_config,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
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
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                cost=cost,
                model_config_id=model_config.id,
                response_time_ms=response_time_ms,
                rag_sources=rag_sources_data,
            )
            saved_assistant_msg = self.message_repo.create(assistant_msg)

            # 11. Update conversation stats
            total_tokens = total_input_tokens + total_output_tokens
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
        page_context: Optional[str] = None,
    ):
        """
        Stream a chat response via SSE events.

        Yields SSE-formatted strings:
        - status events for UX feedback during context building
        - token events during LLM streaming
        - done event with metadata after completion

        Performance optimizations vs. original:
        - RAG + analytics run in parallel (saves 100-300ms)
        - Simple queries skip RAG/analytics entirely (saves 400-800ms)
        - Tools only loaded when query intent needs them (enables real streaming)
        - Real streaming for Claude when tools aren't needed (first token in ~500ms)
        """
        import json
        start_time = time.time()

        # Load runtime settings from DB
        self._load_runtime_settings()

        try:
            # 1. Validate conversation
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
                return

            if conversation.user_id != user_id:
                yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
                return

            # 2. Model config
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
            complexity = classify_complexity(user_message)
            model_config = self._select_model(user_message, model_config)

            # Save user message
            user_msg = Message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=user_message,
                model_config_id=model_config.id,
            )
            self.message_repo.create(user_msg)

            # 3. Skip RAG/analytics for simple queries (greetings, thanks, etc.)
            rag_sources = []
            rag_context = None
            analytics_context = None
            learned_patterns = []

            if complexity == 'simple':
                logger.debug("Simple query — skipping RAG and analytics")
            else:
                # Emit status so frontend shows what we're doing
                yield f"event: status\ndata: {json.dumps({'status': 'Searching knowledge base...'})}\n\n"

                # Run RAG, analytics, and knowledge retrieval in PARALLEL
                rag_future = None
                analytics_future = None
                knowledge_future = self._executor.submit(
                    self._get_learned_patterns, user_message
                )

                if self.config.RAG_ENABLED:
                    def _do_rag():
                        allowed = self.get_allowed_rag_sources(user_id)
                        sources = self.rag_service.search(
                            query=user_message,
                            limit=self.config.RAG_TOP_K,
                            company_id=None,
                            source_types=allowed,
                        )
                        ctx = None
                        if sources:
                            ctx = self.rag_service.format_context(
                                sources,
                                max_tokens=self.config.MAX_CONTEXT_TOKENS // 2,
                            )
                        return sources, ctx

                    rag_future = self._executor.submit(_do_rag)

                if self.config.ANALYTICS_ENABLED:
                    analytics_future = self._executor.submit(
                        self._get_analytics_context, user_message
                    )

                # Collect results (futures complete in parallel)
                if rag_future:
                    try:
                        rag_sources, rag_context = rag_future.result(timeout=5)
                    except Exception as e:
                        logger.warning(f"RAG retrieval failed: {e}")

                if analytics_future:
                    try:
                        analytics_context = analytics_future.result(timeout=5)
                    except Exception as e:
                        logger.warning(f"Analytics context failed: {e}")

                try:
                    learned_patterns = knowledge_future.result(timeout=2)
                except Exception as e:
                    logger.debug(f"Knowledge retrieval failed: {e}")

            provider = self.get_provider(model_config.provider.value)

            # 4. Load tools for all providers (skip only for simple queries)
            tool_schemas = None
            if complexity != 'simple':
                try:
                    from ai_agent.tools import tool_registry
                    raw_schemas = tool_registry.get_schemas()
                    if raw_schemas:
                        tool_schemas = provider.format_tool_schemas(raw_schemas)
                        logger.info(f"Tools loaded: {len(raw_schemas)} tools for {model_config.provider.value}/{model_config.model_name}")
                    else:
                        logger.warning(f"Tool registry returned empty schemas (tool_count={tool_registry.tool_count})")
                except Exception as e:
                    logger.error(f"Failed to load tool schemas for {model_config.provider.value}: {e}", exc_info=True)
            else:
                logger.info(f"Skipping tools: complexity='{complexity}' for '{user_message[:50]}'")

            logger.info(f"Tool decision: tool_schemas={'set' if tool_schemas else 'None'}, complexity='{complexity}', provider={model_config.provider.value}")

            # 5. Build system prompt (needs has_tools flag)
            system_prompt = self._build_system_prompt(
                rag_context=rag_context,
                analytics_context=analytics_context,
                has_tools=bool(tool_schemas),
                learned_patterns=learned_patterns,
                page_context=page_context,
            )
            system_prompt_tokens = estimate_tokens(system_prompt)

            # 6. Build context messages (token-aware)
            context_messages = self._build_context_messages(
                conversation_id=conversation_id,
                current_message=user_message,
                model_config=model_config,
                system_prompt_tokens=system_prompt_tokens,
            )

            tools_used = False
            tools_used_names = []
            total_input_tokens = 0
            total_output_tokens = 0
            llm_response = None

            # 7a. Tool path — non-streaming call + tool loop (provider-agnostic)
            if tool_schemas:
                yield f"event: status\ndata: {json.dumps({'status': 'Analyzing query...'})}\n\n"

                llm_response = provider.generate(
                    model_name=model_config.model_name,
                    messages=context_messages,
                    max_tokens=model_config.max_tokens,
                    temperature=float(model_config.default_temperature),
                    api_key=model_config.api_key_encrypted,
                    system=system_prompt,
                    tools=tool_schemas,
                )
                total_input_tokens += llm_response.input_tokens
                total_output_tokens += llm_response.output_tokens

                # Tool call loop
                max_tool_iterations = 5
                while llm_response.tool_calls and max_tool_iterations > 0:
                    max_tool_iterations -= 1
                    tools_used = True
                    from ai_agent.tools import tool_registry as _tr

                    yield f"event: status\ndata: {json.dumps({'status': 'Using tools...'})}\n\n"

                    # Build assistant message (provider-specific format)
                    context_messages.append(provider.build_tool_call_message(llm_response))

                    # Execute tools (parallel if multiple)
                    tool_calls = llm_response.tool_calls
                    tool_results = []

                    if len(tool_calls) > 1:
                        futures = {}
                        for tc in tool_calls:
                            tools_used_names.append(tc['name'])
                            futures[tc['id']] = self._executor.submit(
                                _tr.execute, name=tc['name'], params=tc['input'], user_id=user_id
                            )
                        for tc in tool_calls:
                            result = futures[tc['id']].result(timeout=10)
                            tool_results.append({
                                'tool_call_id': tc['id'],
                                'name': tc['name'],
                                'content': json.dumps(result, default=str),
                            })
                    else:
                        for tc in tool_calls:
                            tools_used_names.append(tc['name'])
                            result = _tr.execute(name=tc['name'], params=tc['input'], user_id=user_id)
                            tool_results.append({
                                'tool_call_id': tc['id'],
                                'name': tc['name'],
                                'content': json.dumps(result, default=str),
                            })

                    # Build tool result messages (provider-specific format)
                    context_messages.extend(provider.build_tool_result_messages(tool_results))

                    yield f"event: status\ndata: {json.dumps({'status': 'Processing tool results...'})}\n\n"

                    llm_response = provider.generate(
                        model_name=model_config.model_name,
                        messages=context_messages,
                        max_tokens=model_config.max_tokens,
                        temperature=float(model_config.default_temperature),
                        api_key=model_config.api_key_encrypted,
                        system=system_prompt,
                        tools=tool_schemas,
                    )
                    total_input_tokens += llm_response.input_tokens
                    total_output_tokens += llm_response.output_tokens

                # Emit the buffered response as chunks
                content = llm_response.content or ''
                chunk_size = 20
                for i in range(0, len(content), chunk_size):
                    yield f"event: token\ndata: {json.dumps({'content': content[i:i+chunk_size]})}\n\n"

            else:
                # 7b. Streaming path — real token-by-token streaming (simple queries only)
                yield f"event: status\ndata: {json.dumps({'status': 'Generating response...'})}\n\n"

                for text_chunk, final_response in provider.generate_stream(
                    model_name=model_config.model_name,
                    messages=context_messages,
                    max_tokens=model_config.max_tokens,
                    temperature=float(model_config.default_temperature),
                    api_key=model_config.api_key_encrypted,
                    system=system_prompt,
                ):
                    if text_chunk is not None:
                        yield f"event: token\ndata: {json.dumps({'content': text_chunk})}\n\n"
                    if final_response is not None:
                        llm_response = final_response
                        total_input_tokens = llm_response.input_tokens
                        total_output_tokens = llm_response.output_tokens

            if not llm_response:
                yield f"event: error\ndata: {json.dumps({'error': 'No response from LLM'})}\n\n"
                return

            # 8. Post-stream: save message, update stats
            cost = self._calculate_cost(
                model_config=model_config,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
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
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                cost=cost,
                model_config_id=model_config.id,
                response_time_ms=response_time_ms,
                rag_sources=rag_sources_data,
            )
            saved_msg = self.message_repo.create(assistant_msg)

            total_tokens = total_input_tokens + total_output_tokens
            self.conversation_repo.update_stats(
                conversation_id=conversation_id,
                tokens=total_tokens,
                cost=cost,
                messages=2,
            )

            if conversation.message_count == 0:
                self._auto_title_conversation(conversation_id, user_message)

            # Final done event
            done_data = {
                'message_id': saved_msg.id,
                'tokens_used': total_tokens,
                'cost': str(cost),
                'response_time_ms': response_time_ms,
                'rag_sources': [{'doc_id': s.doc_id, 'score': s.score, 'snippet': s.snippet, 'source_type': s.source_type} for s in rag_sources],
            }
            if tools_used_names:
                done_data['tools_used'] = list(dict.fromkeys(tools_used_names))
            yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

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

    def _get_learned_patterns(self, query: str) -> List[str]:
        """Get learned patterns relevant to the current query."""
        try:
            from .knowledge_service import KnowledgeService
            svc = KnowledgeService(self.config)
            return svc.get_relevant_patterns(query, limit=5)
        except Exception as e:
            logger.debug(f"Knowledge retrieval skipped: {e}")
            return []

    # Page path → human-readable description for system prompt injection
    _PAGE_DESCRIPTIONS = {
        '/app/dashboard': 'Dashboard — company statistics overview',
        '/app/accounting': 'Accounting — supplier invoice management',
        '/app/hr': 'HR — employee management, events, and bonuses',
        '/app/statements': 'Bank Statements — bank transactions and reconciliation',
        '/app/efactura': 'E-Factura — electronic invoices from ANAF',
        '/app/approvals': 'Approvals — workflow approval requests',
        '/app/marketing': 'Marketing — projects and campaigns',
        '/app/sales/crm': 'CRM (Sales) — client management and car sales dossiers. '
                          '"Clients" here are car buyers/customers, NOT suppliers. '
                          '"Furnizor/supplier" refers to invoice suppliers in Accounting.',
        '/app/settings': 'Settings — system configuration',
        '/app/profile': 'User Profile',
    }

    def _describe_page(self, path: Optional[str]) -> Optional[str]:
        """Map a frontend route path to a human-readable page description."""
        if not path:
            return None
        # Exact match first, then prefix match for nested routes
        if path in self._PAGE_DESCRIPTIONS:
            return self._PAGE_DESCRIPTIONS[path]
        for prefix, desc in self._PAGE_DESCRIPTIONS.items():
            if path.startswith(prefix):
                return desc
        return None

    def _build_system_prompt(
        self,
        rag_context: Optional[str] = None,
        analytics_context: Optional[str] = None,
        has_tools: bool = False,
        learned_patterns: Optional[List[str]] = None,
        page_context: Optional[str] = None,
    ) -> str:
        """
        Build system prompt for LLM with domain knowledge, tool examples,
        Romanian glossary, and learned patterns from user feedback.

        Args:
            rag_context: Optional RAG context to include
            analytics_context: Optional analytics data to include
            has_tools: Whether tools are available for this request
            learned_patterns: Optional list of learned pattern strings
            page_context: Optional frontend route path (e.g. '/app/sales/crm')

        Returns:
            Complete system prompt
        """
        from datetime import date

        today = date.today().strftime('%d.%m.%Y')

        base_prompt = f"""You are JARVIS, an intelligent AI assistant for the JARVIS enterprise platform used by AUTOWORLD — a group of car dealerships in Romania (Toyota, Lexus, Porsche, Bentley, Lamborghini).

Today's date: {today}

JARVIS manages these data entities:
- **Invoices**: supplier invoices with number, date, value, currency (RON/EUR), status (pending/paid/approved/overdue), supplier name, allocations to companies/departments/brands
- **Bank Transactions**: bank statement lines with vendor, amount, date, reconciliation status, linked to companies via CUI
- **e-Factura**: electronic invoices from ANAF (Romanian tax authority), with allocation status (unallocated/hidden/allocated), direction (sent/received)
- **Companies**: legal entities in the group (e.g., Autoworld SRL, Autoworld Premium SRL), identified by CUI/VAT code
- **Departments & Brands**: organizational units (Sales, Service, Parts) under companies, brands (Toyota, Lexus, Porsche, etc.)
- **Employees**: staff members with name, role, department, company assignment
- **HR Events**: company events (dealer open doors, team buildings, masterclasses) with employee bonuses/participation
- **Marketing Projects**: campaigns with budgets, KPIs, team members, status workflow (draft→pending→active→completed)
- **Approvals**: workflow requests for invoices and marketing projects with multi-step approval chains

Response guidelines:
- Be helpful, accurate, and concise
- Format currency: "1.234,56 RON" or "1.234,56 EUR" (Romanian thousands separator = dot, decimal = comma)
- Format dates: DD.MM.YYYY (e.g., 24.02.2026)
- Use markdown tables for financial data, include totals
- Always respond in the same language as the user's message (Romanian or English)"""

        sections = [base_prompt]

        # Inject page context so the model knows what the user is looking at
        page_desc = self._describe_page(page_context)
        if page_desc:
            sections.append(f"""CURRENT PAGE CONTEXT:
The user is currently viewing: {page_desc}
Use this context to interpret ambiguous questions. For example:
- On the CRM page, "client" / "cel mai mare client" means a car buyer/customer — use get_top_clients or search_clients, NOT get_top_suppliers.
- On the Accounting page, "furnizor" means an invoice supplier — use get_top_suppliers or search_invoices.
- On the HR page, prefer HR tools (search_hr_events, search_bonuses) over others.""")

        if has_tools:
            sections.append("""TOOL USAGE — MANDATORY:
You have tools that query the JARVIS database in real-time. You MUST use them when the user asks about data.

RULES:
1. NEVER say "I don't have access to real-time data" or "I cannot access the database" — you DO have access via tools.
2. ALWAYS call a tool when the user asks about invoices, transactions, suppliers, employees, events, approvals, or marketing projects.
3. If unsure which tool to use, prefer search_invoices for invoice questions and get_invoice_summary for totals/aggregations.
4. After getting tool results, present the data clearly with markdown tables when appropriate.

EXAMPLES of when to use each tool:
- "Arată-mi facturile de la Porsche" → search_invoices(supplier="Porsche")
- "Câte facturi avem luna aceasta?" → get_invoice_summary(start_date="2026-02-01")
- "Top 5 furnizori" → get_top_suppliers(limit=5)
- "Cel mai mare client" / "Top clienti" → get_top_clients(limit=5)
- "Caută client Popescu" → search_clients(name="Popescu")
- "Ce aprobări am de făcut?" → get_pending_approvals(scope="mine")
- "Detalii factura 123" → get_invoice_details(invoice_id=123)
- "Sumar e-Factura" → get_efactura_summary()
- "Bonusuri angajat Ion Popescu" → search_bonuses(employee="Ion Popescu")
- "Proiecte marketing active" → search_marketing_projects(status="active")
- "Tranzacții bancare luna ianuarie" → get_transaction_summary(date_from="2026-01-01", date_to="2026-01-31")
- "Evenimente HR din 2025" → search_hr_events(year=2025)

IMPORTANT — client ≠ furnizor:
- "client" / "cel mai mare client" = CRM client (car buyer). Use get_top_clients or search_clients.
- "furnizor" / "supplier" = invoice supplier (vendor we pay). Use get_top_suppliers or search_invoices.
Do NOT confuse these — they are different entities in different modules.""")

        sections.append("""ROMANIAN GLOSSARY (user may ask in Romanian):
factura/facturi = invoice(s), furnizor = supplier (vendor we pay), client = client (car buyer/customer),
cheltuieli = spending/expenses, plată = payment, departament = department, angajat = employee,
bonus/bonusuri = bonus(es), eveniment = event, luna/lună = month, an/anul = year,
total/totaluri = total(s), aprobare = approval, tranzacție = transaction, extras bancar = bank statement,
buget = budget, proiect = project, ultima/ultimele = last/recent, câte/câți = how many,
arată = show, caută = search, dosare = dossiers (car sales files), vânzări = sales""")

        if learned_patterns:
            patterns_text = '\n'.join(f'- {p}' for p in learned_patterns)
            sections.append(f"""LEARNED PATTERNS (from past successful interactions):
{patterns_text}

Use these patterns to improve your responses when they are relevant to the current query.""")

        if analytics_context:
            sections.append(f"""ANALYTICS DATA (live aggregations from JARVIS database):
{analytics_context}

Present this data clearly using markdown tables. Include totals where appropriate.""")

        if rag_context:
            sections.append(f"""CONTEXT FROM JARVIS DATABASE:
{rag_context}""")

        if not analytics_context and not rag_context and not has_tools:
            sections.append("Note: No specific context was retrieved for this query. Answer based on your general knowledge about the JARVIS platform.")

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
