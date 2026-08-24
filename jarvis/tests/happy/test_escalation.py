"""Unit tests for escalation step-determination (spec §5.4)."""
from datetime import datetime, timedelta, timezone

from happy.services.escalation import due_step

UTC = timezone.utc
PUB = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
DEADLINE = datetime(2026, 8, 15, 21, 0, tzinfo=UTC)


def at(delta):
    return PUB + delta


def test_nothing_due_before_48h():
    assert due_step(at(timedelta(hours=47)), PUB, DEADLINE, last_step=0) == 0


def test_step1_at_48h():
    assert due_step(at(timedelta(hours=48)), PUB, DEADLINE, last_step=0) == 1


def test_step2_at_5d_after_step1():
    assert due_step(at(timedelta(days=5)), PUB, DEADLINE, last_step=1) == 2


def test_step3_at_7d_after_step2():
    assert due_step(at(timedelta(days=7)), PUB, DEADLINE, last_step=2) == 3


def test_step4_at_deadline():
    assert due_step(DEADLINE, PUB, DEADLINE, last_step=3) == 4


def test_step5_three_days_after_deadline():
    assert due_step(DEADLINE + timedelta(days=3), PUB, DEADLINE, last_step=4) == 5


def test_no_repeat_after_last_step():
    assert due_step(DEADLINE + timedelta(days=10), PUB, DEADLINE, last_step=5) == 0


def test_steps_fire_in_order_when_job_lagged():
    # 6 days elapsed but only step1 fired so far -> next is step2, not step3
    assert due_step(at(timedelta(days=6)), PUB, DEADLINE, last_step=1) == 2


def test_no_deadline_only_time_based_steps():
    assert due_step(at(timedelta(days=30)), PUB, None, last_step=2) == 3
    assert due_step(at(timedelta(days=30)), PUB, None, last_step=3) == 0
