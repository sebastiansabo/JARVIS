"""Employee-facing Happy routes — the resolver surface + event/ack/snooze/dismiss.

All session-authenticated via Flask-Login (@login_required). These are not
permission-gated: any authenticated user may read their own surface and act on it.
No endpoint here returns another person's engagement data.
"""
import logging
from datetime import datetime, timezone

from flask import request, jsonify
from flask_login import login_required, current_user

from happy.routes import happy_bp, iso, jsonable
from happy.repositories import SurfaceRepository
from happy.services.surface_resolver import SurfaceResolver, PLACEMENT_LIMITS
from happy.services.tokens import mint_impression_token, verify_impression_token

logger = logging.getLogger("jarvis.happy.routes.surface")

_ALLOWED_EVENTS = ("impression", "read", "click", "dismiss", "snooze")

# ack/snooze/dismiss mutate per-campaign state and (for ack) write a compliance
# record, so they require the signed impression token that proves the item was
# actually surfaced to this user. Longer TTL than raw events: a user may read a
# long mandatory policy before acknowledging it.
_ACT_TTL = 3600  # 1 hour


def _require_shown_item(body, campaign_id):
    """Verify the impression token binds this user to this campaign. Returns the
    token payload, or None if invalid/expired/mismatched."""
    data = verify_impression_token((body or {}).get("impression_token"), max_age=_ACT_TTL)
    if not data or data.get("user_id") != current_user.id or data.get("campaign_id") != campaign_id:
        return None
    return data


def _serialize_item(c, user_id, placement, snooze_count, route, now):
    media = None
    if c.get("media_key"):
        media = {"key": c["media_key"], "url": f"/api/media/{c['media_key']}", "alt": c.get("media_alt")}
    cta = None
    if c.get("cta_label"):
        cta = {"label": c["cta_label"], "href": c.get("cta_href"), "deeplink": c.get("cta_deeplink")}
    ack = None
    has_ack = c.get("ack_mode") and c["ack_mode"] != "none"
    if has_ack:
        ack = {"mode": c["ack_mode"], "deadline_at": iso(c.get("ack_deadline_at")), "state": "pending"}

    # Past the ack deadline and still unacknowledged, a mandatory campaign becomes
    # non-dismissible on /app/hub only (spec §5.2) — never on Dashboard/mobile.
    dismissible = c.get("dismissible", True)
    deadline = c.get("ack_deadline_at")
    if has_ack and route == "/app/hub" and deadline and now > deadline:
        dismissible = False

    return {
        "id": c["id"], "kind": c["kind"], "tier": c["tier"], "kicker": c.get("kicker"),
        "title": c["title"], "summary": c.get("summary"), "body_md": c.get("body_md"),
        "event_at": iso(c.get("event_at")),
        "media": media, "cta": cta, "ack": ack,
        "dismissible": dismissible,
        "snooze_remaining": max(0, 3 - (snooze_count or 0)),
        "impression_token": mint_impression_token(c["id"], user_id, placement),
    }


@happy_bp.route("/surface", methods=["GET"])
@login_required
def surface():
    placement = request.args.get("placement", "")
    route = request.args.get("route", "")
    if placement not in PLACEMENT_LIMITS:
        return jsonify({"error": "invalid placement"}), 400

    user_id = current_user.id
    now = datetime.now(timezone.utc)
    repo = SurfaceRepository()
    result = SurfaceResolver(repo).resolve({"id": user_id}, placement, route, now)

    states = repo.get_user_states(user_id)
    items = [
        _serialize_item(c, user_id, placement, (states.get(c["id"]) or {}).get("snooze_count", 0), route, now)
        for c in result["items"]
    ]
    meta = result["meta"]
    return jsonify({
        "placement": placement,
        "items": items,
        "meta": {"capped": meta["capped"], "next_eligible_at": iso(meta["next_eligible_at"])},
    })


@happy_bp.route("/events", methods=["POST"])
@login_required
def events():
    body = request.get_json(silent=True) or {}
    data = verify_impression_token(body.get("impression_token"))
    if not data or data["user_id"] != current_user.id:
        return jsonify({"error": "invalid or expired impression token"}), 400
    etype = body.get("type")
    if etype not in _ALLOWED_EVENTS:
        return jsonify({"error": "invalid event type"}), 400
    try:
        SurfaceRepository().record_event(
            data["campaign_id"], current_user.id, data["surface"], etype, body.get("dwell_ms")
        )
    except Exception:                       # fire-and-forget: never block a render
        logger.exception("happy: event write failed")
    return jsonify({"ok": True})


@happy_bp.route("/campaigns/<int:campaign_id>/ack", methods=["POST"])
@login_required
def acknowledge(campaign_id):
    body = request.get_json(silent=True) or {}
    method = body.get("method", "click")
    if method not in ("click", "quiz"):
        return jsonify({"error": "unsupported ack method"}), 400
    data = _require_shown_item(body, campaign_id)
    if not data:
        return jsonify({"error": "invalid or expired impression token"}), 400
    repo = SurfaceRepository()
    # Defense in depth: an ack is a compliance record — the user must be in the
    # materialized audience for this campaign, not merely holding a token.
    if not repo.is_targeted(campaign_id, current_user.id):
        return jsonify({"error": "not in campaign audience"}), 403

    if method == "quiz":
        result = repo.record_quiz_attempt(campaign_id, body.get("answers") or {})
        if not result["all_correct"]:
            # Not acknowledged: reveal only wrong answers for re-selection. No score.
            return jsonify({"acknowledged": False, "quiz": result})
        first = repo.record_ack(campaign_id, current_user.id, "quiz", data["surface"])
        return jsonify({"acknowledged": True, "first_time": first, "quiz": {"all_correct": True}})

    first = repo.record_ack(campaign_id, current_user.id, "click", data["surface"])
    return jsonify({"acknowledged": True, "first_time": first})


@happy_bp.route("/campaigns/<int:campaign_id>/quiz", methods=["GET"])
@login_required
def quiz(campaign_id):
    repo = SurfaceRepository()
    if not repo.is_targeted(campaign_id, current_user.id):
        return jsonify({"error": "not in campaign audience"}), 403
    # Employee view — never includes correct_index.
    return jsonify({"questions": jsonable(repo.get_quiz(campaign_id, include_answers=False))})


@happy_bp.route("/campaigns/<int:campaign_id>/snooze", methods=["POST"])
@login_required
def snooze(campaign_id):
    if not _require_shown_item(request.get_json(silent=True), campaign_id):
        return jsonify({"error": "invalid or expired impression token"}), 400
    count = SurfaceRepository().snooze(campaign_id, current_user.id, datetime.now(timezone.utc))
    return jsonify({"snooze_count": count, "snooze_remaining": max(0, 3 - count)})


@happy_bp.route("/campaigns/<int:campaign_id>/dismiss", methods=["POST"])
@login_required
def dismiss(campaign_id):
    if not _require_shown_item(request.get_json(silent=True), campaign_id):
        return jsonify({"error": "invalid or expired impression token"}), 400
    SurfaceRepository().dismiss(campaign_id, current_user.id, datetime.now(timezone.utc))
    return jsonify({"ok": True})


@happy_bp.route("/inbox", methods=["GET"])
@login_required
def inbox():
    rows = SurfaceRepository().get_open_acks(current_user.id)
    return jsonify({"items": jsonable(rows)})
