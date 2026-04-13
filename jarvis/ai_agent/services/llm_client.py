"""
Lightweight wrapper over ClaudeProvider for simple text completions.

Use this instead of calling anthropic.Anthropic() directly:
    from ai_agent.services.llm_client import ask, ask_stream, call

    text = ask(prompt, system="You are a helpful assistant.")
    for chunk in ask_stream(prompt): ...
    text = call(messages, model="claude-sonnet-4-6")  # pre-built messages (multimodal, etc.)
"""
from ai_agent.providers.claude_provider import ClaudeProvider

_DEFAULT_MODEL = 'claude-sonnet-4-6'
_provider = ClaudeProvider()


def ask(prompt: str, system: str = '', model: str = _DEFAULT_MODEL,
        max_tokens: int = 4096, api_key: str = None) -> str:
    """Non-streaming text completion. Returns the response text string."""
    response = _provider.generate(
        model_name=model,
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=max_tokens,
        system=system,
        api_key=api_key,
    )
    return response.content


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
    response = _provider.generate(
        model_name=model,
        messages=messages,
        max_tokens=max_tokens,
        api_key=api_key,
    )
    return response.content
