"""Smoke test: the Happy blueprint imports and registers its routes.

Runs under the DB-driver mock in jarvis/conftest.py, so importing the blueprint
(which pulls BaseRepository -> database) does not touch a real DB.
"""
from flask import Flask


def test_happy_bp_registers_expected_rules():
    from happy.routes import happy_bp

    app = Flask(__name__)
    app.register_blueprint(happy_bp, url_prefix="/api/happy")
    rules = {r.rule for r in app.url_map.iter_rules()}

    expected = {
        "/api/happy/surface",
        "/api/happy/events",
        "/api/happy/campaigns/<int:campaign_id>/ack",
        "/api/happy/campaigns/<int:campaign_id>/snooze",
        "/api/happy/campaigns/<int:campaign_id>/dismiss",
        "/api/happy/inbox",
        "/api/happy/admin/campaigns",
        "/api/happy/admin/campaigns/<int:campaign_id>/publish",
        "/api/happy/admin/campaigns/<int:campaign_id>/preview-audience",
    }
    missing = expected - rules
    assert not missing, f"missing routes: {missing}"
