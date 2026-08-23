"""Unit tests for the Happy surface resolver (spec §4, the 12 canonical cases).

Pure tests — no DB. A FakeRepo supplies live campaigns, the user's targeted set,
per-campaign UI state, and the daily frequency ledger; the resolver applies
window/audience/state/route/cap/priority/slice logic.
"""
from datetime import datetime, timedelta, timezone

from happy.services.surface_resolver import SurfaceResolver

UTC = timezone.utc
NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)
PAST = NOW - timedelta(days=1)
FUTURE = NOW + timedelta(days=7)
USER = {"id": 42, "company": "AutoWorld", "department": "Vanzari"}


def _campaign(cid, **over):
    base = dict(
        id=cid, slug=f"c{cid}", kind="hr_announcement", tier="normal",
        placements=["interstitial"], locale="ro",
        title=f"Campaign {cid}", summary=None, body_md=None, kicker=None,
        media_key=None, media_alt=None, cta_label=None, cta_href=None, cta_deeplink=None,
        event_at=None, ack_mode="none", ack_deadline_at=None, dismissible=True,
        status="live", starts_at=PAST, ends_at=FUTURE, created_at=PAST,
    )
    base.update(over)
    return base


class FakeRepo:
    def __init__(self):
        self.live = []
        self.targeted = set()
        self.states = {}          # campaign_id -> state dict
        self.freq = {}            # placement -> shown_count today
        self.audits = []          # (user_id, campaign_id, placement)

    def get_live_campaigns(self):
        return list(self.live)

    def get_targeted_campaign_ids(self, user_id):
        return set(self.targeted)

    def get_user_states(self, user_id):
        return dict(self.states)

    def get_frequency(self, user_id, day):
        return dict(self.freq)

    def record_cap_override(self, user_id, campaign_id, placement, now):
        self.audits.append((user_id, campaign_id, placement))


def _resolve(repo, placement, route, now=NOW):
    return SurfaceResolver(repo).resolve(USER, placement, route, now)


def _ids(result):
    return [it["id"] for it in result["items"]]


# 1 ---------------------------------------------------------------------------
def test_user_not_in_audience_is_empty():
    repo = FakeRepo()
    repo.live = [_campaign(1)]
    repo.targeted = set()  # not targeted
    assert _ids(_resolve(repo, "interstitial", "/app/hub")) == []


# 2 ---------------------------------------------------------------------------
def test_campaign_not_yet_started_is_empty():
    repo = FakeRepo()
    repo.live = [_campaign(1, starts_at=NOW + timedelta(days=1))]
    repo.targeted = {1}
    assert _ids(_resolve(repo, "interstitial", "/app/hub")) == []


# 3 ---------------------------------------------------------------------------
def test_campaign_ended_is_empty():
    repo = FakeRepo()
    repo.live = [_campaign(1, ends_at=NOW - timedelta(hours=1))]
    repo.targeted = {1}
    assert _ids(_resolve(repo, "interstitial", "/app/hub")) == []


# 4 ---------------------------------------------------------------------------
def test_already_acknowledged_is_empty():
    repo = FakeRepo()
    repo.live = [_campaign(1)]
    repo.targeted = {1}
    repo.states = {1: {"acknowledged": True}}
    assert _ids(_resolve(repo, "interstitial", "/app/hub")) == []


# 5 ---------------------------------------------------------------------------
def test_snoozed_not_expired_is_empty():
    repo = FakeRepo()
    repo.live = [_campaign(1)]
    repo.targeted = {1}
    repo.states = {1: {"snoozed_until": NOW + timedelta(hours=2), "snooze_count": 1}}
    assert _ids(_resolve(repo, "interstitial", "/app/hub")) == []


# 6 ---------------------------------------------------------------------------
def test_snoozed_three_times_converts_to_hub_card_only():
    repo = FakeRepo()
    repo.live = [_campaign(1, placements=["interstitial", "hub_card"])]
    repo.targeted = {1}
    repo.states = {1: {"snooze_count": 3, "snoozed_until": NOW + timedelta(hours=2)}}
    # No longer interrupts as an interstitial …
    assert _ids(_resolve(repo, "interstitial", "/app/hub")) == []
    # … but persists as a Hub card.
    assert _ids(_resolve(repo, "hub_card", "/app/hub")) == [1]


# 7 ---------------------------------------------------------------------------
def test_critical_sorts_before_normal():
    repo = FakeRepo()
    repo.live = [_campaign(1, tier="normal"), _campaign(2, tier="critical")]
    repo.targeted = {1, 2}
    # interstitial slice is 1 → only the critical survives, first.
    assert _ids(_resolve(repo, "interstitial", "/app/hub")) == [2]


# 8 ---------------------------------------------------------------------------
def test_same_tier_earlier_deadline_first():
    repo = FakeRepo()
    repo.live = [
        _campaign(1, tier="important", placements=["hub_card"],
                  ack_deadline_at=NOW + timedelta(days=2)),
        _campaign(2, tier="important", placements=["hub_card"],
                  ack_deadline_at=NOW + timedelta(days=1)),
    ]
    repo.targeted = {1, 2}
    assert _ids(_resolve(repo, "hub_card", "/app/hub")) == [2, 1]


# 9 ---------------------------------------------------------------------------
def test_daily_cap_reached_normal_is_empty_with_next_eligible():
    repo = FakeRepo()
    repo.live = [_campaign(1, tier="normal")]
    repo.targeted = {1}
    repo.freq = {"interstitial": 1}  # cap of 1 already reached
    result = _resolve(repo, "interstitial", "/app/hub")
    assert _ids(result) == []
    assert result["meta"]["capped"] is True
    assert result["meta"]["next_eligible_at"] is not None
    assert result["meta"]["next_eligible_at"] > NOW


# 10 --------------------------------------------------------------------------
def test_daily_cap_reached_critical_overrides_and_audits():
    repo = FakeRepo()
    repo.live = [_campaign(1, tier="critical")]
    repo.targeted = {1}
    repo.freq = {"interstitial": 1}  # cap reached
    result = _resolve(repo, "interstitial", "/app/hub")
    assert _ids(result) == [1]          # critical overrides the cap
    assert result["meta"]["capped"] is True
    assert repo.audits == [(42, 1, "interstitial")]  # audit row written


# 11 --------------------------------------------------------------------------
def test_route_guard_interstitial_blocked_offroute_banner_ok_on_host():
    repo = FakeRepo()
    repo.live = [_campaign(1, placements=["interstitial", "dash_banner"])]
    repo.targeted = {1}
    # interstitial never interrupts a task route
    assert _ids(_resolve(repo, "interstitial", "/app/accounting")) == []
    # dash_banner shows on a route that hosts one
    assert _ids(_resolve(repo, "dash_banner", "/app/dashboard")) == [1]


# 12 --------------------------------------------------------------------------
def test_new_joiner_inherits_when_targeted():
    repo = FakeRepo()
    # published before the user existed; nightly refresh added them to targets
    repo.live = [_campaign(1, starts_at=NOW - timedelta(days=30))]
    repo.targeted = {1}
    assert _ids(_resolve(repo, "interstitial", "/app/hub")) == [1]
