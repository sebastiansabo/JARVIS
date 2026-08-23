"""Unit tests for praise anti-gaming pure helpers (spec §7.4 rule 4)."""
from happy.services.praise_rules import text_similarity, is_duplicate_note

NOTE = "Mulțumesc pentru ajutorul real la livrarea proiectului"  # >= 40 chars


def test_identical_text_similarity_is_one():
    assert text_similarity(NOTE, NOTE) == 1.0


def test_disjoint_text_similarity_is_low():
    assert text_similarity("aaaaaaaaaa", "zzzzzzzzzz") < 0.3


def test_case_and_whitespace_insensitive():
    assert text_similarity(NOTE, "  " + NOTE.upper() + "  ") == 1.0


def test_identical_note_is_duplicate():
    assert is_duplicate_note(NOTE, ["something else entirely here padding", NOTE]) is True


def test_near_identical_note_is_duplicate():
    # a single-word change in a long note stays > 0.9
    assert is_duplicate_note(NOTE + " azi", [NOTE + " ieri"]) is True


def test_distinct_note_is_not_duplicate():
    assert is_duplicate_note(NOTE, ["cu totul alt mesaj despre altceva complet diferit"]) is False


def test_empty_history_is_not_duplicate():
    assert is_duplicate_note(NOTE, []) is False
