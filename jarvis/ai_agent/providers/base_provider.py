"""
Base Provider

Abstract base class for LLM providers.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator, Tuple

from ..models import LLMResponse

logger = logging.getLogger('jarvis.ai_agent.providers.base')


class BaseProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'claude', 'openai')."""
        pass

    @abstractmethod
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
        Generate a response from the LLM.

        Args:
            model_name: Model identifier (e.g., 'claude-sonnet-4-20250514')
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            api_key: API key (optional, falls back to environment)
            **kwargs: Provider-specific options

        Returns:
            LLMResponse with content and token counts
        """
        pass

    @abstractmethod
    def generate_stream(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> Generator[Tuple[Optional[str], Optional[LLMResponse]], None, None]:
        """
        Stream a response from the LLM.

        Yields (text_chunk, None) for each token, then (None, LLMResponse) at end.

        Args:
            model_name: Model identifier
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            api_key: API key (optional, falls back to environment)
            **kwargs: Provider-specific options

        Yields:
            Tuples of (text_chunk, None) during streaming,
            then (None, LLMResponse) as the final item with token counts
        """
        pass

    def format_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        Format messages for this provider.

        Default implementation returns messages as-is.
        Override for provider-specific formatting.

        Args:
            messages: List of message dicts

        Returns:
            Formatted messages
        """
        return messages

    def extract_system_message(
        self,
        messages: List[Dict[str, str]],
    ) -> tuple[Optional[str], List[Dict[str, str]]]:
        """
        Extract system message from messages list.

        Some providers (like Anthropic) require system message
        to be passed separately.

        Args:
            messages: List of message dicts

        Returns:
            Tuple of (system_content, remaining_messages)
        """
        system_content = None
        remaining = []

        for msg in messages:
            if msg.get('role') == 'system':
                system_content = msg.get('content', '')
            else:
                remaining.append(msg)

        return system_content, remaining

    def generate_structured(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Generate a structured JSON response from the LLM.

        Default implementation calls generate() and extracts JSON from the
        response text. Providers can override to use native structured output
        (e.g., Claude tool_use, OpenAI json_schema, Gemini response_mime_type).

        Args:
            model_name: Model identifier
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (lower default for structured)
            api_key: API key (optional)
            **kwargs: Provider-specific options

        Returns:
            Parsed JSON (list or dict)

        Raises:
            ValueError: If response cannot be parsed as JSON
        """
        response = self.generate(
            model_name=model_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            api_key=api_key,
            **kwargs,
        )
        return self._extract_json(response.content)

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Extract JSON from LLM text that may contain markdown fences.

        Handles common patterns:
        - Raw JSON
        - ```json ... ```
        - ``` ... ```
        - Text before/after JSON

        Returns:
            Parsed JSON object (list or dict)

        Raises:
            ValueError: If no valid JSON found
        """
        text = text.strip()

        # Try raw parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences
        if '```' in text:
            parts = text.split('```')
            for part in parts[1::2]:  # odd-indexed parts are inside fences
                content = part.strip()
                if content.startswith('json'):
                    content = content[4:].strip()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    continue

        # Try to find JSON array or object in the text
        for start_char, end_char in [('[', ']'), ('{', '}')]:
            start = text.find(start_char)
            if start == -1:
                continue
            end = text.rfind(end_char)
            if end <= start:
                continue
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue

        raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}")
