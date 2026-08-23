"""Escalation ladder step-determination (spec §5.4). Pure and unit-testable.

Steps (relative to publication, then to the ack deadline):
  1  +48h   re-surface + push
  2  +5d    email to employee
  3  +7d    email to employee + direct manager
  4  deadline      non-dismissible on /app/hub + critical push
  5  deadline+3d   compliance-export row; no further employee-facing escalation

`due_step` returns the next step to fire (the smallest step past `last_step`
whose time has arrived), or 0 if nothing is due — so steps fire in order across
job runs and each fires at most once.

STUB — implementation follows the failing tests (TDD).
"""


from datetime import timedelta


def due_step(now, published_at, deadline_at, last_step):
    """Return the next escalation step (1..5) to fire now, or 0 if none is due.

    The smallest step greater than last_step whose trigger time has arrived, so
    steps fire in order across job runs and each fires at most once.
    """
    due = []
    if published_at:
        if now >= published_at + timedelta(hours=48):
            due.append(1)
        if now >= published_at + timedelta(days=5):
            due.append(2)
        if now >= published_at + timedelta(days=7):
            due.append(3)
    if deadline_at:
        if now >= deadline_at:
            due.append(4)
        if now >= deadline_at + timedelta(days=3):
            due.append(5)
    pending = [s for s in due if s > last_step]
    return min(pending) if pending else 0
