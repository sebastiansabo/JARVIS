"""Tests for the Weekly Driving Digest service (jarvis/foi_parcurs/services/driving_digest_service.py).

Unit tests only — no DB. psycopg2 is mocked by jarvis/conftest.py, and every
collaborator (repos, LLM client, email/notify infra) is monkeypatched at the
module level, mirroring tests/foi_parcurs/test_reports.py.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
from datetime import datetime
from foi_parcurs.services import driving_digest_service as dds


# --- Task 1: week-range helper ---------------------------------------------

def test_week_range_previous_mon_to_sun():
    # Wednesday 2026-08-26 → previous week Mon 2026-08-17 .. Sun 2026-08-23
    frm, to = dds._week_range(datetime(2026, 8, 26, 9, 0))
    assert frm == '2026-08-17'
    assert to == '2026-08-23'


def test_week_range_on_monday_uses_prior_week():
    # Monday 2026-08-24 → previous week Mon 2026-08-17 .. Sun 2026-08-23
    frm, to = dds._week_range(datetime(2026, 8, 24, 8, 0))
    assert frm == '2026-08-17'
    assert to == '2026-08-23'
