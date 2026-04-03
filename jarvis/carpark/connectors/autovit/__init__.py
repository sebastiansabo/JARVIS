"""Autovit.ro connector — Dealer API integration."""
from flask import Blueprint

autovit_bp = Blueprint('autovit', __name__, url_prefix='/autovit')

from . import routes  # noqa: E402, F401

__all__ = ['autovit_bp']
