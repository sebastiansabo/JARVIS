"""JARVIS Foi de Parcurs — Test Drive & Comodat contract generation.

Manages route sheets (foi de parcurs) for vehicle test drives and comodat
agreements, including fuel distribution, odometer tracking, and client management.
"""
from flask import Blueprint

foi_parcurs_bp = Blueprint('foi_parcurs', __name__)

from . import routes  # noqa: E402, F401
