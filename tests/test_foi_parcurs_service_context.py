"""Pure-logic units for the Foi de Parcurs Service context."""
import os, sys
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from foi_parcurs.document_types import SALES, SERVICE, normalize, pools_match
from foi_parcurs.services.contract_template import render_contract_template, PLACEHOLDERS


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


class TestContractTemplate:
    def test_substitutes_known_tokens(self):
        out = render_contract_template(
            'Client {client_name}, VIN {vin}, km {km_start}.',
            {'client_name': 'Ion Pop', 'vin': 'WVW123', 'km_start': 45000},
        )
        assert out == 'Client Ion Pop, VIN WVW123, km 45000.'

    def test_unknown_token_renders_literally(self):
        out = render_contract_template('Hi {not_a_token} there', {'client_name': 'X'})
        assert out == 'Hi {not_a_token} there'

    def test_missing_known_token_is_blank(self):
        out = render_contract_template('Ref: {service_order_ref}!', {})
        assert out == 'Ref: !'

    def test_service_order_ref_is_whitelisted(self):
        assert 'service_order_ref' in PLACEHOLDERS

    def test_none_template_is_empty_string(self):
        assert render_contract_template(None, {'vin': 'X'}) == ''
