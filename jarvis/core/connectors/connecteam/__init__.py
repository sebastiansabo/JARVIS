"""Connecteam Connector — Leave permission form submissions via webhook."""

from flask import Blueprint

connecteam_bp = Blueprint(
    'connecteam',
    __name__,
    url_prefix='/connecteam',
)

from . import routes  # noqa: F401, E402

__all__ = ['connecteam_bp']
