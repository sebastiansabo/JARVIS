"""OpenAIProvider._to_openai_content — Anthropic -> OpenAI content translation.

Pure staticmethod (no DB/HTTP/LLM): translates Anthropic-style content blocks
(used throughout llm_client/ai_agent) into the OpenAI chat format so the
Claude->OpenAI fallback can serve vision requests (e.g. invoice OCR) instead
of 400ing on an 'image' block OpenAI doesn't understand. See the method's own
docstring in ai_agent/providers/openai_provider.py.

GOTCHA: importing ai_agent.providers.openai_provider pulls in ai_agent/__init__
-> ai_agent.routes -> ... -> core.base_repository -> database (which calls
init_db() at import time) -> migrations -> buyback -> core.base_repository
again, while the first import of core.base_repository is still mid-execution.
That's a genuine circular import ("cannot import name 'BaseRepository' from
partially initialized module") that bites ANY test module that is the first
one in a pytest run to touch core.base_repository — it already affects the
neighbouring test_claude_provider_sampling.py in this directory when run
alone, independent of anything added here. It resolves cleanly once some
other test (e.g. the carpark suite, whose conftest.py fully imports
`database`) has already warmed up the import graph. Run this file alongside
another suite, e.g.:
    venv/bin/python -m pytest jarvis/tests/carpark/test_invoice_cost_mapper.py \
        jarvis/tests/ai_agent/test_openai_content_translation.py -v
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from ai_agent.providers.openai_provider import OpenAIProvider

_to_openai_content = OpenAIProvider._to_openai_content


def test_base64_image_becomes_data_url():
    block = {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'X'}}
    out = _to_openai_content([block])
    assert out == [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,X'}}]


def test_url_image_passes_url_through():
    block = {'type': 'image', 'source': {'type': 'url', 'url': 'U'}}
    out = _to_openai_content([block])
    assert out == [{'type': 'image_url', 'image_url': {'url': 'U'}}]


def test_text_block_unchanged():
    block = {'type': 'text', 'text': 'hello'}
    out = _to_openai_content([block])
    assert out == [block]


def test_plain_string_content_unchanged():
    assert _to_openai_content('hello') == 'hello'


def test_mixed_list_translates_only_the_image():
    text_block = {'type': 'text', 'text': 'describe this'}
    image_block = {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': 'Y'}}
    out = _to_openai_content([text_block, image_block])
    assert out == [
        text_block,
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,Y'}},
    ]


def test_base64_image_defaults_media_type_to_png_when_missing():
    block = {'type': 'image', 'source': {'type': 'base64', 'data': 'Z'}}
    out = _to_openai_content([block])
    assert out == [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,Z'}}]
