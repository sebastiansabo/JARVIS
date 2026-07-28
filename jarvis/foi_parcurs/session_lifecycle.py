"""Single source of truth for the Test Drive session lifecycle.

A PLANNED row is 'planned' until its departure; 'late' during the GRACE_HOURS
window after a missed start; 'missed' once GRACE_HOURS have elapsed. The same
rule is expressed as a SQL fragment (TD_STATUS_SQL) for the list/detail queries
and as a pure Python helper (derive_planned_substatus) for the sweeper job.
"""
from datetime import timedelta

GRACE_HOURS = 8


def derive_planned_substatus(departure_dt, now):
    """Sub-status of a PLANNED row: 'planned' | 'late' | 'missed'."""
    if departure_dt is None:
        return 'planned'
    if now >= departure_dt + timedelta(hours=GRACE_HOURS):
        return 'missed'
    if now >= departure_dt:
        return 'late'
    return 'planned'


# Derived status for Test Drive rows, evaluated missed → late → planned before
# the FILLED-era branches so an unactivated draft is never mislabeled 'driving'.
TD_STATUS_SQL = (
    "CASE "
    "WHEN fp.status = 'COMPLETED' THEN 'complete' "
    "WHEN fp.status = 'MISSED' THEN 'missed' "
    f"WHEN fp.status = 'PLANNED' AND fp.departure_datetime + INTERVAL '{GRACE_HOURS} hours' < NOW() THEN 'missed' "
    "WHEN fp.status = 'PLANNED' AND fp.departure_datetime < NOW() THEN 'late' "
    "WHEN fp.status = 'PLANNED' THEN 'planned' "
    "WHEN fp.return_datetime IS NOT NULL AND fp.return_datetime < NOW() THEN 'incomplete' "
    "ELSE 'driving' "
    "END AS td_status"
)
