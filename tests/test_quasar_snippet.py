"""Tests for critical-value preservation in RAG snippets.

Motivated by the snippet-loss finding (scripts/quasar_snippet_report.py):
on staging, the 300-char _create_snippet cut silently dropped real IBANs from
10 bank_statement/transaction docs and 341 VINs from car dossiers. These tests
pin the fix: high-criticality values past the cutoff must be preserved.

Pure/dependency-free — loads quasar_patterns by path, no DB, no torch.
"""
import os
import importlib.util

_p = os.path.join(os.path.dirname(__file__), "..", "jarvis", "ai_agent",
                  "services", "quasar_patterns.py")
_spec = importlib.util.spec_from_file_location("quasar_patterns", _p)
qp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qp)


def test_dropped_critical_values_finds_iban_past_cutoff():
    filler = "Plata efectuata catre furnizor pentru servicii prestate. " * 6
    content = filler + " IBAN: RO86BACX0000002700704003"
    assert len(content) > 300
    dropped = qp.dropped_critical_values(content, content[:300])
    assert "RO86BACX0000002700704003" in dropped


def test_dropped_critical_values_finds_vin_past_cutoff():
    content = ("Dosar auto marca Audi, culoare gri, an fabricatie 2011. " * 8) \
        + " Serie sasiu WAUZZZ8E66A142936"
    dropped = qp.dropped_critical_values(content, content[:300])
    assert "WAUZZZ8E66A142936" in dropped


def test_generic_longid_is_not_preserved():
    # A bare 6-digit id is 'long_id' (generic) — must NOT be force-preserved,
    # or we'd bloat car_dossier snippets with 25k internal ids.
    content = ("x" * 310) + " 12560020"
    assert qp.dropped_critical_values(content, content[:300]) == []


def test_value_already_visible_is_not_duplicated():
    content = "IBAN RO86BACX0000002700704003 " + ("y" * 400)
    assert qp.dropped_critical_values(content, content[:300]) == []
