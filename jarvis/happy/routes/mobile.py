"""Mobile JWT twin of the employee-facing Happy API (spec §8 — one service layer,
two transports).

Same SurfaceResolver / repositories / tokens as the web routes; the only
differences are JWT auth (core.mobile._shared.jwt_required + _current_mobile_user)
and platform='android' on events. The admin Board stays web-only. Mounted at
/api/mobile/happy. (CORS is handled globally by app._mobile_cors on Capacitor
origins, so no per-endpoint CORS wiring is needed.)
"""
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from core.mobile.routes._shared import jwt_required, _current_mobile_user
from happy.routes import jsonable
from happy.routes.surface import _serialize_item, _ALLOWED_EVENTS, _ACT_TTL
from happy.repositories import (
    SurfaceRepository, PraiseRepository, KudosError, PulseRepository, PulseError,
)
from happy.services.surface_resolver import SurfaceResolver, PLACEMENT_LIMITS
from happy.services.tokens import verify_impression_token

happy_mobile_bp = Blueprint("happy_mobile_bp", __name__)
PLATFORM = "android"


def _uid():
    u = _current_mobile_user()
    return u.id if u else None


def _require_shown(body, campaign_id):
    data = verify_impression_token((body or {}).get("impression_token"), max_age=_ACT_TTL)
    if not data or data.get("user_id") != _uid() or data.get("campaign_id") != campaign_id:
        return None
    return data


# -- surface engine -----------------------------------------------------------

@happy_mobile_bp.route("/surface", methods=["GET"])
@jwt_required
def surface():
    placement = request.args.get("placement", "")
    route = request.args.get("route", "")
    if placement not in PLACEMENT_LIMITS:
        return jsonify({"error": "invalid placement"}), 400
    uid = _uid()
    now = datetime.now(timezone.utc)
    repo = SurfaceRepository()
    result = SurfaceResolver(repo).resolve({"id": uid}, placement, route, now)
    states = repo.get_user_states(uid)
    items = [_serialize_item(c, uid, placement, (states.get(c["id"]) or {}).get("snooze_count", 0), route, now)
             for c in result["items"]]
    return jsonify({"placement": placement, "items": items, "meta": result["meta"]})


@happy_mobile_bp.route("/events", methods=["POST"])
@jwt_required
def events():
    body = request.get_json(silent=True) or {}
    data = verify_impression_token(body.get("impression_token"))
    if not data or data["user_id"] != _uid():
        return jsonify({"error": "invalid or expired impression token"}), 400
    if body.get("type") not in _ALLOWED_EVENTS:
        return jsonify({"error": "invalid event type"}), 400
    try:
        SurfaceRepository().record_event(
            data["campaign_id"], _uid(), data["surface"], body["type"], body.get("dwell_ms"), platform=PLATFORM)
    except Exception:
        pass
    return jsonify({"ok": True})


@happy_mobile_bp.route("/campaigns/<int:campaign_id>/ack", methods=["POST"])
@jwt_required
def acknowledge(campaign_id):
    body = request.get_json(silent=True) or {}
    method = body.get("method", "click")
    if method not in ("click", "quiz"):
        return jsonify({"error": "unsupported ack method"}), 400
    data = _require_shown(body, campaign_id)
    if not data:
        return jsonify({"error": "invalid or expired impression token"}), 400
    repo = SurfaceRepository()
    if not repo.is_targeted(campaign_id, _uid()):
        return jsonify({"error": "not in campaign audience"}), 403
    if method == "quiz":
        result = repo.record_quiz_attempt(campaign_id, body.get("answers") or {})
        if not result["all_correct"]:
            return jsonify({"acknowledged": False, "quiz": result})
        first = repo.record_ack(campaign_id, _uid(), "quiz", data["surface"])
        return jsonify({"acknowledged": True, "first_time": first, "quiz": {"all_correct": True}})
    first = repo.record_ack(campaign_id, _uid(), "click", data["surface"])
    return jsonify({"acknowledged": True, "first_time": first})


@happy_mobile_bp.route("/campaigns/<int:campaign_id>/snooze", methods=["POST"])
@jwt_required
def snooze(campaign_id):
    if not _require_shown(request.get_json(silent=True), campaign_id):
        return jsonify({"error": "invalid or expired impression token"}), 400
    count = SurfaceRepository().snooze(campaign_id, _uid(), datetime.now(timezone.utc))
    return jsonify({"snooze_count": count, "snooze_remaining": max(0, 3 - count)})


@happy_mobile_bp.route("/campaigns/<int:campaign_id>/dismiss", methods=["POST"])
@jwt_required
def dismiss(campaign_id):
    if not _require_shown(request.get_json(silent=True), campaign_id):
        return jsonify({"error": "invalid or expired impression token"}), 400
    SurfaceRepository().dismiss(campaign_id, _uid(), datetime.now(timezone.utc))
    return jsonify({"ok": True})


@happy_mobile_bp.route("/campaigns/<int:campaign_id>/quiz", methods=["GET"])
@jwt_required
def quiz(campaign_id):
    repo = SurfaceRepository()
    if not repo.is_targeted(campaign_id, _uid()):
        return jsonify({"error": "not in campaign audience"}), 403
    return jsonify({"questions": jsonable(repo.get_quiz(campaign_id, include_answers=False))})


@happy_mobile_bp.route("/inbox", methods=["GET"])
@jwt_required
def inbox():
    return jsonify({"items": jsonable(SurfaceRepository().get_open_acks(_uid()))})


# -- praise -------------------------------------------------------------------

@happy_mobile_bp.route("/praise/value-tags", methods=["GET"])
@jwt_required
def praise_value_tags():
    return jsonify({"value_tags": jsonable(PraiseRepository().list_value_tags())})


@happy_mobile_bp.route("/praise/wallet", methods=["GET"])
@jwt_required
def praise_wallet():
    return jsonify(jsonable(PraiseRepository().get_wallet(_uid(), datetime.now(timezone.utc))))


@happy_mobile_bp.route("/praise/kudos", methods=["POST"])
@jwt_required
def praise_send():
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("to_user"), int):
        return jsonify({"error": "to_user is required"}), 400
    try:
        result = PraiseRepository().send_kudos(
            _uid(), body["to_user"], body.get("value_tag_id"), body.get("note"),
            datetime.now(timezone.utc), points=body.get("points"),
            visibility=body.get("visibility", "company"))
    except KudosError as e:
        return jsonify({"error": "kudos rejected", "code": str(e)}), 400
    return jsonify({"kudos": result}), 201


@happy_mobile_bp.route("/praise/received", methods=["GET"])
@jwt_required
def praise_received():
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    return jsonify({"items": jsonable(PraiseRepository().get_received(_uid(), limit, offset))})


@happy_mobile_bp.route("/praise/me", methods=["GET"])
@jwt_required
def praise_me():
    return jsonify(jsonable(PraiseRepository().get_my_praise(_uid(), datetime.now(timezone.utc))))


# -- pulse --------------------------------------------------------------------

@happy_mobile_bp.route("/pulse/current", methods=["GET"])
@jwt_required
def pulse_current():
    current = PulseRepository().get_current(_uid())
    return jsonify(jsonable(current) if current else {"pulse": None})


@happy_mobile_bp.route("/pulse/<int:pulse_id>/respond", methods=["POST"])
@jwt_required
def pulse_respond(pulse_id):
    answers = (request.get_json(silent=True) or {}).get("answers")
    if not isinstance(answers, dict) or not answers:
        return jsonify({"error": "answers required"}), 400
    try:
        PulseRepository().respond(pulse_id, _uid(), answers, datetime.now(timezone.utc))
    except PulseError as e:
        code = str(e)
        return jsonify({"error": "pulse response rejected", "code": code}), 409 if code == "already_responded" else 400
    return jsonify({"ok": True})
