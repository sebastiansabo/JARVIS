"""JARVIS Parc — logistics / yard-ops module.

Mirrors `jarvis/carpark/` (repositories/, routes/, services/). Own schema
(`jarvis/migrations/domains/schema_logistics.py`), own tables
(`logistics_*`), never writes another module's tables. See
docs/superpowers/specs/2026-11-27-jarvis-parc-design.md for the full design.

Blueprint: logistics_bp, mounted with NO url_prefix (unlike carpark_bp) —
routes under jarvis/logistics/routes/ declare their own full
`/api/logistics/...` paths, since the intake endpoints are the
server-to-server jarvis-alpha feed surface rather than the browser-facing
carpark UI API.
"""
from flask import Blueprint

logistics_bp = Blueprint('logistics', __name__)

# Import routes to register them on the blueprint
from .routes import intake  # noqa: F401, E402
from .routes import vehicles  # noqa: F401, E402
