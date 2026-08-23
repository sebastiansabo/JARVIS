"""Smoke test: the Happy mobile JWT twin imports and registers its routes."""
from flask import Flask


def test_happy_mobile_bp_registers_expected_rules():
    from happy.routes.mobile import happy_mobile_bp

    app = Flask(__name__)
    app.register_blueprint(happy_mobile_bp, url_prefix="/api/mobile/happy")
    rules = {r.rule for r in app.url_map.iter_rules()}

    expected = {
        "/api/mobile/happy/surface",
        "/api/mobile/happy/events",
        "/api/mobile/happy/campaigns/<int:campaign_id>/ack",
        "/api/mobile/happy/inbox",
        "/api/mobile/happy/praise/kudos",
        "/api/mobile/happy/praise/wallet",
        "/api/mobile/happy/pulse/current",
        "/api/mobile/happy/pulse/<int:pulse_id>/respond",
    }
    missing = expected - rules
    assert not missing, f"missing mobile routes: {missing}"
