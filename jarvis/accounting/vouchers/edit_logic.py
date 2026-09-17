"""Pure logic for an admin full-edit of a voucher.

Kept free of Flask and DB access so every branch is unit-testable directly.
The route layer loads the existing row, calls :func:`build_admin_voucher_edit`,
persists the returned column updates, and writes the audit diff.

``build_admin_voucher_edit(existing, payload)`` returns ``(updates, changes)``:
  * ``updates`` maps DB column -> new value, ready for a parameterised UPDATE.
  * ``changes`` maps column -> ``{'old': .., 'new': ..}`` for the fields whose
    value actually changed (JSON-safe), for the audit log. Fields that resolve
    to the same value they already held are omitted.
"""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from accounting.vouchers.repositories import compute_voucher_dates

VALID_STATUSES = (
    'draft', 'pending_approval', 'approved', 'active',
    'rejected', 'redeemed', 'expired', 'archived',
)
VALID_TYPES = ('value', 'accessory_discount_code', 'accessory_percentage', 'service_items')
VALID_VALIDITY = (1, 3, 6, 12, 24, 36, 48)

# voucher_type -> the single benefit column it uses
BENEFIT_FIELD = {
    'value': 'value_lei',
    'accessory_discount_code': 'discount_code',
    'accessory_percentage': 'discount_percentage',
    'service_items': 'service_items',
}
ALL_BENEFIT_FIELDS = ('value_lei', 'discount_code', 'discount_percentage', 'service_items')

# Plain text columns copied straight through (trimmed).
TEXT_FIELDS = ('client_name', 'contract_number', 'notes', 'redemption_notes',
               'client_email', 'client_cif')
NULLABLE_TEXT = ('notes', 'redemption_notes', 'client_email', 'client_cif')
DATE_FIELDS = ('start_date', 'issued_at', 'expires_at')


def _to_date(v):
    if v in (None, ''):
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _to_decimal(v):
    if v in (None, ''):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        raise ValueError(f'Invalid numeric value: {v!r}')


def _coerce_benefit(field: str, value):
    """Coerce a benefit payload value to its DB representation."""
    if field == 'value_lei':
        return _to_decimal(value)
    if field == 'discount_percentage':
        d = _to_decimal(value)
        if d is not None and (d < 0 or d > 100):
            raise ValueError('discount_percentage must be between 0 and 100')
        return d
    if field == 'discount_code':
        if value in (None, ''):
            return None
        return str(value).strip()
    if field == 'service_items':
        if not value:
            return None
        if isinstance(value, str):
            value = json.loads(value)
        return list(value)
    return value


def _json_safe(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def _norm(v):
    """Normalise a value for equality comparison between old and new.

    Decimals compare numerically (500 == 500.00); a JSON-string list is
    parsed so it matches the coerced list; everything else compares as-is.
    """
    if isinstance(v, str):
        stripped = v.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            try:
                return json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                return v
    return v


def build_admin_voucher_edit(existing: dict, payload: dict) -> tuple[dict, dict]:
    """Compute column updates and the audit diff for an admin voucher edit.

    Raises ``ValueError`` on any invalid enum / VIN / numeric value.
    """
    updates: dict = {}

    # --- plain text ---
    for f in TEXT_FIELDS:
        if f in payload:
            val = payload[f]
            val = val.strip() if isinstance(val, str) else val
            updates[f] = val
    if 'client_cif' in updates and isinstance(updates['client_cif'], str):
        updates['client_cif'] = updates['client_cif'].upper()
    for f in NULLABLE_TEXT:
        if updates.get(f) == '':
            updates[f] = None

    # --- VIN (validated when non-empty) ---
    if 'car_vin' in payload:
        vin = (payload['car_vin'] or '').strip().upper()
        if vin and not re.fullmatch(r'[A-Z0-9]{17}', vin):
            raise ValueError('VIN must be exactly 17 alphanumeric characters')
        updates['car_vin'] = vin

    # --- validity ---
    if 'validity_months' in payload:
        v = int(payload['validity_months'])
        if v not in VALID_VALIDITY:
            raise ValueError('validity_months must be 1, 3, 6, 12, 24, 36, or 48')
        updates['validity_months'] = v

    # --- type + benefit ---
    if 'voucher_type' in payload:
        vt = payload['voucher_type']
        if vt not in VALID_TYPES:
            raise ValueError(f'voucher_type must be one of {VALID_TYPES}')
        updates['voucher_type'] = vt
        matching = BENEFIT_FIELD[vt]
        if matching in payload:
            updates[matching] = _coerce_benefit(matching, payload[matching])
        # A type change must clear the other three benefit columns so the row
        # stays consistent (only one benefit field is meaningful per type).
        for other in ALL_BENEFIT_FIELDS:
            if other != matching:
                updates[other] = None
    else:
        for f in ALL_BENEFIT_FIELDS:
            if f in payload:
                updates[f] = _coerce_benefit(f, payload[f])

    # --- dates ---
    for f in DATE_FIELDS:
        if f in payload:
            updates[f] = _to_date(payload[f])

    # --- status (with date fill on activate) ---
    if 'status' in payload:
        st = payload['status']
        if st not in VALID_STATUSES:
            raise ValueError(f'status must be one of {VALID_STATUSES}')
        updates['status'] = st
        if st == 'active':
            final_issued = updates.get('issued_at', existing.get('issued_at'))
            if not final_issued:
                start = updates.get('start_date', existing.get('start_date'))
                validity = updates.get('validity_months', existing.get('validity_months'))
                issued, expires = compute_voucher_dates(start, validity)
                updates['issued_at'] = issued
                updates['expires_at'] = expires

    # --- audit diff (only genuinely-changed columns) ---
    changes: dict = {}
    for k, new_val in updates.items():
        old_val = existing.get(k)
        if _norm(old_val) != _norm(new_val):
            changes[k] = {'old': _json_safe(old_val), 'new': _json_safe(new_val)}

    return updates, changes
