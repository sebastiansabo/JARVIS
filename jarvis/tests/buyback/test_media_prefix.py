"""Media proxy allowlist regression: the buyback module's Spaces prefix must
be servable through the authenticated /api/media/<key> proxy (core/media/
routes.py), so buyback photo galleries can render like carpark's do.

Pure — no DB, no Flask client — just asserts the constant.
"""
from core.media import routes as m


def test_buyback_prefix_allowed():
    assert 'private/buyback/' in m._ALLOWED_PREFIXES
