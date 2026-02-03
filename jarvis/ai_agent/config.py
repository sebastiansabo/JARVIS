"""
AI Agent Configuration

Environment variables and settings for the AI Agent module.
Following pattern from accounting/efactura/config.py.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIAgentConfig:
    """AI Agent configuration settings."""

    # RAG Settings
    RAG_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_EMBEDDING_DIMENSIONS: int = 1536
    RAG_TOP_K: int = 5                    # Number of documents to retrieve
    RAG_MIN_SIMILARITY: float = 0.7       # Minimum similarity score

    # Context Settings
    MAX_CONTEXT_MESSAGES: int = 10        # Messages to include in context
    MAX_CONTEXT_TOKENS: int = 8000        # Max tokens for context

    # Response Settings
    DEFAULT_MAX_TOKENS: int = 2048
    DEFAULT_TEMPERATURE: float = 0.7

    # Cost Tracking
    ENABLE_COST_TRACKING: bool = True
    COST_ALERT_THRESHOLD: float = 10.0    # Alert if daily cost exceeds

    # Security
    ENABLE_DATA_FILTERING: bool = True
    LOG_CONVERSATIONS: bool = True

    # Performance
    EMBEDDING_BATCH_SIZE: int = 100
    REINDEX_BATCH_SIZE: int = 500

    # Feature Flags
    RAG_ENABLED: bool = True              # Enable RAG (requires OpenAI key)
    MULTI_PROVIDER_ENABLED: bool = True   # Enable multiple LLM providers

    @classmethod
    def from_env(cls) -> 'AIAgentConfig':
        """Load configuration from environment variables."""
        return cls(
            RAG_EMBEDDING_MODEL=os.environ.get(
                'AI_AGENT_EMBEDDING_MODEL', 'text-embedding-3-small'
            ),
            RAG_TOP_K=int(os.environ.get('AI_AGENT_RAG_TOP_K', '5')),
            RAG_MIN_SIMILARITY=float(os.environ.get(
                'AI_AGENT_RAG_MIN_SIMILARITY', '0.7'
            )),
            MAX_CONTEXT_MESSAGES=int(os.environ.get(
                'AI_AGENT_MAX_CONTEXT_MESSAGES', '10'
            )),
            DEFAULT_MAX_TOKENS=int(os.environ.get(
                'AI_AGENT_MAX_TOKENS', '2048'
            )),
            DEFAULT_TEMPERATURE=float(os.environ.get(
                'AI_AGENT_TEMPERATURE', '0.7'
            )),
            ENABLE_COST_TRACKING=os.environ.get(
                'AI_AGENT_COST_TRACKING', 'true'
            ).lower() == 'true',
            LOG_CONVERSATIONS=os.environ.get(
                'AI_AGENT_LOG_CONVERSATIONS', 'true'
            ).lower() == 'true',
            RAG_ENABLED=os.environ.get(
                'AI_AGENT_RAG_ENABLED', 'true'
            ).lower() == 'true',
            MULTI_PROVIDER_ENABLED=os.environ.get(
                'AI_AGENT_MULTI_PROVIDER', 'true'
            ).lower() == 'true',
        )


# System prompt template for RAG responses
SYSTEM_PROMPT_TEMPLATE = """You are JARVIS, an AI assistant for the J.A.R.V.I.S. enterprise platform.

You have access to platform data including invoices, bank transactions, company information, employee data, and organizational structure.

When answering questions:
1. Use ONLY the provided context data - do not make up information
2. Cite your sources by referencing invoice numbers, dates, company names, or other identifiers
3. If the data doesn't contain enough information to answer, say so clearly
4. Format financial amounts with currency symbols (e.g., "1.234,56 RON" or "5.000 EUR")
5. Use Romanian date format (DD.MM.YYYY) when displaying dates
6. Be concise but thorough - include relevant details

Current user: {user_name}
User role: {user_role}
Today's date: {today}

{rag_context}"""

# System prompt for conversations without RAG context
SYSTEM_PROMPT_NO_RAG = """You are JARVIS, an AI assistant for the J.A.R.V.I.S. enterprise platform.

You can help with:
- Explaining how to use the platform features
- Answering general questions about accounting, invoicing, HR processes
- Providing guidance on best practices

Note: To answer questions about specific invoices, transactions, or company data, the user should ask questions that reference the actual data in the system.

Current user: {user_name}
User role: {user_role}
Today's date: {today}"""

# Prompt for entity extraction
ENTITY_EXTRACTION_PROMPT = """Extract the following entities from the user's query if present:

- dates: Any dates or date ranges (e.g., "January 2026", "last month", "2025-01-15")
- amounts: Any monetary amounts (e.g., "5000 RON", "over 1000 EUR")
- companies: Company or supplier names (e.g., "ACME Corp", "Meta", "Google")
- invoice_numbers: Invoice or document numbers (e.g., "INV-001", "FBADS-123")
- people: Person names (e.g., employees, contacts)
- departments: Department or brand names
- status: Status values (e.g., "paid", "pending", "overdue")

User query: {query}

Respond in JSON format:
{
  "dates": [],
  "amounts": [],
  "companies": [],
  "invoice_numbers": [],
  "people": [],
  "departments": [],
  "status": [],
  "intent": "query|analysis|report|action|general"
}"""


# Default configuration instance
_default_config: Optional[AIAgentConfig] = None


def get_config() -> AIAgentConfig:
    """Get the default configuration instance."""
    global _default_config
    if _default_config is None:
        _default_config = AIAgentConfig.from_env()
    return _default_config


def reset_config():
    """Reset configuration (for testing)."""
    global _default_config
    _default_config = None
