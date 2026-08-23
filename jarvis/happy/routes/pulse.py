"""Pulse routes — anonymous surveys / eNPS (spec §7.5 / §8).

Employee routes never expose who answered. Admin results are threshold-enforced:
cohorts below min_group_size return {suppressed:true}.
"""
from datetime import datetime, timezone

from flask import request, jsonify
from flask_login import login_required, current_user

from core.roles.decorators import v2_permission_required
from happy.routes import happy_bp, jsonable
from happy.repositories import PulseRepository, PulseError


# -- employee -----------------------------------------------------------------

@happy_bp.route("/pulse/current", methods=["GET"])
@login_required
def pulse_current():
    current = PulseRepository().get_current(current_user.id)
    if not current:
        return jsonify({"pulse": None})
    return jsonify(jsonable(current))


@happy_bp.route("/pulse/<int:pulse_id>/respond", methods=["POST"])
@login_required
def pulse_respond(pulse_id):
    answers = (request.get_json(silent=True) or {}).get("answers")
    if not isinstance(answers, dict) or not answers:
        return jsonify({"error": "answers required"}), 400
    try:
        PulseRepository().respond(pulse_id, current_user.id, answers, datetime.now(timezone.utc))
    except PulseError as e:
        code = str(e)
        # already_responded / not_invited / not_open are client-state, not server faults
        return jsonify({"error": "pulse response rejected", "code": code}), 409 if code == "already_responded" else 400
    return jsonify({"ok": True})


# -- admin --------------------------------------------------------------------

@happy_bp.route("/admin/pulses", methods=["GET"])
@v2_permission_required("happy", "pulse", "manage")
def admin_list_pulses():
    return jsonify({"pulses": jsonable(PulseRepository().list(request.args.get("status")))})


@happy_bp.route("/admin/pulses", methods=["POST"])
@v2_permission_required("happy", "pulse", "manage")
def admin_create_pulse():
    body = request.get_json(silent=True) or {}
    if not body.get("slug") or not body.get("title"):
        return jsonify({"error": "slug and title are required"}), 400
    return jsonify({"pulse": jsonable(PulseRepository().create(body, current_user.id))}), 201


@happy_bp.route("/admin/pulses/<int:pulse_id>", methods=["GET"])
@v2_permission_required("happy", "pulse", "manage")
def admin_get_pulse(pulse_id):
    repo = PulseRepository()
    pulse = repo.get_pulse(pulse_id)
    if not pulse:
        return jsonify({"error": "not found"}), 404
    return jsonify({"pulse": jsonable(pulse), "questions": jsonable(repo.get_questions(pulse_id))})


@happy_bp.route("/admin/pulses/<int:pulse_id>/questions", methods=["PUT"])
@v2_permission_required("happy", "pulse", "manage")
def admin_set_questions(pulse_id):
    body = request.get_json(silent=True) or {}
    try:
        n = PulseRepository().replace_questions(pulse_id, body.get("questions") or [])
    except PulseError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"questions": n})


@happy_bp.route("/admin/pulses/<int:pulse_id>/open", methods=["POST"])
@v2_permission_required("happy", "pulse", "manage")
def admin_open_pulse(pulse_id):
    try:
        invited = PulseRepository().open_pulse(pulse_id, datetime.now(timezone.utc),
                                               (request.get_json(silent=True) or {}).get("audience_user_ids"))
    except PulseError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "live", "invited": invited})


@happy_bp.route("/admin/pulses/<int:pulse_id>/close", methods=["POST"])
@v2_permission_required("happy", "pulse", "manage")
def admin_close_pulse(pulse_id):
    PulseRepository().close_pulse(pulse_id, datetime.now(timezone.utc))
    return jsonify({"status": "closed"})


@happy_bp.route("/admin/pulses/<int:pulse_id>/results", methods=["GET"])
@v2_permission_required("happy", "pulse", "results")
def admin_pulse_results(pulse_id):
    results = PulseRepository().get_results(pulse_id)
    if results is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(jsonable(results))
