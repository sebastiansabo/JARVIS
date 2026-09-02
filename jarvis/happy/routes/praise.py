"""Praise routes — recognition (spec §7.4 / §8.1).

Employee routes are session-authenticated. No endpoint ranks named employees;
`/praise/me` returns only the caller's own streak + trend.
"""
from datetime import datetime, timezone

from flask import request, jsonify
from flask_login import login_required, current_user

from core.roles.decorators import v2_permission_required
from happy.routes import happy_bp, jsonable
from happy.repositories import PraiseRepository, KudosError


@happy_bp.route("/praise/value-tags", methods=["GET"])
@login_required
def praise_value_tags():
    return jsonify({"value_tags": jsonable(PraiseRepository().list_value_tags())})


@happy_bp.route("/praise/wallet", methods=["GET"])
@login_required
def praise_wallet():
    return jsonify(jsonable(PraiseRepository().get_wallet(current_user.id, datetime.now(timezone.utc))))


@happy_bp.route("/praise/kudos", methods=["POST"])
@login_required
def praise_send():
    body = request.get_json(silent=True) or {}
    to_user = body.get("to_user")
    if not isinstance(to_user, int):
        return jsonify({"error": "to_user is required"}), 400
    try:
        result = PraiseRepository().send_kudos(
            current_user.id, to_user, body.get("value_tag_id"), body.get("note"),
            datetime.now(timezone.utc), points=body.get("points"),
            visibility=body.get("visibility", "company"),
        )
    except KudosError as e:
        return jsonify({"error": "kudos rejected", "code": str(e)}), 400
    return jsonify({"kudos": result}), 201


@happy_bp.route("/praise/received", methods=["GET"])
@login_required
def praise_received():
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    return jsonify({"items": jsonable(PraiseRepository().get_received(current_user.id, limit, offset))})


@happy_bp.route("/praise/sent", methods=["GET"])
@login_required
def praise_sent():
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    return jsonify({"items": jsonable(PraiseRepository().get_sent(current_user.id, limit, offset))})


@happy_bp.route("/praise/me", methods=["GET"])
@login_required
def praise_me():
    return jsonify(jsonable(PraiseRepository().get_my_praise(current_user.id, datetime.now(timezone.utc))))


@happy_bp.route("/admin/praise/flags", methods=["GET"])
@v2_permission_required("happy", "praise", "moderate")
def praise_flags():
    return jsonify({"flags": jsonable(PraiseRepository().get_flags())})
