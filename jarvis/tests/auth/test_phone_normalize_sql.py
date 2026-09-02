"""Verifies the fn_normalize_phone SQL function and the users.phone_normalized
generated column exist and normalize Romanian numbers to 40XXXXXXXXX.

Requires a real, reachable Postgres (localhost/defaultdb by default) —
this test proves actual SQL execution (an IMMUTABLE plpgsql function backing
a STORED generated column), which cannot be meaningfully exercised against a
mock. jarvis/conftest.py replaces psycopg2 with a MagicMock for the rest of
the suite so unit tests don't need a live DB; under that mock,
cursor.execute() never raises and dict_from_row() on a MagicMock row
silently degrades (missing/empty dict) instead of erroring, so we detect
that condition by checking the *value* of a known-good query and skip rather
than asserting on it (mirrors tests/foi_parcurs/test_session_lifecycle_tz.py's
_real_repo_or_skip idiom).

To actually exercise this test against a real DB, bypass the ancestor
conftest.py's mock via --confcutdir, e.g.:

    DATABASE_URL=postgresql://localhost/defaultdb \\
      python -m pytest tests/auth/test_phone_normalize_sql.py \\
      --confcutdir=tests/auth -v
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from core.base_repository import BaseRepository


def _repo_or_skip():
    """Return a BaseRepository backed by a genuine DB connection, or skip.
    A mocked psycopg2 (this suite's normal conftest.py setup) makes
    query_one('SELECT 1 AS one') come back as {} rather than {'one': 1} —
    dict_from_row() on a MagicMock row silently degrades instead of
    raising, so we must check the *value*, not just catch exceptions."""
    repo = BaseRepository()
    try:
        row = repo.query_one('SELECT 1 AS one')
    except Exception as e:
        pytest.skip(f'DB unavailable: {e}')
        return None
    if not row or row.get('one') != 1:
        pytest.skip(
            'DB unavailable for this test (psycopg2 appears mocked in this '
            'pytest session) — run with --confcutdir=tests/auth to bypass '
            'the top-level conftest.py mock and hit a real Postgres'
        )
    return repo


@pytest.fixture(scope='module')
def repo():
    return _repo_or_skip()


@pytest.mark.parametrize('raw,expected', [
    ('0723574040', '40723574040'),
    ('40723574040', '40723574040'),
    ('+40 723 574 040', '40723574040'),
    ('0040723574040', None),  # 00-prefix unsupported (parity with normalize_phone)
    ('723574040', '40723574040'),
    ('abc', None),
    ('0723', None),
    ('', None),
    (None, None),
])
def test_fn_normalize_phone(repo, raw, expected):
    row = repo.query_one('SELECT fn_normalize_phone(%s) AS n', (raw,))
    assert row['n'] == expected


def test_phone_normalized_column_exists(repo):
    row = repo.query_one('''
        SELECT 1 AS ok FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'phone_normalized'
    ''')
    assert row is not None
