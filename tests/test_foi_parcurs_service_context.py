"""Pure-logic units for the Foi de Parcurs Service context."""
import os, sys
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from foi_parcurs.document_types import SALES, SERVICE, normalize, pools_match


class TestDocumentTypes:
    def test_normalize_valid(self):
        assert normalize('service') == SERVICE
        assert normalize('sales') == SALES

    def test_normalize_unknown_defaults_to_sales(self):
        assert normalize('') == SALES
        assert normalize(None) == SALES
        assert normalize('bogus') == SALES

    def test_pools_match(self):
        assert pools_match('service', 'service') is True
        assert pools_match('sales', 'sales') is True

    def test_pools_mismatch(self):
        assert pools_match('service', 'sales') is False
        assert pools_match('sales', 'service') is False

    def test_pools_match_normalizes_blanks(self):
        # a legacy/blank vehicle pool is treated as 'sales'
        assert pools_match('sales', None) is True
        assert pools_match('service', None) is False
