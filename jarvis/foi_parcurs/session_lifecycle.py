"""Single source of truth for the Test Drive session lifecycle.

A PLANNED row is 'planned' until its departure; 'late' during the GRACE_HOURS
window after a missed start; 'missed' once GRACE_HOURS have elapsed. The same
rule is expressed as a SQL fragment (TD_STATUS_SQL) for the list/detail queries
and as a pure Python helper (derive_planned_substatus) for the sweeper job.
"""
from datetime import timedelta

# A no-show is archived (PLANNED→MISSED) once this grace window elapses after the
# scheduled departure. Drives TD_STATUS_SQL, the archive sweeper, and conflicts.
GRACE_HOURS = 6

# TD datetimes are naive Bucharest wall-clock (stored as digits, displayed
# as-is) even though the columns are timestamptz. Production's DB session runs
# in UTC, so comparing them against bare NOW() fires ~2-3h late there (NOW()
# would be a UTC instant, not the Bucharest wall-clock the row was written
# with). Every SQL comparison against "now" for these columns must therefore
# go through this local-wall-clock expression instead of bare NOW() — mirrors
# the same compensation record_return already applies to its auto return time.
NOW_LOCAL_SQL = "(NOW() AT TIME ZONE 'Europe/Bucharest')::timestamptz"


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
    f"WHEN fp.status = 'PLANNED' AND fp.departure_datetime + INTERVAL '{GRACE_HOURS} hours' < {NOW_LOCAL_SQL} THEN 'missed' "
    f"WHEN fp.status = 'PLANNED' AND fp.departure_datetime < {NOW_LOCAL_SQL} THEN 'late' "
    "WHEN fp.status = 'PLANNED' THEN 'planned' "
    f"WHEN fp.return_datetime IS NOT NULL AND fp.return_datetime < {NOW_LOCAL_SQL} THEN 'incomplete' "
    "ELSE 'driving' "
    "END AS td_status"
)
