"""Sincron HR Connector — Timesheet data integration from Sincron API."""

from flask import Blueprint

sincron_bp = Blueprint(
    'sincron',
    __name__,
    url_prefix='/sincron',
)

from . import routes  # noqa: F401, E402

__all__ = ['sincron_bp']
