"""
OpenAI Provider

OpenAI GPT LLM provider implementation.
"""

import os
from typing import List, Dict, Any, Optional

import openai

from core.utils.logging_config import get_logger
from ..models import LLMResponse
from ..exceptions import LLMProviderError, LLMRateLimitError, LLMAuthenticationError
from .base_provider import BaseProvider

logger = get_logger('jarvis.ai_agent.providers.openai')


class OpenAIProvider(BaseProvider):
    """OpenAI GPT LLM provider."""

    @property
    def name(self) -> str:
        return "openai"

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
        Generate a response using OpenAI GPT.

        Args:
            model_name: OpenAI model identifier (e.g., 'gpt-4-turbo', 'gpt-3.5-turbo')
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            api_key: API key (optional, falls back to OPENAI_API_KEY env)
            **kwargs: Additional options (system prompt, etc.)

        Returns:
            LLMResponse with content and token counts

        Raises:
            LLMProviderError: If API call fails
            LLMRateLimitError: If rate limited
            LLMAuthenticationError: If API key invalid
        """
        # Get API key
        key = api_key or os.environ.get('OPENAI_API_KEY')
        if not key:
            raise LLMAuthenticationError("OPENAI_API_KEY not found")

        # Format messages for OpenAI API
        formatted_messages = self.format_messages(messages)

        # Add system message if provided in kwargs
        if 'system' in kwargs:
            formatted_messages.insert(0, {
                'role': 'system',
                'content': kwargs.pop('system'),
            })

        # Clamp temperature to OpenAI's range (0.0-2.0)
        temperature = max(0.0, min(2.0, temperature))

        try:
            client = openai.OpenAI(api_key=key)

            logger.debug(f"OpenAI API request: model={model_name}, messages={len(formatted_messages)}")

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

            logger.debug(f"OpenAI API response: tokens_in={input_tokens}, tokens_out={output_tokens}")

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                finish_reason=finish_reason,
            )

        except openai.RateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded: {e}")
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")

        except openai.AuthenticationError as e:
            logger.error(f"OpenAI authentication failed: {e}")
            raise LLMAuthenticationError(f"Authentication failed: {e}")

        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMProviderError(f"OpenAI API error: {e}")

        except Exception as e:
            logger.error(f"Unexpected error calling OpenAI: {e}")
            raise LLMProviderError(f"Failed to call OpenAI API: {e}")

    def format_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        Format messages for OpenAI API.

        OpenAI accepts messages in the standard format.

        Args:
            messages: List of message dicts

        Returns:
            Formatted messages for OpenAI
        """
        if not messages:
            return []

        formatted = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            # OpenAI accepts system, user, assistant roles
            if role not in ('system', 'user', 'assistant'):
                role = 'user'

            formatted.append({
                'role': role,
                'content': content,
            })

        return formatted
