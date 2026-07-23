"""360° Employee Evaluation module.

Multi-rater (self / manager / peer / direct-report / external) evaluation cycles.
See docs/360/jarvis-360-module-spec.md (behavior) and
docs/360/jarvis2-360-indicators.json (metrics). HR admin surface is status-only;
the employee & manager evaluation UX lives in the web hub + mobile.
"""
from flask import Blueprint

eval360_bp = Blueprint('evaluation360', __name__, url_prefix='/hr/evaluation360')

from . import routes  # noqa: E402,F401  (registers routes on the blueprint)
