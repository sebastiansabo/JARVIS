"""
Base Provider

Abstract base class for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from ..models import LLMResponse


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
