"""
Gemini Provider

Google Gemini LLM provider implementation.
"""

import json as json_module
import os
from typing import List, Dict, Any, Optional, Generator, Tuple

from core.utils.logging_config import get_logger
from ..models import LLMResponse
from ..exceptions import LLMProviderError, LLMRateLimitError, LLMAuthenticationError
from .base_provider import BaseProvider

logger = get_logger('jarvis.ai_agent.providers.gemini')


class GeminiProvider(BaseProvider):
    """Google Gemini LLM provider."""

    @property
    def name(self) -> str:
        return "gemini"

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
        Generate a response using Google Gemini.

        Args:
            model_name: Gemini model identifier (e.g., 'gemini-pro')
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-1.0 for Gemini)
            api_key: API key (optional, falls back to GOOGLE_AI_API_KEY env)
            **kwargs: Additional options (system prompt, etc.)

        Returns:
            LLMResponse with content and token counts

        Raises:
            LLMProviderError: If API call fails
            LLMRateLimitError: If rate limited
            LLMAuthenticationError: If API key invalid
        """
        try:
            import google.generativeai as genai
        except ImportError:
            raise LLMProviderError("google-generativeai package not installed. Run: pip install google-generativeai")

        # Get API key
        key = api_key or os.environ.get('GOOGLE_AI_API_KEY')
        if not key:
            raise LLMAuthenticationError("GOOGLE_AI_API_KEY not found")

        # Configure the API
        genai.configure(api_key=key)

        # Extract system instruction if provided
        system_instruction = kwargs.pop('system', None)

        # Format messages for Gemini
        formatted_messages = self._format_for_gemini(messages)

        # Clamp temperature to Gemini's range (0.0-1.0)
        temperature = max(0.0, min(1.0, temperature))

        # Handle tools
        tools = kwargs.pop('tools', None)

        try:
            generation_config = {
                'temperature': temperature,
                'max_output_tokens': max_tokens,
            }

            model_kwargs = {'model_name': model_name}
            if system_instruction:
                model_kwargs['system_instruction'] = system_instruction
            if tools:
                model_kwargs['tools'] = tools

            model = genai.GenerativeModel(**model_kwargs)

            logger.debug(f"Gemini API request: model={model_name}, messages={len(formatted_messages)}, tools={len(tools[0]['function_declarations']) if tools else 0}")

            # Use generate_content for full history support (needed for tool loops)
            response = model.generate_content(
                contents=formatted_messages,
                generation_config=generation_config,
            )

            # Extract content and tool calls
            content = ""
            tool_calls = []

            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if part.text:
                        content += part.text
                    elif part.function_call.name:
                        tool_calls.append({
                            'id': f'gemini_{part.function_call.name}_{len(tool_calls)}',
                            'name': part.function_call.name,
                            'input': dict(part.function_call.args) if part.function_call.args else {},
                        })

            # Estimate token counts
            input_tokens = self._estimate_input_tokens(formatted_messages)
            output_tokens = len(content) // 4

            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = getattr(response.usage_metadata, 'prompt_token_count', input_tokens)
                output_tokens = getattr(response.usage_metadata, 'candidates_token_count', output_tokens)

            logger.debug(f"Gemini API response: tokens_in={input_tokens}, tokens_out={output_tokens}, tool_calls={len(tool_calls)}")

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                finish_reason='tool_use' if tool_calls else 'stop',
                tool_calls=tool_calls,
            )

        except Exception as e:
            error_str = str(e).lower()
            if 'quota' in error_str or 'rate' in error_str:
                logger.warning(f"Gemini rate limit exceeded: {e}")
                raise LLMRateLimitError(f"Rate limit exceeded: {e}")
            elif 'api key' in error_str or 'auth' in error_str:
                logger.error(f"Gemini authentication failed: {e}")
                raise LLMAuthenticationError(f"Authentication failed: {e}")
            else:
                logger.error(f"Gemini API error: {e}")
                raise LLMProviderError(f"Gemini API error: {e}")

    def generate_structured(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.3,
        api_key: str | None = None,
        **kwargs,
    ):
        """Generate structured JSON using Gemini's response_mime_type."""
        import json as json_module

        try:
            import google.generativeai as genai
        except ImportError:
            raise LLMProviderError("google-generativeai package not installed")

        key = api_key or os.environ.get('GOOGLE_AI_API_KEY')
        if not key:
            raise LLMAuthenticationError("GOOGLE_AI_API_KEY not found")

        genai.configure(api_key=key)

        system_instruction = kwargs.pop('system', None)
        formatted_messages = self._format_for_gemini(messages)
        temperature = max(0.0, min(1.0, temperature))

        try:
            generation_config = {
                'temperature': temperature,
                'max_output_tokens': max_tokens,
                'response_mime_type': 'application/json',
            }

            model_kwargs = {'model_name': model_name}
            if system_instruction:
                model_kwargs['system_instruction'] = system_instruction

            model = genai.GenerativeModel(**model_kwargs)
            chat = model.start_chat(history=formatted_messages[:-1] if len(formatted_messages) > 1 else [])
            last_message = formatted_messages[-1]['parts'][0] if formatted_messages else ""
            response = chat.send_message(last_message, generation_config=generation_config)

            return json_module.loads(response.text)

        except Exception as e:
            error_str = str(e).lower()
            if 'quota' in error_str or 'rate' in error_str:
                raise LLMRateLimitError(f"Rate limit exceeded: {e}")
            elif 'api key' in error_str or 'auth' in error_str:
                raise LLMAuthenticationError(f"Authentication failed: {e}")
            logger.warning(f"Gemini structured output failed, falling back: {e}")
            return super().generate_structured(
                model_name, messages, max_tokens, temperature, api_key, **kwargs
            )

    def _format_for_gemini(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Format messages for Gemini API.

        Gemini uses 'user' and 'model' roles with 'parts' content.
        Messages that already have 'parts' (e.g. tool call/result messages)
        are passed through with only role normalization.
        """
        if not messages:
            return []

        formatted = []
        for msg in messages:
            # Pass through messages already in Gemini format (tool messages)
            if 'parts' in msg:
                formatted.append(msg)
                continue

            role = msg.get('role', 'user')
            content = msg.get('content', '')

            # Skip system messages (handled separately)
            if role == 'system':
                continue

            # Map roles: assistant -> model
            gemini_role = 'model' if role == 'assistant' else 'user'

            formatted.append({
                'role': gemini_role,
                'parts': [content],
            })

        # Ensure conversation starts with user
        if formatted and formatted[0]['role'] != 'user':
            formatted.insert(0, {
                'role': 'user',
                'parts': ['[Conversation context]'],
            })

        return formatted

    @staticmethod
    def _estimate_input_tokens(formatted_messages: list) -> int:
        """Estimate input tokens from Gemini-formatted messages."""
        total_chars = 0
        for m in formatted_messages:
            for p in m.get('parts', []):
                if isinstance(p, str):
                    total_chars += len(p)
                else:
                    total_chars += len(str(p))
        return max(1, total_chars // 4)

    def format_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Format messages (standard interface)."""
        return messages

    # ── Tool-calling helpers (Gemini format) ────────────────

    def format_tool_schemas(self, schemas):
        """Convert to Gemini function_declarations format."""
        declarations = []
        for s in schemas:
            declarations.append({
                'name': s['name'],
                'description': s['description'],
                'parameters': s['input_schema'],
            })
        return [{'function_declarations': declarations}]

    def build_tool_call_message(self, llm_response):
        """Gemini format: model message with function_call parts."""
        parts = []
        if llm_response.content:
            parts.append({'text': llm_response.content})
        for tc in llm_response.tool_calls:
            parts.append({
                'function_call': {
                    'name': tc['name'],
                    'args': tc['input'],
                }
            })
        return {'role': 'model', 'parts': parts}

    def build_tool_result_messages(self, tool_results):
        """Gemini format: single user message with function_response parts."""
        parts = []
        for tr in tool_results:
            response_data = tr['content']
            if isinstance(response_data, str):
                try:
                    response_data = json_module.loads(response_data)
                except (json_module.JSONDecodeError, ValueError):
                    response_data = {'result': response_data}
            parts.append({
                'function_response': {
                    'name': tr['name'],
                    'response': response_data,
                }
            })
        return [{'role': 'user', 'parts': parts}]

    def generate_stream(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> Generator[Tuple[Optional[str], Optional[LLMResponse]], None, None]:
        """Stream a response from Gemini, yielding text chunks."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise LLMProviderError("google-generativeai package not installed")

        key = api_key or os.environ.get('GOOGLE_AI_API_KEY')
        if not key:
            raise LLMAuthenticationError("GOOGLE_AI_API_KEY not found")

        genai.configure(api_key=key)

        system_instruction = kwargs.pop('system', None)
        formatted_messages = self._format_for_gemini(messages)
        temperature = max(0.0, min(1.0, temperature))

        try:
            generation_config = {
                'temperature': temperature,
                'max_output_tokens': max_tokens,
            }

            model_kwargs = {'model_name': model_name}
            if system_instruction:
                model_kwargs['system_instruction'] = system_instruction

            model = genai.GenerativeModel(**model_kwargs)

            chat = model.start_chat(history=formatted_messages[:-1] if len(formatted_messages) > 1 else [])
            last_message = formatted_messages[-1]['parts'][0] if formatted_messages else ""

            response = chat.send_message(last_message, generation_config=generation_config, stream=True)

            full_content = ""
            for chunk in response:
                if chunk.text:
                    full_content += chunk.text
                    yield (chunk.text, None)

            # Estimate token counts
            input_tokens = self._estimate_input_tokens(formatted_messages)
            output_tokens = len(full_content) // 4

            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = getattr(response.usage_metadata, 'prompt_token_count', input_tokens)
                output_tokens = getattr(response.usage_metadata, 'candidates_token_count', output_tokens)

            yield (None, LLMResponse(
                content=full_content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                finish_reason='stop',
            ))

        except Exception as e:
            error_str = str(e).lower()
            if 'quota' in error_str or 'rate' in error_str:
                raise LLMRateLimitError(f"Rate limit exceeded: {e}")
            elif 'api key' in error_str or 'auth' in error_str:
                raise LLMAuthenticationError(f"Authentication failed: {e}")
            else:
                raise LLMProviderError(f"Gemini streaming error: {e}")
