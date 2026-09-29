"""Change detection for the vehicle audit trail.

The editor submits the whole form (~90 fields) on every save, so a naive
``str(old) != str(new)`` comparison flags fields as changed purely on
type/format differences the round-trip introduces — a DB ``Decimal('45000.00')``
vs the form's ``45000``, or a ``DATE`` column's ``date`` object vs the form's
``'2020-01-01'`` string. That logged dozens of spurious modification-history
rows (each its own INSERT/commit) on every save. ``value_changed`` normalizes
those away so only genuine changes are recorded.
"""
import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _as_decimal(v: Any):
    """v as a Decimal when it's a number or a clean numeric string, else None.
    Bools are deliberately excluded — a flag flip must never look numeric."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float, Decimal)):
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError):
            return None
    return None


def _normalize(v: Any) -> Any:
    """Canonicalize dates/datetimes to their ISO string for comparison."""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return v


def value_changed(old: Any, new: Any) -> bool:
    """True iff old and new represent a genuinely different value.

    Ignores type/format noise from a full-form re-save: numeric values are
    compared as Decimals (``Decimal('45000.00') == 45000 == '45000'``) and
    date/datetime objects are compared by ISO string (``date(2020,1,1) ==
    '2020-01-01'``). Bools are never treated as numbers.
    """
    if old is None and new is None:
        return False
    if (old is None) != (new is None):
        return True

    old_dec, new_dec = _as_decimal(old), _as_decimal(new)
    if old_dec is not None and new_dec is not None:
        return old_dec != new_dec

    return str(_normalize(old)) != str(_normalize(new))
