"""Bilant (Balance Sheet) Generator — sub-module of Accounting.

Converts Trial Balance (Balanta) uploads into standardized Balance Sheets (Bilant)
with configurable templates, per-company scoping, and financial ratio analytics.
"""
from flask import Blueprint

bilant_bp = Blueprint('bilant', __name__)

from . import routes  # noqa: E402, F401
