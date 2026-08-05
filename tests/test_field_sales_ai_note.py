import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

import json

from field_sales.services import ai_service
from field_sales.services.ai_service import _normalize_structured_note, _coerce_number

CANONICAL_KEYS = {
    'visit_summary', 'sentiment', 'contact_person', 'vehicles_discussed',
    'commitments_made', 'next_steps', 'opportunity_value_eur',
    'decision_timeline', 'follow_up_date', 'objections', 'risk_flags',
}


def test_normalizer_coerces_offshape_to_canonical():
    raw = {
        'visit_summary': 'Rezumat',
        'sentiment': 'wat',                       # invalid -> None
        'next_steps': 'do a thing',               # string -> []
        'commitments_made': None,                 # None -> []
        'vehicles_discussed': [{'action': 'buy', 'budget_eur': '20000'}],
        'opportunity_value_eur': 'nope',          # non-numeric -> None
        'stray_key': 'dropped',
    }
    out = _normalize_structured_note(raw)
    assert set(out) == CANONICAL_KEYS
    assert out['sentiment'] is None
    assert out['next_steps'] == []
    assert out['commitments_made'] == []
    assert out['vehicles_discussed'][0]['budget_eur'] == 20000
    assert out['vehicles_discussed'][0]['current_vehicle'] is None
    assert out['opportunity_value_eur'] is None
    assert 'stray_key' not in out


def test_normalizer_passes_error_marker_through():
    err = {'error': 'parse_failed', 'raw': 'x'}
    assert _normalize_structured_note(err) == err


def test_normalizer_preserves_valid_canonical():
    raw = {
        'visit_summary': 'S', 'sentiment': 'positive', 'contact_person': 'Ana',
        'vehicles_discussed': [{'action': 'replace', 'current_vehicle': 'A4', 'interested_in': 'A6', 'budget_eur': 45000}],
        'commitments_made': ['send offer'],
        'next_steps': [{'action': 'call', 'owner': 'kam', 'deadline': '2026-08-10'}],
        'opportunity_value_eur': 45000, 'decision_timeline': 'Q3',
        'follow_up_date': '2026-08-10', 'objections': ['price'], 'risk_flags': ['competitor'],
    }
    assert _normalize_structured_note(raw) == raw


def test_normalizer_non_dict_returns_error():
    out = _normalize_structured_note('garbage')
    assert out.get('error') == 'parse_failed'


def test_normalizer_guards_offshape_scalar_strings():
    # If the LLM emits an object/list where a string is expected, the
    # normalizer must degrade it to '' / None rather than passing the
    # object/list through -- otherwise it reaches the frontend and rendering
    # a non-string as a React child throws ("Objects are not valid as a React
    # child"), blanking the review card.
    raw = {
        'visit_summary': {'nested': 'object'},
        'contact_person': ['a', 'list'],
        'decision_timeline': {'not': 'a string'},
        'follow_up_date': 123,
        'next_steps': [{'action': {'weird': 'object'}, 'owner': 'kam', 'deadline': '2026-08-10'}],
        'vehicles_discussed': [{'action': 'buy', 'current_vehicle': ['x'], 'interested_in': {'y': 1}, 'budget_eur': 1000}],
    }
    out = _normalize_structured_note(raw)
    assert out['visit_summary'] == ''
    assert out['contact_person'] is None
    assert out['decision_timeline'] is None
    assert out['follow_up_date'] is None
    assert out['next_steps'][0]['action'] is None
    assert out['next_steps'][0]['owner'] == 'kam'
    assert out['vehicles_discussed'][0]['current_vehicle'] is None
    assert out['vehicles_discussed'][0]['interested_in'] is None


def test_coerce_number_rejects_non_finite():
    # Non-finite values (from untrusted LLM output) must coerce to None so they
    # never reach json.dumps as the invalid-JSON tokens NaN/Infinity.
    assert _coerce_number('nan') is None
    assert _coerce_number('inf') is None
    assert _coerce_number('-inf') is None
    assert _coerce_number('Infinity') is None
    assert _coerce_number(float('inf')) is None
    assert _coerce_number(float('-inf')) is None
    assert _coerce_number(float('nan')) is None
    # Genuine finite numbers still pass through unchanged.
    assert _coerce_number(20000) == 20000
    assert _coerce_number('20000') == 20000
    # Bools still map to None.
    assert _coerce_number(True) is None


def test_normalizer_maps_non_finite_to_none():
    raw = {
        'opportunity_value_eur': 'inf',
        'vehicles_discussed': [{'action': 'buy', 'budget_eur': 'nan'}],
    }
    out = _normalize_structured_note(raw)
    assert out['opportunity_value_eur'] is None
    assert out['vehicles_discussed'][0]['budget_eur'] is None


def test_coerce_number_handles_huge_int_without_raising():
    # json.loads yields arbitrary-precision ints; one too large for a C double
    # must map to None (never raise) — _normalize_structured_note is
    # documented to NEVER raise.
    assert _coerce_number(10 ** 400) is None
    out = _normalize_structured_note({'opportunity_value_eur': 10 ** 400})
    assert out['opportunity_value_eur'] is None


def _patch_ask(monkeypatch, response):
    captured = {}

    def fake_ask(user_message, system=None, model=None, max_tokens=None):
        captured['system'] = system
        captured['user'] = user_message
        return response

    monkeypatch.setattr(ai_service, '_AI_AVAILABLE', True)
    monkeypatch.setattr(ai_service, 'ask', fake_ask)
    return captured


def test_prompt_declares_every_canonical_key(monkeypatch):
    captured = _patch_ask(monkeypatch, json.dumps({'visit_summary': 'ok'}))
    ai_service.structure_visit_note('some note')
    for key in CANONICAL_KEYS:
        assert key in captured['system'], f'prompt missing {key}'
    # dropped legacy fields must not reappear in the schema block
    assert 'deal_probability' not in captured['system']
    assert 'vehicles_of_interest' not in captured['system']


def test_structure_visit_note_normalizes_fenced_ai_output(monkeypatch):
    payload = {'visit_summary': 'S', 'sentiment': 'positive', 'next_steps': 'bad', 'stray': 1}
    _patch_ask(monkeypatch, '```json\n' + json.dumps(payload) + '\n```')
    out = ai_service.structure_visit_note('note')
    assert set(out) == CANONICAL_KEYS       # stray dropped, keys filled
    assert out['visit_summary'] == 'S'
    assert out['sentiment'] == 'positive'
    assert out['next_steps'] == []          # string coerced away
