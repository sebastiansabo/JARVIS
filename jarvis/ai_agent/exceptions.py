"""
AI Agent Custom Exceptions

Custom exception classes for the AI Agent module.
"""


class AIAgentError(Exception):
    """Base exception for AI Agent module."""
    pass


class ConversationNotFoundError(AIAgentError):
    """Raised when a conversation is not found."""
    def __init__(self, conversation_id: int):
        self.conversation_id = conversation_id
        super().__init__(f"Conversation {conversation_id} not found")


class ConversationAccessDeniedError(AIAgentError):
    """Raised when user doesn't have access to a conversation."""
    def __init__(self, conversation_id: int, user_id: int):
        self.conversation_id = conversation_id
        self.user_id = user_id
        super().__init__(
            f"User {user_id} does not have access to conversation {conversation_id}"
        )


class ConversationNotActiveError(AIAgentError):
    """Raised when trying to interact with a non-active conversation."""
    def __init__(self, conversation_id: int, status: str):
        self.conversation_id = conversation_id
        self.status = status
        super().__init__(
            f"Conversation {conversation_id} is {status}, not active"
        )


class ModelConfigNotFoundError(AIAgentError):
    """Raised when a model configuration is not found."""
    def __init__(self, model_id: int = None, provider: str = None):
        self.model_id = model_id
        self.provider = provider
        if model_id:
            msg = f"Model configuration {model_id} not found"
        elif provider:
            msg = f"No active model configuration found for provider {provider}"
        else:
            msg = "No active model configuration found"
        super().__init__(msg)


class LLMProviderError(AIAgentError):
    """Base exception for LLM provider errors."""
    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class LLMAuthenticationError(LLMProviderError):
    """Raised when LLM provider authentication fails."""
    def __init__(self, provider: str):
        super().__init__(provider, "Authentication failed - check API key")


class LLMRateLimitError(LLMProviderError):
    """Raised when LLM provider rate limit is exceeded."""
    def __init__(self, provider: str, retry_after: int = None):
        self.retry_after = retry_after
        msg = "Rate limit exceeded"
        if retry_after:
            msg += f" - retry after {retry_after} seconds"
        super().__init__(provider, msg)


class LLMModelNotFoundError(LLMProviderError):
    """Raised when specified model is not found."""
    def __init__(self, provider: str, model_name: str):
        self.model_name = model_name
        super().__init__(provider, f"Model '{model_name}' not found")


class LLMTimeoutError(LLMProviderError):
    """Raised when LLM request times out."""
    def __init__(self, provider: str, timeout: int):
        self.timeout = timeout
        super().__init__(provider, f"Request timed out after {timeout} seconds")


class LLMContentFilterError(LLMProviderError):
    """Raised when content is filtered by the LLM provider."""
    def __init__(self, provider: str, reason: str = None):
        self.reason = reason
        msg = "Content was filtered"
        if reason:
            msg += f": {reason}"
        super().__init__(provider, msg)


class RAGError(AIAgentError):
    """Base exception for RAG errors."""
    pass


class EmbeddingError(RAGError):
    """Raised when embedding generation fails."""
    def __init__(self, message: str):
        super().__init__(f"Embedding error: {message}")


class RAGSearchError(RAGError):
    """Raised when RAG search fails."""
    def __init__(self, message: str):
        super().__init__(f"RAG search error: {message}")


class RAGIndexError(RAGError):
    """Raised when RAG indexing fails."""
    def __init__(self, source_type: str, source_id: int, message: str):
        self.source_type = source_type
        self.source_id = source_id
        super().__init__(
            f"Failed to index {source_type} {source_id}: {message}"
        )


class SecurityError(AIAgentError):
    """Raised when security check fails."""
    def __init__(self, message: str):
        super().__init__(f"Security error: {message}")


class DataAccessDeniedError(SecurityError):
    """Raised when user doesn't have access to data."""
    def __init__(self, user_id: int, resource: str):
        self.user_id = user_id
        self.resource = resource
        super().__init__(f"User {user_id} cannot access {resource}")


class ConfigurationError(AIAgentError):
    """Raised when configuration is invalid or missing."""
    def __init__(self, message: str):
        super().__init__(f"Configuration error: {message}")
