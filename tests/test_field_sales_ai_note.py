import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

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
