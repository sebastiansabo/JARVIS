from core.connectors.connecteam.services.connecteam_service import _decider_name


def test_none_when_no_decisions():
    assert _decider_name([]) is None


def test_picks_approved_decider():
    rows = [{'decision': 'approved', 'decided_by_name': 'Ion Popescu'}]
    assert _decider_name(rows) == 'Ion Popescu'


def test_picks_rejected_decider():
    rows = [{'decision': 'rejected', 'decided_by_name': 'Ana Ionescu'}]
    assert _decider_name(rows) == 'Ana Ionescu'


def test_ignores_non_terminal_decisions():
    rows = [{'decision': 'returned', 'decided_by_name': 'X'}]
    assert _decider_name(rows) is None
