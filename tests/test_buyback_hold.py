import sys, os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
from buyback import lifecycle
from buyback.services.buyback_service import BuyBackService

def test_on_hold_transitions_and_label():
    assert lifecycle.ON_HOLD == 'ON_HOLD'
    assert lifecycle.STATUS_LABELS['ON_HOLD'] == 'Suspendat'
    assert lifecycle.is_valid_transition('PENDING_EVALUATION', 'ON_HOLD')
    assert lifecycle.is_valid_transition('INSPECTION', 'ON_HOLD')
    assert lifecycle.is_valid_transition('ON_HOLD', 'INSPECTION')
    assert lifecycle.is_valid_transition('ON_HOLD', 'PENDING_EVALUATION')
    # existing transitions preserved
    assert lifecycle.is_valid_transition('PENDING_EVALUATION', 'INITIAL_OFFER')
    assert not lifecycle.is_valid_transition('BOUGHT', 'ON_HOLD')


def _service():
    svc = BuyBackService()
    svc.records = MagicMock()
    svc.events = MagicMock()
    return svc


ACTIVE_STATUSES = [
    lifecycle.PENDING_EVALUATION,
    lifecycle.INITIAL_OFFER,
    lifecycle.INSPECTION,
    lifecycle.FINAL_OFFER,
]


@pytest.mark.parametrize('old_status', ACTIVE_STATUSES)
def test_hold_from_each_active_status(old_status):
    svc = _service()
    rec = {'id': 1, 'status': old_status}
    svc.records.set_status.return_value = {**rec, 'status': lifecycle.ON_HOLD}
    svc.records.update.return_value = {**rec, 'status': lifecycle.ON_HOLD, 'hold_prior_status': old_status}

    result = svc.hold(rec, 'Poze lipsă', 'lipsesc 3 poze', actor=9)

    svc.records.set_status.assert_called_once_with(1, lifecycle.ON_HOLD, 9)

    update_args = svc.records.update.call_args.args
    assert update_args[0] == 1
    payload = update_args[1]
    assert payload['hold_prior_status'] == old_status
    assert payload['hold_reason'] == 'Poze lipsă'
    assert payload['hold_note'] == 'lipsesc 3 poze'
    assert payload['held_by'] == 9
    assert payload['held_at'] is not None

    svc.events.log.assert_called_once_with(
        1, 'held', 9, {'reason': 'Poze lipsă', 'note': 'lipsesc 3 poze'}
    )

    # returned value is exactly what update() returned
    assert result is svc.records.update.return_value


@pytest.mark.parametrize('bad_status', [lifecycle.BOUGHT, lifecycle.LOST, lifecycle.ON_HOLD])
def test_hold_from_non_active_status_raises(bad_status):
    svc = _service()
    rec = {'id': 2, 'status': bad_status}

    with pytest.raises(ValueError):
        svc.hold(rec, 'reason', 'note', actor=9)

    svc.records.set_status.assert_not_called()
    svc.records.update.assert_not_called()
    svc.events.log.assert_not_called()


def test_resume_from_on_hold_restores_exact_prior_status():
    svc = _service()
    rec = {
        'id': 3, 'status': lifecycle.ON_HOLD,
        'hold_prior_status': lifecycle.INSPECTION,
    }
    svc.records.set_status.return_value = {**rec, 'status': lifecycle.INSPECTION}
    svc.records.update.return_value = {**rec, 'status': lifecycle.INSPECTION}

    result = svc.resume(rec, actor=7)

    svc.records.set_status.assert_called_once_with(3, lifecycle.INSPECTION, 7)

    update_args = svc.records.update.call_args.args
    assert update_args[0] == 3
    payload = update_args[1]
    assert payload == {
        'hold_prior_status': None,
        'hold_reason': None,
        'hold_note': None,
        'held_at': None,
        'held_by': None,
    }

    svc.events.log.assert_called_once_with(
        3, 'resumed', 7, {'restored_to': lifecycle.INSPECTION}
    )

    assert result is svc.records.update.return_value


def test_resume_from_non_on_hold_raises():
    svc = _service()
    rec = {'id': 4, 'status': lifecycle.PENDING_EVALUATION}

    with pytest.raises(ValueError):
        svc.resume(rec, actor=7)

    svc.records.set_status.assert_not_called()
    svc.records.update.assert_not_called()
    svc.events.log.assert_not_called()
