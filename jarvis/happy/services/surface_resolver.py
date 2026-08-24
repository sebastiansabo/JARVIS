"""Happy surface resolver — the core primitive (spec §4).

Pure and unit-testable: `resolve(user_context, placement, route, now)` returns the
items to render for one placement. All I/O is behind the injected repository. The
client never decides what to show; it asks for a surface and renders the result.

Pipeline (spec §4):
  1. eligible      status=live, now in [starts_at, ends_at], placement in placements
  2. audience      user_id in the materialized campaign_targets set
  3. state         not acknowledged, not dismissed, snooze not active
  4. route guard   placement allowed on this route (never mid-flow)
  5. frequency cap per placement, per day (critical overrides + audit)
  6. priority sort critical > important > normal, then ack_deadline ASC, then created DESC
  7. slice         interstitial:1 · dash_banner:3 · hub_card:5 · feed:20
"""
from datetime import datetime, time, timedelta, timezone

TIER_ORDER = {"critical": 0, "important": 1, "normal": 2}

PLACEMENT_LIMITS = {"interstitial": 1, "dash_banner": 3, "hub_card": 5, "feed": 20}

# Per-placement per-day caps that feed the frequency governor. hub_card and feed
# are persistent surfaces and are not daily-capped as interruptions.
DAILY_CAP = {"interstitial": 1, "dash_banner": 3, "hub_card": None, "feed": None}

# Route guard (spec §5.2 / §6.2). interstitial never interrupts a task route.
INTERSTITIAL_ROUTES = {"/app/hub", "/app/dashboard"}
HUB_CARD_ROUTES = {"/app/hub"}
DASH_BANNER_ROUTES = {"/app/dashboard"}

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class SurfaceResolver:
    def __init__(self, repo):
        self.repo = repo

    # -- public ---------------------------------------------------------------

    def resolve(self, user_context, placement, route, now):
        user_id = user_context["id"]
        targeted = self.repo.get_targeted_campaign_ids(user_id)
        states = self.repo.get_user_states(user_id)
        freq = self.repo.get_frequency(user_id, now.date())

        eligible = [
            c for c in self.repo.get_live_campaigns()
            if self._is_eligible(c, placement, route, now, targeted, states)
        ]
        eligible = self._prioritize(eligible)

        capped = False
        next_eligible_at = None
        override = False
        cap = DAILY_CAP.get(placement)
        if cap is not None and freq.get(placement, 0) >= cap:
            capped = True
            criticals = [c for c in eligible if c["tier"] == "critical"]
            if criticals:
                override = True
                eligible = criticals
            else:
                eligible = []
                next_eligible_at = self._next_day_start(now)

        items = eligible[: PLACEMENT_LIMITS.get(placement, 0)]
        if override:
            for c in items:
                self.repo.record_cap_override(user_id, c["id"], placement, now)

        return {"items": items, "meta": {"capped": capped, "next_eligible_at": next_eligible_at}}

    # -- steps ----------------------------------------------------------------

    def _is_eligible(self, c, placement, route, now, targeted, states):
        if c.get("status") != "live":
            return False
        if placement not in c["placements"]:
            return False
        if c["id"] not in targeted:                       # audience
            return False
        if c.get("starts_at") and now < c["starts_at"]:   # not yet started
            return False
        if c.get("ends_at") and now > c["ends_at"]:        # ended
            return False
        if not self._route_allows(placement, route):       # route guard
            return False

        st = states.get(c["id"], {})
        if st.get("acknowledged"):
            return False
        dismissed_until = st.get("dismissed_until")
        if dismissed_until and now < dismissed_until:
            return False

        # Snooze suppresses the interrupting surface only. After the 3rd snooze the
        # campaign converts to a persistent Hub card and no longer interrupts.
        if placement == "interstitial":
            snoozed_until = st.get("snoozed_until")
            if snoozed_until and now < snoozed_until:
                return False
            if st.get("snooze_count", 0) >= 3:
                return False
        return True

    @staticmethod
    def _route_allows(placement, route):
        if placement == "interstitial":
            return route in INTERSTITIAL_ROUTES
        if placement == "hub_card":
            return route in HUB_CARD_ROUTES
        if placement == "dash_banner":
            return route in DASH_BANNER_ROUTES
        if placement == "feed":
            return True
        return False

    @staticmethod
    def _prioritize(campaigns):
        # created DESC first (stable base), then tier then deadline ASC (with-deadline first)
        campaigns = sorted(campaigns, key=lambda c: c.get("created_at") or _EPOCH, reverse=True)
        campaigns.sort(key=lambda c: (TIER_ORDER.get(c["tier"], 99), SurfaceResolver._deadline_key(c)))
        return campaigns

    @staticmethod
    def _deadline_key(c):
        d = c.get("ack_deadline_at")
        return (0, d) if d else (1,)   # campaigns with a deadline sort first, earliest first

    @staticmethod
    def _next_day_start(now):
        nxt = (now + timedelta(days=1)).date()
        return datetime.combine(nxt, time(0, 0), tzinfo=now.tzinfo)
