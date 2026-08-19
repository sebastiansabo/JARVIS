"""Test that cancelled/rejected leaves are excluded from absence counting."""
import pathlib

SRC = pathlib.Path('jarvis/hr/events/repositories/employee_overview_repository.py').read_text()


def test_both_form_submissions_leave_reads_exclude_cancelled_and_rejected():
    """There are two form_submissions (fs) reads joined to the bilet-de-invoire form;
    each must exclude cancelled+rejected (mirroring the sibling connecteam check).
    """
    assert SRC.count("fs.status NOT IN ('cancelled', 'rejected')") >= 2


def test_cancellation_pending_still_counts_as_absence():
    """A cancellation-pending leave is still in effect until approved — must NOT be
    excluded anywhere in the fs leave-status filters.
    """
    assert "fs.status NOT IN ('cancelled', 'rejected', 'cancellation_pending')" not in SRC
    assert "cancellation_pending" not in SRC
