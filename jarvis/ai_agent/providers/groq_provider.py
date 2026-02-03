"""
Groq Provider

Groq LLM provider implementation for ultra-fast inference.
"""

import os
from typing import List, Dict, Any, Optional

from core.utils.logging_config import get_logger
from ..models import LLMResponse
from ..exceptions import LLMProviderError, LLMRateLimitError, LLMAuthenticationError
from .base_provider import BaseProvider

logger = get_logger('jarvis.ai_agent.providers.groq')


class GroqProvider(BaseProvider):
    """Groq LLM provider for fast inference."""

    @property
    def name(self) -> str:
        return "groq"

    def generate(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate a response using Groq.

        Args:
            model_name: Groq model identifier (e.g., 'mixtral-8x7b-32768', 'llama-3.3-70b-versatile')
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            api_key: API key (optional, falls back to GROQ_API_KEY env)
            **kwargs: Additional options (system prompt, etc.)

        Returns:
            LLMResponse with content and token counts

        Raises:
            LLMProviderError: If API call fails
            LLMRateLimitError: If rate limited
            LLMAuthenticationError: If API key invalid
        """
        try:
            from groq import Groq
        except ImportError:
            raise LLMProviderError("groq package not installed. Run: pip install groq")

        # Get API key
        key = api_key or os.environ.get('GROQ_API_KEY')
        if not key:
            raise LLMAuthenticationError("GROQ_API_KEY not found")

        # Format messages for Groq API (OpenAI-compatible)
        formatted_messages = self.format_messages(messages)

        # Add system message if provided in kwargs
        if 'system' in kwargs:
            formatted_messages.insert(0, {
                'role': 'system',
                'content': kwargs.pop('system'),
            })

        # Clamp temperature
        temperature = max(0.0, min(2.0, temperature))

        try:
            client = Groq(api_key=key)

            logger.debug(f"Groq API request: model={model_name}, messages={len(formatted_messages)}")

            response = client.chat.completions.create(
                model=model_name,
                messages=formatted_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            # Extract content from response
            content = ""
            if response.choices:
                content = response.choices[0].message.content or ""

            # Get token counts from usage
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            finish_reason = response.choices[0].finish_reason if response.choices else None

            logger.debug(f"Groq API response: tokens_in={input_tokens}, tokens_out={output_tokens}")

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                finish_reason=finish_reason,
            )

        except Exception as e:
            error_str = str(e).lower()
            if 'rate' in error_str and 'limit' in error_str:
                logger.warning(f"Groq rate limit exceeded: {e}")
                raise LLMRateLimitError(f"Rate limit exceeded: {e}")
            elif 'auth' in error_str or 'key' in error_str or 'unauthorized' in error_str:
                logger.error(f"Groq authentication failed: {e}")
                raise LLMAuthenticationError(f"Authentication failed: {e}")
            else:
                logger.error(f"Groq API error: {e}")
                raise LLMProviderError(f"Groq API error: {e}")

    def format_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        Format messages for Groq API (OpenAI-compatible).

        Args:
            messages: List of message dicts

        Returns:
            Formatted messages for Groq
        """
        if not messages:
            return []

        formatted = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role not in ('system', 'user', 'assistant'):
                role = 'user'

            formatted.append({
                'role': role,
                'content': content,
            })

        return formatted
