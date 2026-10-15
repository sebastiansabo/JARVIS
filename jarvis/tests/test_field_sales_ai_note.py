"""Field Sales AI visit-note structuring — model + language behavior.

The note structurer runs on Opus 4.8 and must force ALL extracted text VALUES
into English (translate summary / next_steps / objections / commitments /
risk_flags; keep proper nouns), rather than the older "field names in English"
instruction that left values in the source language. The pre-visit brief is out
of scope — it keeps its existing "Write in English" instruction unchanged.

DB-free: the top-level conftest mocks psycopg2; ask() is faked.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import json

import field_sales.services.ai_service as ai


def test_model_is_opus_4_8():
    assert ai._MODEL == 'claude-opus-4-8'


def test_module_docstring_names_current_model():
    doc = (ai.__doc__ or '').lower()
    assert 'claude-sonnet-4-6' not in doc
    assert 'claude-opus-4-8' in doc


def test_structure_visit_note_uses_opus_and_english_values(monkeypatch):
    captured = {}

    def fake_ask(prompt, system='', model=None, max_tokens=None, api_key=None):
        captured['system'] = system
        captured['model'] = model
        captured['max_tokens'] = max_tokens
        return json.dumps({'visit_summary': 'Client wants a new SUV',
                           'sentiment': 'positive'})

    monkeypatch.setattr(ai, '_AI_AVAILABLE', True)
    monkeypatch.setattr(ai, 'ask', fake_ask)

    result = ai.structure_visit_note('clientul vrea un SUV nou')

    # model switched to Opus 4.8; max_tokens unchanged (safe thinking-off)
    assert captured['model'] == 'claude-opus-4-8'
    assert captured['max_tokens'] == 2000

    sys_lower = captured['system'].lower()
    # old field-names-only instruction removed
    assert 'always output field names in english' not in sys_lower
    # new instruction forces VALUES into English and preserves proper nouns
    assert 'translate' in sys_lower
    assert 'english' in sys_lower
    assert 'proper noun' in sys_lower

    # behavior preserved: valid JSON still parsed + normalized
    assert result['visit_summary'] == 'Client wants a new SUV'
    assert result['sentiment'] == 'positive'


def test_visit_brief_prompt_out_of_scope(monkeypatch):
    """The value-translation instruction is note-only; the brief keeps its
    existing 'Write in English' line and does not get the 'translate' directive."""
    captured = {}

    def fake_ask(prompt, system='', model=None, max_tokens=None, api_key=None):
        captured['system'] = system
        captured['model'] = model
        return 'BRIEF'

    monkeypatch.setattr(ai, '_AI_AVAILABLE', True)
    monkeypatch.setattr(ai, 'ask', fake_ask)

    out = ai.generate_visit_brief({'profile': {'display_name': 'ACME'}})

    assert out == 'BRIEF'
    assert captured['model'] == 'claude-opus-4-8'
    sys_lower = captured['system'].lower()
    assert 'write in english' in sys_lower          # existing brief instruction preserved
    assert 'translate' not in sys_lower             # note-only directive did not leak in
