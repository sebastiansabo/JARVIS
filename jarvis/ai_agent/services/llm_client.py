"""
Lightweight wrapper over LLM providers for simple text completions.

Use this instead of calling anthropic.Anthropic() directly:
    from ai_agent.services.llm_client import ask, ask_stream, call

    text = ask(prompt, system="You are a helpful assistant.")
    for chunk in ask_stream(prompt): ...
    text = call(messages, model="claude-sonnet-4-6")  # pre-built messages (multimodal, etc.)

Fallback: if Claude fails (model unavailable, auth error, etc.), automatically
retries with OpenAI GPT-4o if OPENAI_API_KEY is set.
"""
import os
import logging

from ai_agent.providers.claude_provider import ClaudeProvider

logger = logging.getLogger('jarvis.ai_agent.llm_client')

_DEFAULT_MODEL = 'claude-sonnet-4-6'
_FALLBACK_MODEL = 'gpt-4o'
_provider = ClaudeProvider()
_fallback_provider = None


def _get_fallback():
    global _fallback_provider
    if _fallback_provider is None:
        if os.environ.get('OPENAI_API_KEY'):
            from ai_agent.providers.openai_provider import OpenAIProvider
            _fallback_provider = OpenAIProvider()
    return _fallback_provider


def ask(prompt: str, system: str = '', model: str = _DEFAULT_MODEL,
        max_tokens: int = 4096, api_key: str = None) -> str:
    """Non-streaming text completion. Returns the response text string."""
    try:
        response = _provider.generate(
            model_name=model,
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=max_tokens,
            system=system,
            api_key=api_key,
        )
        return response.content
    except Exception as e:
        fallback = _get_fallback()
        if fallback:
            logger.warning(f"Claude failed ({e}), falling back to OpenAI {_FALLBACK_MODEL}")
            messages = [{'role': 'user', 'content': prompt}]
            response = fallback.generate(
                model_name=_FALLBACK_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                system=system,
            )
            return response.content
        raise


def ask_stream(prompt: str, system: str = '', model: str = _DEFAULT_MODEL,
               max_tokens: int = 4096, api_key: str = None):
    """Streaming completion. Yields text chunks (str)."""
    for chunk, _final in _provider.generate_stream(
        model_name=model,
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=max_tokens,
        system=system,
        api_key=api_key,
    ):
        if chunk is not None:
            yield chunk


def call(messages: list, model: str = _DEFAULT_MODEL, max_tokens: int = 4096,
         api_key: str = None) -> str:
    """Full-messages call accepting a pre-built messages list (supports multimodal content).
    Returns the response text string."""
    try:
        response = _provider.generate(
            model_name=model,
            messages=messages,
            max_tokens=max_tokens,
            api_key=api_key,
        )
        return response.content
    except Exception as e:
        fallback = _get_fallback()
        if fallback:
            logger.warning(f"Claude failed ({e}), falling back to OpenAI {_FALLBACK_MODEL}")
            response = fallback.generate(
                model_name=_FALLBACK_MODEL,
                messages=messages,
                max_tokens=max_tokens,
            )
            return response.content
        raise
