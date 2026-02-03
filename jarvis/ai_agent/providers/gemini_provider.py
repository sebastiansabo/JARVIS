"""
Gemini Provider

Google Gemini LLM provider implementation.
"""

import os
from typing import List, Dict, Any, Optional

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

        try:
            # Create model with system instruction if provided
            generation_config = {
                'temperature': temperature,
                'max_output_tokens': max_tokens,
            }

            model_kwargs = {'model_name': model_name}
            if system_instruction:
                model_kwargs['system_instruction'] = system_instruction

            model = genai.GenerativeModel(**model_kwargs)

            logger.debug(f"Gemini API request: model={model_name}, messages={len(formatted_messages)}")

            # Start chat and send messages
            chat = model.start_chat(history=formatted_messages[:-1] if len(formatted_messages) > 1 else [])

            # Send the last message
            last_message = formatted_messages[-1]['parts'][0] if formatted_messages else ""
            response = chat.send_message(last_message, generation_config=generation_config)

            # Extract content
            content = response.text if response.text else ""

            # Estimate token counts (Gemini doesn't always provide exact counts)
            input_tokens = sum(len(m.get('parts', [''])[0]) // 4 for m in formatted_messages)
            output_tokens = len(content) // 4

            # Try to get actual token counts if available
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = getattr(response.usage_metadata, 'prompt_token_count', input_tokens)
                output_tokens = getattr(response.usage_metadata, 'candidates_token_count', output_tokens)

            logger.debug(f"Gemini API response: tokens_in={input_tokens}, tokens_out={output_tokens}")

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                finish_reason='stop',
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

    def _format_for_gemini(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """
        Format messages for Gemini API.

        Gemini uses 'user' and 'model' roles with 'parts' content.

        Args:
            messages: List of message dicts

        Returns:
            Formatted messages for Gemini
        """
        if not messages:
            return []

        formatted = []
        for msg in messages:
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

    def format_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        Format messages (standard interface).

        Args:
            messages: List of message dicts

        Returns:
            Formatted messages
        """
        return messages
