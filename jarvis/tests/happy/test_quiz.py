"""Unit tests for quiz comprehension grading (spec §5.4)."""
from happy.services.quiz import grade_quiz

Q = [
    {"id": 1, "position": 1, "correct_index": 2},
    {"id": 2, "position": 2, "correct_index": 0},
]


def test_all_correct_no_reveal():
    r = grade_quiz(Q, {1: 2, 2: 0})
    assert r["all_correct"] is True
    assert all(x["correct"] for x in r["results"])
    assert all(x["correct_index"] is None for x in r["results"])  # correct → never revealed


def test_one_wrong_reveals_only_that_answer():
    r = grade_quiz(Q, {1: 0, 2: 0})
    assert r["all_correct"] is False
    by_pos = {x["position"]: x for x in r["results"]}
    assert by_pos[1]["correct"] is False and by_pos[1]["correct_index"] == 2   # revealed
    assert by_pos[2]["correct"] is True and by_pos[2]["correct_index"] is None


def test_missing_answer_is_wrong():
    r = grade_quiz(Q, {1: 2})   # q2 unanswered
    by_pos = {x["position"]: x for x in grade_quiz(Q, {1: 2}).get("results", [])}
    assert r["all_correct"] is False
    assert by_pos[2]["correct"] is False and by_pos[2]["correct_index"] == 0


def test_string_keyed_answers_are_tolerated():
    assert grade_quiz(Q, {"1": 2, "2": 0})["all_correct"] is True


def test_partial_correct_reveals_only_wrong():
    r = grade_quiz(Q, {1: 2, 2: 1})
    by_pos = {x["position"]: x for x in r["results"]}
    assert by_pos[1]["correct_index"] is None   # correct → not revealed
    assert by_pos[2]["correct_index"] == 0       # wrong → revealed
