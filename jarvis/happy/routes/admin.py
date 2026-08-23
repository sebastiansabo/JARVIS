"""Happy Board admin routes — campaign CRUD, audience, publish. All permission-gated.

preview-audience returns count + cohort breakdown only, never a name list (spec §8.2).
Publish enforces the authoring constraints (spec §6.5 / §7.1) server-side.
"""
from datetime import timedelta

from flask import request, jsonify
from flask_login import current_user

from core.roles.decorators import v2_permission_required
from happy.routes import happy_bp, jsonable
from happy.repositories import CampaignRepository, SurfaceRepository


def _validate_for_publish(c):
    """Return a list of human-readable validation errors (empty = ok)."""
    errors = []
    placements = c.get("placements") or []
    title = c.get("title") or ""
    if not title:
        errors.append("title is required")
    elif len(title) > 64:
        errors.append("title exceeds 64 characters")
    if "dash_banner" in placements and len(title) > 56:
        errors.append("title exceeds 56 characters (dash_banner limit)")
    if not placements:
        errors.append("at least one placement is required")
    if not c.get("ends_at"):
        errors.append("ends_at is required at publish")
    starts, ends = c.get("starts_at"), c.get("ends_at")
    if starts and ends and ends > starts + timedelta(days=90):
        errors.append("ends_at must be within 90 days of starts_at")
    if c.get("media_key") and len(c.get("media_alt") or "") < 10:
        errors.append("media_alt (>=10 chars) is required when media is present")
    if c.get("cta_label") and len(c["cta_label"]) > 24:
        errors.append("cta_label exceeds 24 characters")
    if c.get("ack_mode") and c["ack_mode"] not in ("none", "click", "quiz"):
        errors.append("invalid ack_mode")
    return errors


@happy_bp.route("/admin/campaigns", methods=["GET"])
@v2_permission_required("happy", "campaigns", "view")
def admin_list_campaigns():
    status = request.args.get("status")
    return jsonify({"campaigns": jsonable(CampaignRepository().list(status=status))})


@happy_bp.route("/admin/campaigns", methods=["POST"])
@v2_permission_required("happy", "campaigns", "edit")
def admin_create_campaign():
    body = request.get_json(silent=True) or {}
    if not body.get("slug") or not body.get("title") or not body.get("kind") or not body.get("placements"):
        return jsonify({"error": "slug, kind, title and placements are required"}), 400
    campaign = CampaignRepository().create(body, current_user.id)
    return jsonify({"campaign": jsonable(campaign)}), 201


@happy_bp.route("/admin/campaigns/<int:campaign_id>", methods=["GET"])
@v2_permission_required("happy", "campaigns", "view")
def admin_get_campaign(campaign_id):
    repo = CampaignRepository()
    campaign = repo.get(campaign_id)
    if not campaign:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "campaign": jsonable(campaign),
        "audience": jsonable(repo.get_audience(campaign_id)),
        "quiz": jsonable(repo.get_quiz(campaign_id)),
    })


@happy_bp.route("/admin/campaigns/<int:campaign_id>", methods=["PUT"])
@v2_permission_required("happy", "campaigns", "edit")
def admin_update_campaign(campaign_id):
    body = request.get_json(silent=True) or {}
    repo = CampaignRepository()
    if not repo.get(campaign_id):
        return jsonify({"error": "not found"}), 404
    campaign = repo.update(campaign_id, body)
    try:
        if "audience" in body:
            repo.replace_audience(campaign_id, body["audience"])
        if "quiz" in body:
            repo.replace_quiz(campaign_id, body["quiz"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"campaign": jsonable(campaign)})


@happy_bp.route("/admin/campaigns/<int:campaign_id>/preview-audience", methods=["POST"])
@v2_permission_required("happy", "campaigns", "edit")
def admin_preview_audience(campaign_id):
    body = request.get_json(silent=True) or {}
    rules = body.get("audience")
    if rules is None:
        rules = CampaignRepository().get_audience(campaign_id)
    try:
        preview = CampaignRepository().preview_audience(rules)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(jsonable(preview))   # {count, cohorts:[{company,n}]} — no names


@happy_bp.route("/admin/campaigns/<int:campaign_id>/publish", methods=["POST"])
@v2_permission_required("happy", "campaigns", "publish")
def admin_publish_campaign(campaign_id):
    repo = CampaignRepository()
    campaign = repo.get(campaign_id)
    if not campaign:
        return jsonify({"error": "not found"}), 404
    errors = _validate_for_publish(campaign)
    if campaign.get("ack_mode") == "quiz" and not repo.get_quiz(campaign_id):
        errors.append("quiz ack_mode requires at least one quiz question")
    if errors:
        return jsonify({"error": "validation failed", "details": errors}), 400
    updated = repo.set_status(campaign_id, "live", current_user.id)
    targeted = repo.refresh_targets(campaign_id, prune=True)
    SurfaceRepository().audit("publish", campaign_id, current_user.id, {"targeted": targeted})
    return jsonify({"campaign": jsonable(updated), "targeted": targeted})


@happy_bp.route("/admin/campaigns/<int:campaign_id>/stats", methods=["GET"])
@v2_permission_required("happy", "campaigns", "view")
def admin_campaign_stats(campaign_id):
    repo = CampaignRepository()
    if not repo.get(campaign_id):
        return jsonify({"error": "not found"}), 404
    return jsonify(jsonable(repo.get_stats(campaign_id)))   # rollups only, never raw events


@happy_bp.route("/admin/health", methods=["GET"])
@v2_permission_required("happy", "admin", "manage")
def admin_health():
    return jsonify(jsonable(CampaignRepository().board_health()))


@happy_bp.route("/admin/campaigns/<int:campaign_id>/compliance-export", methods=["GET"])
@v2_permission_required("happy", "compliance", "export")
def admin_compliance_export(campaign_id):
    repo = CampaignRepository()
    if not repo.get(campaign_id):
        return jsonify({"error": "not found"}), 404
    rows = repo.compliance_export(campaign_id)
    # The one legitimate per-person export — every call is audited (spec §9.4).
    SurfaceRepository().audit("compliance_export", campaign_id, current_user.id, {"rows": len(rows)})
    return jsonify({"campaign_id": campaign_id, "acknowledgements": jsonable(rows)})


@happy_bp.route("/admin/campaigns/<int:campaign_id>/pause", methods=["POST"])
@v2_permission_required("happy", "campaigns", "publish")
def admin_pause_campaign(campaign_id):
    updated = CampaignRepository().set_status(campaign_id, "paused", current_user.id)
    if not updated:
        return jsonify({"error": "not found"}), 404
    return jsonify({"campaign": jsonable(updated)})
