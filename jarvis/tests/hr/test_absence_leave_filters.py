"""Test that cancelled/rejected leaves are excluded from absence counting in the
two remaining bilet-de-invoire form_submissions (fs) reads found in FINAL-REVIEW:
  - core/connectors/biostar/services/pontaje_export_service.py (_fetch_permits, JARVIS branch)
  - hr/events/routes/employees.py (JARVIS branch)

Mirrors jarvis/tests/hr/test_employee_overview_leave_filter.py.
"""
import pathlib

# cwd-independent: from jarvis/tests/hr/<file>, parents[2] == jarvis/
JARVIS_ROOT = pathlib.Path(__file__).resolve().parents[2]

PONTAJE_SRC = (JARVIS_ROOT / 'core' / 'connectors' / 'biostar' / 'services'
               / 'pontaje_export_service.py').read_text()
EMPLOYEES_SRC = (JARVIS_ROOT / 'hr' / 'events' / 'routes' / 'employees.py').read_text()


def test_pontaje_export_bilet_de_invoire_read_excludes_cancelled_and_rejected():
    """_fetch_permits' JARVIS branch must exclude cancelled+rejected leaves,
    mirroring the sibling Connecteam branch's status filter.
    """
    assert "fs.status NOT IN ('cancelled', 'rejected')" in PONTAJE_SRC


def test_pontaje_export_does_not_exclude_cancellation_pending():
    """A cancellation-pending leave is still in effect until approved — must NOT be
    excluded from the fs leave-status filter."""
    assert "fs.status NOT IN ('cancelled', 'rejected', 'cancellation_pending')" not in PONTAJE_SRC
    assert "cancellation_pending" not in PONTAJE_SRC


def test_employees_route_bilet_de_invoire_read_excludes_cancelled_and_rejected():
    """The JARVIS branch reading bilet-de-invoire submissions must exclude
    cancelled+rejected leaves, mirroring the sibling Connecteam branch's status filter.
    """
    assert "fs.status NOT IN ('cancelled', 'rejected')" in EMPLOYEES_SRC


def test_employees_route_does_not_exclude_cancellation_pending():
    """A cancellation-pending leave is still in effect until approved — must NOT be
    excluded from the fs leave-status filter."""
    assert "fs.status NOT IN ('cancelled', 'rejected', 'cancellation_pending')" not in EMPLOYEES_SRC
    assert "cancellation_pending" not in EMPLOYEES_SRC
