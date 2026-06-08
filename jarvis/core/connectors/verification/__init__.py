"""Verification connector — cross-source data consistency checks (Sincron vs BioStar vs JARVIS)."""

from flask import Blueprint

verification_bp = Blueprint(
    'verification',
    __name__,
    url_prefix='/verification',
)

from . import routes  # noqa: F401, E402

__all__ = ['verification_bp']
