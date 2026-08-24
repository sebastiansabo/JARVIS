"""Quiz comprehension grading (spec §5.4). Pure and unit-testable.

Ack is recorded only when every question is correct. A wrong answer reveals the
correct option for THAT question only (so the client can force re-selection); a
correct question never leaks its answer. No score is returned to the user, and no
per-person answer is ever persisted — only aggregate stats (§7.2).

STUB — implementation follows the failing tests (TDD).
"""


def grade_quiz(questions, answers):
    """Grade a quiz attempt.

    questions: [{id, position, correct_index}]
    answers:   {position: chosen_index}  (str keys tolerated — they arrive as JSON)
    returns:   {all_correct, results:[{position, question_id, correct, correct_index}]}
               correct_index is populated ONLY for wrong answers (reveal); None otherwise.
    """
    answers = answers or {}
    results = []
    all_correct = True
    for q in questions:
        pos = q["position"]
        chosen = answers.get(pos, answers.get(str(pos)))
        try:
            correct = chosen is not None and int(chosen) == q["correct_index"]
        except (TypeError, ValueError):
            correct = False
        if not correct:
            all_correct = False
        results.append({
            "position": pos,
            "question_id": q.get("id"),
            "correct": correct,
            "correct_index": None if correct else q["correct_index"],
        })
    return {"all_correct": all_correct, "results": results}
