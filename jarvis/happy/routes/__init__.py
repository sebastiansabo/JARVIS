"""Happy blueprint — one blueprint, employee + admin routes, mounted at /api/happy."""
from datetime import datetime, date

from flask import Blueprint

happy_bp = Blueprint("happy_bp", __name__)


def iso(value):
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def jsonable(row):
    """Shallow-convert a repo row (or list) so datetimes serialize as ISO strings."""
    if row is None:
        return None
    if isinstance(row, list):
        return [jsonable(r) for r in row]
    return {k: iso(v) for k, v in row.items()}


# Import route modules for their side effect of registering on happy_bp.
from happy.routes import surface, admin  # noqa: E402,F401
