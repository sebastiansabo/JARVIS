"""
Grok (xAI) Provider

xAI Grok LLM provider implementation.
Uses OpenAI-compatible API at https://api.x.ai/v1.
"""

import json as json_module
import os
from typing import List, Dict, Any, Optional, Generator, Tuple

import openai

from core.utils.logging_config import get_logger
from ..models import LLMResponse
from ..exceptions import LLMProviderError, LLMRateLimitError, LLMAuthenticationError
from .base_provider import BaseProvider

logger = get_logger('jarvis.ai_agent.providers.grok')

XAI_BASE_URL = "https://api.x.ai/v1"


class GrokProvider(BaseProvider):
    """xAI Grok LLM provider (OpenAI-compatible API)."""

    @property
    def name(self) -> str:
        return "grok"

    def _get_client(self, api_key: Optional[str] = None) -> openai.OpenAI:
        """Create OpenAI client pointed at xAI endpoint."""
        key = api_key or os.environ.get('XAI_API_KEY')
        if not key:
            raise LLMAuthenticationError("XAI_API_KEY not found")
        return openai.OpenAI(api_key=key, base_url=XAI_BASE_URL)

    def generate(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """Generate a response using xAI Grok."""
        client = self._get_client(api_key)
        formatted_messages = self.format_messages(messages)

        if 'system' in kwargs:
            formatted_messages.insert(0, {
                'role': 'system',
                'content': kwargs.pop('system'),
            })

        temperature = max(0.0, min(2.0, temperature))

        # Handle tools
        tools = kwargs.pop('tools', None)

        try:
            logger.debug(f"Grok API request: model={model_name}, messages={len(formatted_messages)}, tools={len(tools) if tools else 0}")

            create_kwargs = {
                'model': model_name,
                'messages': formatted_messages,
                'max_tokens': max_tokens,
                'temperature': temperature,
            }
            if tools:
                create_kwargs['tools'] = tools

            response = client.chat.completions.create(**create_kwargs)

            content = ""
            if response.choices:
                content = response.choices[0].message.content or ""

            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            finish_reason = response.choices[0].finish_reason if response.choices else None

            # Parse tool calls if present
            tool_calls = []
            if response.choices and response.choices[0].message.tool_calls:
                for tc in response.choices[0].message.tool_calls:
                    tool_calls.append({
                        'id': tc.id,
                        'name': tc.function.name,
                        'input': json_module.loads(tc.function.arguments),
                    })

            logger.debug(f"Grok API response: tokens_in={input_tokens}, tokens_out={output_tokens}, tool_calls={len(tool_calls)}")

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                finish_reason=finish_reason,
                tool_calls=tool_calls,
            )

        except openai.RateLimitError as e:
            logger.warning(f"Grok rate limit exceeded: {e}")
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except openai.AuthenticationError as e:
            logger.error(f"Grok authentication failed: {e}")
            raise LLMAuthenticationError(f"Authentication failed: {e}")
        except openai.APIError as e:
            logger.error(f"Grok API error: {e}")
            raise LLMProviderError(f"Grok API error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error calling Grok: {e}")
            raise LLMProviderError(f"Failed to call Grok API: {e}")

    def generate_structured(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.3,
        api_key: str | None = None,
        **kwargs,
    ):
        """Generate structured JSON using json_object response_format."""
        import json as json_module

        client = self._get_client(api_key)
        formatted_messages = self.format_messages(messages)
        if 'system' in kwargs:
            formatted_messages.insert(0, {
                'role': 'system',
                'content': kwargs.pop('system'),
            })

        temperature = max(0.0, min(2.0, temperature))

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=formatted_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )

            content = ""
            if response.choices:
                content = response.choices[0].message.content or ""

            return json_module.loads(content)

        except (openai.RateLimitError, openai.AuthenticationError, openai.APIError):
            raise
        except Exception as e:
            logger.warning(f"Grok structured output failed, falling back: {e}")
            return super().generate_structured(
                model_name, messages, max_tokens, temperature, api_key, **kwargs
            )

    def format_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Format messages for xAI API (OpenAI-compatible).

        Passes through tool-related messages unchanged.
        """
        if not messages:
            return []

        formatted = []
        for msg in messages:
            role = msg.get('role', 'user')

            # Pass through tool result messages and assistant tool_call messages
            if role == 'tool' or 'tool_calls' in msg:
                formatted.append(msg)
                continue

            content = msg.get('content', '')

            if role not in ('system', 'user', 'assistant'):
                role = 'user'

            formatted.append({
                'role': role,
                'content': content,
            })

        return formatted

    def generate_stream(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> Generator[Tuple[Optional[str], Optional[LLMResponse]], None, None]:
        """Stream a response from Grok, yielding text chunks."""
        client = self._get_client(api_key)
        formatted_messages = self.format_messages(messages)
        if 'system' in kwargs:
            formatted_messages.insert(0, {
                'role': 'system',
                'content': kwargs.pop('system'),
            })

        temperature = max(0.0, min(2.0, temperature))

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=formatted_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                stream_options={"include_usage": True},
            )

            full_content = ""
            input_tokens = 0
            output_tokens = 0
            finish_reason = None

            for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        full_content += delta.content
                        yield (delta.content, None)
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason

                if chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens or 0
                    output_tokens = chunk.usage.completion_tokens or 0

            yield (None, LLMResponse(
                content=full_content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                finish_reason=finish_reason,
            ))

        except openai.RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except openai.AuthenticationError as e:
            raise LLMAuthenticationError(f"Authentication failed: {e}")
        except openai.APIError as e:
            raise LLMProviderError(f"Grok API error: {e}")
        except Exception as e:
            raise LLMProviderError(f"Failed to stream Grok API: {e}")
