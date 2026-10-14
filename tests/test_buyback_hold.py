import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
from buyback import lifecycle

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
