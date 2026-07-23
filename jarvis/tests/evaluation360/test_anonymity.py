"""Tests for the anonymity engine (spec §4, indicator B6). The n=2 hide case
must fail closed."""
import pytest

from hr.evaluation360.domain import anonymity as a


def test_peer_category_visible_at_threshold():
    assert a.category_visible('peer', 3) is True
    assert a.category_visible('peer', 2) is False
    assert a.category_visible('direct_report', 5) is True


def test_manager_and_self_always_attributed():
    assert a.is_attributed('manager')
    assert a.is_attributed('self')
    assert a.category_visible('manager', 1) is True
    assert a.category_visible('self', 1) is True


def test_apply_anonymity_splits_visible_and_hidden():
    counts = {'self': 1, 'manager': 1, 'peer': 4, 'direct_report': 2}
    visible, hidden = a.apply_anonymity(counts)
    assert visible == ['manager', 'peer', 'self']
    assert hidden == ['direct_report']  # n=2 peer-type below threshold


def test_assert_renderable_fails_closed_on_n2_peer():
    with pytest.raises(a.AnonymityViolation):
        a.assert_renderable('peer', 2)
    # visible categories don't raise
    a.assert_renderable('peer', 3)
    a.assert_renderable('manager', 1)


def test_custom_min_n_respected():
    assert a.category_visible('peer', 4, min_n=5) is False
    with pytest.raises(a.AnonymityViolation):
        a.assert_renderable('peer', 4, min_n=5)
