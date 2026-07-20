import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
from foi_parcurs.repositories.dealer_config_repository import DealerConfigRepository


def test_get_general_conditions_returns_text():
    repo = DealerConfigRepository()
    repo.query_one = MagicMock(return_value={'general_conditions': '## Titlu\n\ntext'})
    out = repo.get_general_conditions(5, 'MG Motor')
    assert out == '## Titlu\n\ntext'
    sql, params = repo.query_one.call_args[0]
    assert 'fp_dealer_config' in sql and 'general_conditions' in sql
    assert params == (5, 'MG Motor')


def test_get_general_conditions_empty_when_none():
    repo = DealerConfigRepository()
    repo.query_one = MagicMock(return_value=None)
    assert repo.get_general_conditions(5, 'MG Motor') == ''
    repo.query_one = MagicMock(return_value={'general_conditions': None})
    assert repo.get_general_conditions(5, 'MG Motor') == ''
