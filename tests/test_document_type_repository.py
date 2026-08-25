"""Unit tests for DocumentTypeRepository (fp_document_types).

- slugify: diacritics → ascii, symbols → dashes, empty → 'tip'
- add: blank label rejected; slug deduped against existing keys
- upsert: the default (sales) row is immutable; blank label rejected
"""
import os
import sys

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from foi_parcurs.repositories.document_type_repository import (
    DocumentTypeRepository, slugify,
)


class TestSlugify:
    def test_romanian_diacritics_become_ascii(self):
        assert slugify('Mașini de curtoazie') == 'masini-de-curtoazie'

    def test_symbols_and_spaces_collapse_to_dashes(self):
        assert slugify('  Contract / Închiriere!! ') == 'contract-inchiriere'

    def test_blank_falls_back_to_tip(self):
        assert slugify('') == 'tip'
        assert slugify('!!!') == 'tip'


class TestAdd:
    def test_blank_label_rejected(self):
        repo = DocumentTypeRepository()
        with pytest.raises(ValueError):
            repo.add(11, '   ')

    def test_dedupes_slug_against_existing_keys(self):
        repo = DocumentTypeRepository()
        repo.list_for_company = MagicMock(return_value=[
            {'key': 'sales', 'sort_order': 0}, {'key': 'comodat', 'sort_order': 1},
        ])
        repo.execute = MagicMock()
        key = repo.add(11, 'Comodat')
        assert key == 'comodat-2'
        # the generated key is what gets inserted
        args = repo.execute.call_args[0][1]
        assert 'comodat-2' in args


class TestUpsert:
    def test_default_row_is_immutable(self):
        repo = DocumentTypeRepository()
        repo.get = MagicMock(return_value={'key': 'sales', 'is_default': True})
        repo.execute = MagicMock()
        with pytest.raises(ValueError):
            repo.upsert(11, 'sales', 'Vânzări', None, None, None)
        repo.execute.assert_not_called()

    def test_blank_label_rejected(self):
        repo = DocumentTypeRepository()
        repo.get = MagicMock(return_value={'key': 'service', 'is_default': False})
        with pytest.raises(ValueError):
            repo.upsert(11, 'service', '', 't', 'b', 'c')

    def test_updates_a_regular_type(self):
        repo = DocumentTypeRepository()
        repo.get = MagicMock(return_value={'key': 'service', 'is_default': False})
        repo.execute = MagicMock()
        repo.upsert(11, 'service', 'Mașini de curtoazie', 'T', 'B', 'C', is_rental=True, is_active=True)
        repo.execute.assert_called_once()
        params = repo.execute.call_args[0][1]
        assert params[1] == 'service' and params[2] == 'Mașini de curtoazie'
        assert params[6] is True  # is_rental


class TestDelete:
    def test_default_cannot_be_deleted(self):
        repo = DocumentTypeRepository()
        repo.get = MagicMock(return_value={'key': 'sales', 'is_default': True})
        repo.execute = MagicMock()
        with pytest.raises(ValueError):
            repo.delete(11, 'sales')
        repo.execute.assert_not_called()

    def test_in_use_type_cannot_be_deleted(self):
        repo = DocumentTypeRepository()
        repo.get = MagicMock(return_value={'key': 'service', 'is_default': False})
        repo.query_one = MagicMock(return_value={'veh': 3, 'ses': 0})
        repo.execute = MagicMock()
        with pytest.raises(ValueError):
            repo.delete(11, 'service')
        repo.execute.assert_not_called()

    def test_deletes_unused_non_default(self):
        repo = DocumentTypeRepository()
        repo.get = MagicMock(return_value={'key': 'comodat', 'is_default': False})
        repo.query_one = MagicMock(return_value={'veh': 0, 'ses': 0})
        repo.execute = MagicMock()
        repo.delete(11, 'comodat')
        repo.execute.assert_called_once()
        assert 'DELETE' in repo.execute.call_args[0][0]

    def test_missing_type_is_noop(self):
        repo = DocumentTypeRepository()
        repo.get = MagicMock(return_value=None)
        repo.execute = MagicMock()
        repo.delete(11, 'ghost')  # no raise
        repo.execute.assert_not_called()
