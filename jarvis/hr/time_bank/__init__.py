"""HR Time Bank module.

Append-only ledger for employee bonus hours (credits/debits).
Credits come from marketing events, manual entries, and T0 imports.
Debits come from leave permits, Connecteam, and CO conversions.
"""

from flask import Blueprint

time_bank_bp = Blueprint('time_bank', __name__)

from . import routes  # noqa: E402, F401

__all__ = ['time_bank_bp']
