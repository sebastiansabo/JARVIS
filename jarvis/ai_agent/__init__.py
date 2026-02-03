"""
AI Agent Module

JARVIS AI chatbot with RAG capabilities for enterprise data queries.

Features:
- Multi-provider LLM support (Claude, OpenAI, Gemini, Groq)
- Conversation history and context management
- RAG integration for invoice/transaction queries
- Cost tracking per conversation
"""
from flask import Blueprint

ai_agent_bp = Blueprint(
    'ai_agent',
    __name__,
    url_prefix='/ai-agent',
)

# Import routes to register them
from . import routes  # noqa: E402, F401
