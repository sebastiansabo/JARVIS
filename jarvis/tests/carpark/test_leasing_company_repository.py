"""Mock-based unit tests for LeasingCompanyRepository — no real DB involved.

Mirrors test_autovit_listing_repository.py's mocking style: patches
`core.base_repository.get_db/get_cursor/release_db` (where BaseRepository's
module-level `from database import ...` binds them — patching `database.get_db`
directly would NOT be observed here) with a fake cursor that records every
`execute(sql, params)` call, then asserts on the generated SQL/params.

Added for Task 1 of the CarPark "Documente vânzare" plan: carpark_leasing_companies
is a GLOBAL directory (no company_id) of leasing companies — the "Cumpărător"
party for a sale-via-leasing contract.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock, patch

import pytest

from carpark.repositories.leasing_company_repository import LeasingCompanyRepository


class _FakeCursor:
    """Minimal cursor: every execute() is recorded; fetchone()/fetchall()
    return canned results so BaseRepository's dict_from_row() conversion has
    something to work with."""

    def __init__(self, one_result=None, all_results=None):
        self._one_result = one_result if one_result is not None else {'id': 1}
        self._all_results = all_results if all_results is not None else []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._one_result

    def fetchall(self):
        return self._all_results


def _run_create(data, created_by=1, cursor=None):
    cursor = cursor or _FakeCursor()
    with patch('core.base_repository.get_db', return_value=MagicMock()), \
         patch('core.base_repository.get_cursor', return_value=cursor), \
         patch('core.base_repository.release_db'):
        LeasingCompanyRepository().create(data, created_by)
    return cursor.executed[0]  # (sql, params)


def test_create_whitelists_fields_and_sets_created_by():
    """A non-whitelisted key (e.g. company_id -- this directory is GLOBAL)
    must be dropped, while every whitelisted field passed plus created_by
    must appear in the generated INSERT's column list and params."""
    sql, params = _run_create({
        'name': 'Leasing SA',
        'cui': 'RO123456',
        'company_id': 999,  # not a real column on this global table
    }, created_by=7)

    insert_cols = sql.split('(', 2)[1].split(')')[0]  # "name, cui, created_by"
    assert 'name' in insert_cols
    assert 'cui' in insert_cols
    assert 'created_by' in insert_cols
    assert 'company_id' not in insert_cols
    assert 'company_id' not in sql
    assert 'Leasing SA' in params
    assert 'RO123456' in params
    assert 7 in params


def test_list_all_returns_rows():
    rows = [{'id': 1, 'name': 'Leasing A'}, {'id': 2, 'name': 'Leasing B'}]
    cursor = _FakeCursor(all_results=rows)
    with patch('core.base_repository.get_db', return_value=MagicMock()), \
         patch('core.base_repository.get_cursor', return_value=cursor), \
         patch('core.base_repository.release_db'):
        result = LeasingCompanyRepository().list_all()

    assert result == rows
    sql, _ = cursor.executed[0]
    assert 'FROM carpark_leasing_companies' in sql
    assert 'ORDER BY name' in sql


def test_create_requires_name():
    with pytest.raises(ValueError):
        LeasingCompanyRepository().create({'cui': 'RO123456'}, created_by=1)
