"""
Claude Provider

Anthropic Claude LLM provider implementation.
"""

import os
from typing import List, Dict, Any, Optional

import anthropic

from core.utils.logging_config import get_logger
from ..models import LLMResponse
from ..exceptions import LLMProviderError, LLMRateLimitError, LLMAuthenticationError
from .base_provider import BaseProvider

logger = get_logger('jarvis.ai_agent.providers.claude')


class ClaudeProvider(BaseProvider):
    """Anthropic Claude LLM provider."""

    @property
    def name(self) -> str:
        return "claude"

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
        Generate a response using Claude.

        Args:
            model_name: Claude model identifier (e.g., 'claude-sonnet-4-20250514')
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-1.0 for Claude)
            api_key: API key (optional, falls back to ANTHROPIC_API_KEY env)
            **kwargs: Additional options (system prompt, etc.)

        Returns:
            LLMResponse with content and token counts

        Raises:
            LLMProviderError: If API call fails
            LLMRateLimitError: If rate limited
            LLMAuthenticationError: If API key invalid
        """
        # Get API key
        key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            raise LLMAuthenticationError("ANTHROPIC_API_KEY not found")

        # Extract system message if present
        system_content, remaining_messages = self.extract_system_message(messages)

        # Allow system override from kwargs
        if 'system' in kwargs:
            system_content = kwargs.pop('system')

        # Format messages for Claude API
        formatted_messages = self.format_messages(remaining_messages)

        # Clamp temperature to Claude's range (0.0-1.0)
        temperature = max(0.0, min(1.0, temperature))

        try:
            client = anthropic.Anthropic(api_key=key)

            # Build request parameters
            request_params = {
                'model': model_name,
                'max_tokens': max_tokens,
                'temperature': temperature,
                'messages': formatted_messages,
            }

            # Add system message if present
            if system_content:
                request_params['system'] = system_content

            logger.debug(f"Claude API request: model={model_name}, messages={len(formatted_messages)}")

            response = client.messages.create(**request_params)

            # Extract content from response
            content = ""
            if response.content:
                content = response.content[0].text

            # Get token counts from usage
            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0

            logger.debug(f"Claude API response: tokens_in={input_tokens}, tokens_out={output_tokens}")

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                finish_reason=response.stop_reason,
            )

        except anthropic.RateLimitError as e:
            logger.warning(f"Claude rate limit exceeded: {e}")
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")

        except anthropic.AuthenticationError as e:
            logger.error(f"Claude authentication failed: {e}")
            raise LLMAuthenticationError(f"Authentication failed: {e}")

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            raise LLMProviderError(f"Claude API error: {e}")

        except Exception as e:
            logger.error(f"Unexpected error calling Claude: {e}")
            raise LLMProviderError(f"Failed to call Claude API: {e}")

    def format_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        Format messages for Claude API.

        Claude requires alternating user/assistant messages.
        Consecutive messages of the same role are merged.

        Args:
            messages: List of message dicts

        Returns:
            Formatted messages for Claude
        """
        if not messages:
            return []

        formatted = []
        prev_role = None

        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            # Skip system messages (handled separately)
            if role == 'system':
                continue

            # Normalize role to user/assistant
            if role not in ('user', 'assistant'):
                role = 'user'

            # Merge consecutive messages of the same role
            if role == prev_role and formatted:
                formatted[-1]['content'] += f"\n\n{content}"
            else:
                formatted.append({
                    'role': role,
                    'content': content,
                })
                prev_role = role

        # Ensure first message is from user (Claude requirement)
        if formatted and formatted[0]['role'] != 'user':
            formatted.insert(0, {
                'role': 'user',
                'content': '[Conversation context]'
            })

        return formatted
