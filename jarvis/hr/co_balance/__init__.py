"""HR CO (Concediu de odihnă) Balance module.

Imports per-year leave-balance snapshots from HR's
`Raport_concedii_contracte_lunar - <COMPANY>.xlsx` files and exposes the 5
static inputs per employee. Used YTD and remaining balance are computed on
read from Sincron timesheets (source of truth for days actually taken).
"""

from flask import Blueprint

co_balance_bp = Blueprint('co_balance', __name__)

from . import routes  # noqa: E402, F401

__all__ = ['co_balance_bp']
