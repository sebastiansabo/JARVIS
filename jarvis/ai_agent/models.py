"""
AI Agent Data Models

Data classes representing AI Agent entities.
Following JARVIS pattern from accounting/efactura/models.py.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum


class ConversationStatus(Enum):
    """Status of a conversation."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MessageRole(Enum):
    """Role of message sender."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class LLMProvider(Enum):
    """Supported LLM providers."""
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    GROQ = "groq"
    LOCAL = "local"


class QueryIntent(Enum):
    """Detected intent of user query."""
    QUERY = "query"           # Simple data lookup
    ANALYSIS = "analysis"     # Calculations, summaries
    REPORT = "report"         # Generate report
    ACTION = "action"         # Perform action
    GENERAL = "general"       # General conversation


class RAGSourceType(Enum):
    """Types of RAG data sources."""
    INVOICE = "invoice"
    TRANSACTION = "transaction"
    COMPANY = "company"
    EMPLOYEE = "employee"
    DEPARTMENT = "department"
    EVENT = "event"


@dataclass
class ModelConfig:
    """LLM Model configuration."""
    id: Optional[int] = None
    provider: LLMProvider = LLMProvider.CLAUDE
    model_name: str = "claude-sonnet-4-20250514"
    display_name: Optional[str] = None
    api_key_encrypted: Optional[str] = None
    base_url: Optional[str] = None

    cost_per_1k_input: Decimal = field(default_factory=lambda: Decimal("0"))
    cost_per_1k_output: Decimal = field(default_factory=lambda: Decimal("0"))

    max_tokens: int = 4096
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100000
    default_temperature: Decimal = field(default_factory=lambda: Decimal("0.7"))

    is_active: bool = True
    is_default: bool = False

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Convert string provider to enum if needed."""
        if isinstance(self.provider, str):
            self.provider = LLMProvider(self.provider)


@dataclass
class Conversation:
    """Chat conversation/session."""
    id: Optional[int] = None
    user_id: int = 0
    title: Optional[str] = None
    model_config_id: Optional[int] = None

    status: ConversationStatus = ConversationStatus.ACTIVE

    total_tokens: int = 0
    total_cost: Decimal = field(default_factory=lambda: Decimal("0"))
    message_count: int = 0

    metadata: Dict[str, Any] = field(default_factory=dict)

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None

    def __post_init__(self):
        """Convert string status to enum if needed."""
        if isinstance(self.status, str):
            self.status = ConversationStatus(self.status)


@dataclass
class Message:
    """Individual chat message."""
    id: Optional[int] = None
    conversation_id: int = 0

    role: MessageRole = MessageRole.USER
    content: str = ""

    input_tokens: int = 0
    output_tokens: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))

    rag_sources: List[Dict[str, Any]] = field(default_factory=list)
    model_config_id: Optional[int] = None
    response_time_ms: Optional[int] = None

    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Convert string role to enum if needed."""
        if isinstance(self.role, str):
            self.role = MessageRole(self.role)


@dataclass
class RAGDocument:
    """Indexed document for RAG retrieval."""
    id: Optional[int] = None

    source_type: RAGSourceType = RAGSourceType.INVOICE
    source_id: Optional[int] = None
    source_table: Optional[str] = None

    content: str = ""
    content_hash: Optional[str] = None

    embedding: Optional[List[float]] = None  # 1536-dim vector

    metadata: Dict[str, Any] = field(default_factory=dict)
    company_id: Optional[int] = None

    is_active: bool = True

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Used in search results
    score: float = 0.0

    def __post_init__(self):
        """Convert string source_type to enum if needed."""
        if isinstance(self.source_type, str):
            self.source_type = RAGSourceType(self.source_type)


@dataclass
class ConversationContext:
    """Analyzed context for a message."""
    id: Optional[int] = None
    message_id: int = 0

    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    detected_intent: Optional[QueryIntent] = None
    confidence: Optional[Decimal] = None

    rag_query: Optional[str] = None
    rag_results: List[Dict[str, Any]] = field(default_factory=list)

    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Convert string intent to enum if needed."""
        if isinstance(self.detected_intent, str):
            self.detected_intent = QueryIntent(self.detected_intent)


@dataclass
class RAGSource:
    """Reference to a RAG source used in response."""
    doc_id: int
    score: float
    snippet: str
    source_type: str
    source_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Response from LLM provider."""
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: Optional[str] = None


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None


@dataclass
class ChatResponse:
    """Response from chat interaction."""
    message: Message
    rag_sources: List[RAGSource] = field(default_factory=list)
    tokens_used: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))
    response_time_ms: int = 0
