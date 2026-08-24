"""Pure rental-pricing math for Service ("Mașini de curtoazie") courtesy-car
sessions. No DB access — inputs are plain dicts/datetimes so this is fully
unit-testable. Mirrors a simple rent-a-car pricing model: day rate under 30
days, month rate (ceil'd) at 30 days and beyond. Advisor may override the
computed snapshot before it is persisted; this module only produces the
initial suggestion."""
from datetime import datetime
from math import ceil

# Policy fields resolved car-value-first, falling back to the per-company
# default. Maps the resolved (short) key to the vehicle/company_policy
# column name they are both stored under.
_POLICY_FIELDS = (
    ('km_included_day', 'svc_km_included_day'),
    ('extra_km_eur', 'svc_extra_km_eur'),
    ('deposit_eur', 'svc_deposit_eur'),
    ('franchise_eur', 'svc_franchise_eur'),
)


def _as_datetime(value):
    """Accept a datetime as-is, or parse an ISO string (tolerating a
    trailing 'Z', which datetime.fromisoformat rejects on its own).
    Normalize to naive wall-clock (drop tzinfo) so a tz-aware parsed string
    and a naive datetime remain comparable — JARVIS TD datetimes are naive
    wall-clock by convention."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value[:-1] + '+00:00' if value.endswith('Z') else value
        dt = datetime.fromisoformat(text)
    else:
        raise TypeError(f'Expected datetime or ISO string, got {type(value)!r}')
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def rental_days(departure, return_dt) -> int:
    """Whole rental days between two datetimes: ceil of the hour span / 24,
    with a floor of 1 (a same-day or reversed span still bills one day)."""
    start = _as_datetime(departure)
    end = _as_datetime(return_dt)
    hours = (end - start).total_seconds() / 3600
    if hours <= 0:
        return 1
    return max(1, ceil(hours / 24))


def resolve_policy(vehicle: dict, company_policy: dict) -> dict:
    """Resolve each policy field as: vehicle value if not None, else the
    company default, else None."""
    vehicle = vehicle or {}
    company_policy = company_policy or {}
    resolved = {}
    for short_key, column in _POLICY_FIELDS:
        value = vehicle.get(column)
        if value is None:
            value = company_policy.get(column)
        resolved[short_key] = value
    return resolved


def compute_service_pricing(vehicle: dict, company_policy: dict, departure, return_dt) -> dict:
    """Compute the rent-a-car style pricing snapshot for a Service session."""
    vehicle = vehicle or {}
    days = rental_days(departure, return_dt)
    is_month = days >= 30
    basis = 'month' if is_month else 'day'
    units = ceil(days / 30) if is_month else days

    rate = (vehicle.get('svc_tariff_eur_month') if is_month else vehicle.get('svc_tariff_eur_day')) or 0
    total = round(rate * units, 2)

    policy = resolve_policy(vehicle, company_policy)

    return {
        'svc_rate_basis': basis,
        'svc_tariff_eur': rate,
        'svc_units': units,
        'svc_total_eur': total,
        'svc_km_included_day': policy['km_included_day'],
        'svc_extra_km_eur': policy['extra_km_eur'],
        'svc_garantie_eur': policy['deposit_eur'],
        'svc_fransiza_eur': policy['franchise_eur'],
    }
