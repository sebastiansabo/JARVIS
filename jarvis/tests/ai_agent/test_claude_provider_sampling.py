"""ClaudeProvider sampling-parameter gating.

Claude Opus 4.7+ / Sonnet 5 / Fable 5 / Mythos 5 return HTTP 400 if any of
``temperature`` / ``top_p`` / ``top_k`` is sent. The provider historically
hardcoded ``temperature`` into every request, so those models could not be
used through llm_client. These tests pin the gate: ``temperature`` must be
OMITTED from the Anthropic payload for the rejecting families and PRESENT for
backward-compatible ones (Sonnet 4.6 and older).

DB-free: the top-level conftest mocks psycopg2; the Anthropic client is faked.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from types import SimpleNamespace

import anthropic

from ai_agent.providers.claude_provider import ClaudeProvider

_MSGS = [{'role': 'user', 'content': 'hi'}]


def _text_response():
    return SimpleNamespace(
        content=[SimpleNamespace(type='text', text='hello')],
        usage=SimpleNamespace(input_tokens=5, output_tokens=3),
        stop_reason='end_turn',
    )


def _tool_use_response():
    return SimpleNamespace(
        content=[SimpleNamespace(type='tool_use', id='t1',
                                 name='structured_output', input={'ok': True})],
        usage=SimpleNamespace(input_tokens=5, output_tokens=3),
        stop_reason='tool_use',
    )


class _FakeStream:
    def __init__(self):
        self.text_stream = iter(['hello'])

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def get_final_message(self):
        return _text_response()


def _install(monkeypatch, response=None):
    """Patch anthropic.Anthropic with a fake client; return a dict capturing
    the kwargs passed to messages.create / messages.stream."""
    captured = {}

    class _Msgs:
        def create(self, **kwargs):
            captured['create'] = kwargs
            return response

        def stream(self, **kwargs):
            captured['stream'] = kwargs
            return _FakeStream()

    class _Client:
        def __init__(self, *_a, **_k):
            self.messages = _Msgs()

    monkeypatch.setattr(anthropic, 'Anthropic', _Client)
    return captured


# ── the gate helper ──────────────────────────────────────────

def test_model_rejects_sampling_for_new_families():
    from ai_agent.providers.claude_provider import _model_rejects_sampling
    for m in ('claude-opus-4-8', 'claude-opus-4-7', 'claude-sonnet-5',
              'claude-fable-5', 'claude-mythos-5'):
        assert _model_rejects_sampling(m) is True, m


def test_model_allows_sampling_for_legacy_families():
    from ai_agent.providers.claude_provider import _model_rejects_sampling
    for m in ('claude-sonnet-4-6', 'claude-opus-4-6', 'claude-opus-4-5',
              'claude-sonnet-4-5', 'claude-haiku-4-5', 'gpt-4o', '', None):
        assert _model_rejects_sampling(m) is False, m


# ── generate() ───────────────────────────────────────────────

def test_generate_omits_temperature_for_opus_4_8(monkeypatch):
    captured = _install(monkeypatch, response=_text_response())
    ClaudeProvider().generate('claude-opus-4-8', _MSGS, api_key='sk-test')
    assert 'temperature' not in captured['create']


def test_generate_includes_temperature_for_sonnet_4_6(monkeypatch):
    captured = _install(monkeypatch, response=_text_response())
    ClaudeProvider().generate('claude-sonnet-4-6', _MSGS, api_key='sk-test')
    assert 'temperature' in captured['create']


# ── generate_structured() ────────────────────────────────────

def test_generate_structured_omits_temperature_for_opus_4_8(monkeypatch):
    captured = _install(monkeypatch, response=_tool_use_response())
    ClaudeProvider().generate_structured('claude-opus-4-8', _MSGS, api_key='sk-test')
    assert 'temperature' not in captured['create']


def test_generate_structured_includes_temperature_for_sonnet_4_6(monkeypatch):
    captured = _install(monkeypatch, response=_tool_use_response())
    ClaudeProvider().generate_structured('claude-sonnet-4-6', _MSGS, api_key='sk-test')
    assert 'temperature' in captured['create']


# ── generate_stream() ────────────────────────────────────────

def test_generate_stream_omits_temperature_for_opus_4_8(monkeypatch):
    captured = _install(monkeypatch)
    list(ClaudeProvider().generate_stream('claude-opus-4-8', _MSGS, api_key='sk-test'))
    assert 'temperature' not in captured['stream']


def test_generate_stream_includes_temperature_for_sonnet_4_6(monkeypatch):
    captured = _install(monkeypatch)
    list(ClaudeProvider().generate_stream('claude-sonnet-4-6', _MSGS, api_key='sk-test'))
    assert 'temperature' in captured['stream']
