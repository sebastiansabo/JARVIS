"""
Lightweight wrapper over LLM providers for simple text completions.

Use this instead of calling anthropic.Anthropic() directly:
    from ai_agent.services.llm_client import ask, ask_stream, call

    text = ask(prompt, system="You are a helpful assistant.")
    for chunk in ask_stream(prompt): ...
    text = call(messages, model="claude-sonnet-4-6")  # pre-built messages (multimodal, etc.)

Fallback chain: Claude → Grok → OpenAI GPT-4o.
Each provider is tried if the previous one fails and its API key is set.
"""
import os
import logging

from ai_agent.providers.claude_provider import ClaudeProvider

logger = logging.getLogger('jarvis.ai_agent.llm_client')

_DEFAULT_MODEL = 'claude-sonnet-4-6'
_provider = ClaudeProvider()
_fallback_chain = None

# Fallback order: OpenAI (OPENAI_API_KEY) → Grok (XAI_API_KEY)
_FALLBACKS = [
    ('OPENAI_API_KEY', 'ai_agent.providers.openai_provider', 'OpenAIProvider', 'gpt-4o'),
    ('XAI_API_KEY', 'ai_agent.providers.grok_provider', 'GrokProvider', 'grok-3'),
]


def _get_fallback_chain():
    global _fallback_chain
    if _fallback_chain is None:
        _fallback_chain = []
        for env_key, module_path, class_name, model in _FALLBACKS:
            if os.environ.get(env_key):
                try:
                    import importlib
                    mod = importlib.import_module(module_path)
                    provider = getattr(mod, class_name)()
                    _fallback_chain.append((provider, model, class_name))
                except Exception:
                    pass
    return _fallback_chain


def _call_with_fallback(fn_primary, fn_fallback):
    """Try primary, then each fallback in chain."""
    try:
        return fn_primary()
    except Exception as primary_err:
        for provider, model, name in _get_fallback_chain():
            try:
                logger.warning(f"Claude failed ({primary_err}), trying {name} ({model})")
                return fn_fallback(provider, model)
            except Exception as fb_err:
                logger.warning(f"{name} also failed ({fb_err}), trying next")
                continue
        raise primary_err


def ask(prompt: str, system: str = '', model: str = _DEFAULT_MODEL,
        max_tokens: int = 4096, api_key: str = None) -> str:
    """Non-streaming text completion. Returns the response text string."""
    msgs = [{'role': 'user', 'content': prompt}]

    def primary():
        return _provider.generate(
            model_name=model, messages=msgs,
            max_tokens=max_tokens, system=system, api_key=api_key,
        ).content

    def fallback(prov, mod):
        return prov.generate(
            model_name=mod, messages=msgs,
            max_tokens=max_tokens, system=system,
        ).content

    return _call_with_fallback(primary, fallback)


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
    def primary():
        return _provider.generate(
            model_name=model, messages=messages,
            max_tokens=max_tokens, api_key=api_key,
        ).content

    def fallback(prov, mod):
        return prov.generate(
            model_name=mod, messages=messages,
            max_tokens=max_tokens,
        ).content

    return _call_with_fallback(primary, fallback)
