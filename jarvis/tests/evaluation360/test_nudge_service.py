"""Tests for NudgeService — the DB-backed 1/day/user rate limit (spec §9)."""
from unittest.mock import MagicMock

import pytest

from hr.evaluation360.services.nudge_service import NudgeService, NudgeRateLimited


def test_nudge_allowed_when_none_today():
    ev = MagicMock()
    ev.nudges_today.return_value = 0
    svc = NudgeService(event_repo=ev)
    assert svc.can_nudge(10) is True
    assert svc.nudge(cycle_id=5, user_id=10) is True
    ev.record_nudge.assert_called_once()
    ev.emit.assert_called_once()
    assert ev.emit.call_args[0][0] == 'nudge.sent'


def test_nudge_rate_limited_after_one():
    ev = MagicMock()
    ev.nudges_today.return_value = 1  # already nudged today
    svc = NudgeService(event_repo=ev)
    assert svc.can_nudge(10) is False
    with pytest.raises(NudgeRateLimited):
        svc.nudge(cycle_id=5, user_id=10)
    ev.record_nudge.assert_not_called()
