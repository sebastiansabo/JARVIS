"""First-party integrations blueprint.

Hosts narrowly-scoped, first-party integration endpoints that let other
Autoworld-owned applications authenticate and authorize against JARVIS, which
remains the single source of truth for identity and authorization.

Currently exposes the JARVIS alpha | BUSINESS CONTROL authorization contract
(``GET /api/integrations/business-control/authorize``).
"""
from flask import Blueprint

integrations_bp = Blueprint('integrations', __name__)

# Import routes to attach view functions to the blueprint. Kept at the bottom to
# avoid a circular import (routes import ``integrations_bp`` from this module).
from core.integrations import routes  # noqa: E402,F401
