"""Unit tests for Currency Converter module.

Tests for:
- currency_converter.py: BNR API integration, exchange rate fetching, currency conversion
"""
import sys
import os

# Set dummy DATABASE_URL before importing modules that require it
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from core.services.currency_converter import (
    get_exchange_rate,
    convert_currency,
    get_eur_ron_conversion,
    clear_cache,
    _parse_bnr_xml,
    _fetch_rates_for_year,
    BNR_CURRENT_URL,
    BNR_YEARLY_URL
)


# ============== SETUP/TEARDOWN ==============

@pytest.fixture(autouse=True)
def clear_rate_cache():
    """Clear cache before and after each test."""
    clear_cache()
    yield
    clear_cache()


# ============== EXCHANGE RATE TESTS ==============

class TestGetExchangeRate:
    """Tests for get_exchange_rate() function."""

    def test_ron_to_ron_always_1(self):
        """RON to RON should always be 1.0"""
        rate = get_exchange_rate('RON', '2025-12-15')
        assert rate == 1.0

    def test_ron_lowercase(self):
        """Should handle lowercase currency code"""
        rate = get_exchange_rate('ron', '2025-12-15')
        assert rate == 1.0

    def test_invalid_date_format(self):
        """Invalid date format should return None"""
        rate = get_exchange_rate('EUR', 'invalid-date')
        assert rate is None

    @patch('core.services.currency_converter._fetch_rates_for_year')
    def test_fetches_rate_from_api(self, mock_fetch):
        """Should fetch rate from BNR API"""
        mock_fetch.return_value = {
            '2025-12-15': {'EUR': 4.9700, 'USD': 4.7500}
        }

        rate = get_exchange_rate('EUR', '2025-12-15')

        assert rate == 4.9700
        mock_fetch.assert_called_once_with(2025)

    @patch('core.services.currency_converter._fetch_rates_for_year')
    def test_uses_cache(self, mock_fetch):
        """Should use cached rate on subsequent calls"""
        # Clear the cache first to ensure clean state
        from core.services import currency_converter
        currency_converter.clear_cache()

        # Mock that also updates the internal cache (like real function does)
        def mock_fetch_and_cache(year):
            rates = {'2025-12-15': {'EUR': 4.9700}}
            currency_converter._rate_cache[year] = rates
            return rates

        mock_fetch.side_effect = mock_fetch_and_cache

        # First call
        get_exchange_rate('EUR', '2025-12-15')
        # Second call should use cache
        get_exchange_rate('EUR', '2025-12-15')

        # Should only fetch once since cache is populated
        assert mock_fetch.call_count == 1

    @patch('core.services.currency_converter._fetch_rates_for_year')
    def test_fallback_to_previous_days(self, mock_fetch):
        """Should try previous days if rate not found (weekends/holidays)"""
        mock_fetch.return_value = {
            '2025-12-12': {'EUR': 4.9700},  # Friday
            # 13, 14 are weekend - no rates
        }

        # Saturday - should fall back to Friday
        rate = get_exchange_rate('EUR', '2025-12-13')

        assert rate == 4.9700

    @patch('core.services.currency_converter._fetch_rates_for_year')
    def test_returns_none_if_not_found(self, mock_fetch):
        """Should return None if rate not found after fallbacks"""
        mock_fetch.return_value = {}

        rate = get_exchange_rate('EUR', '2025-12-15')

        assert rate is None


# ============== XML PARSING TESTS ==============

class TestParseBnrXml:
    """Tests for _parse_bnr_xml() function."""

    def test_parses_valid_xml(self):
        """Should parse valid BNR XML format"""
        xml_content = b'''<?xml version="1.0" encoding="utf-8"?>
        <DataSet xmlns="http://www.bnr.ro/xsd">
            <Body>
                <Cube date="2025-12-15">
                    <Rate currency="EUR">4.9700</Rate>
                    <Rate currency="USD">4.7500</Rate>
                </Cube>
            </Body>
        </DataSet>'''

        result = _parse_bnr_xml(xml_content)

        assert '2025-12-15' in result
        assert result['2025-12-15']['EUR'] == 4.9700
        assert result['2025-12-15']['USD'] == 4.7500

    def test_handles_multiplier(self):
        """Should handle multiplier attribute (e.g., HUF per 100)"""
        xml_content = b'''<?xml version="1.0" encoding="utf-8"?>
        <DataSet xmlns="http://www.bnr.ro/xsd">
            <Body>
                <Cube date="2025-12-15">
                    <Rate currency="HUF" multiplier="100">1.2300</Rate>
                </Cube>
            </Body>
        </DataSet>'''

        result = _parse_bnr_xml(xml_content)

        # Should divide by multiplier
        assert result['2025-12-15']['HUF'] == 0.0123

    def test_handles_empty_cube(self):
        """Should handle cube with no rates"""
        xml_content = b'''<?xml version="1.0" encoding="utf-8"?>
        <DataSet xmlns="http://www.bnr.ro/xsd">
            <Body>
                <Cube date="2025-12-15">
                </Cube>
            </Body>
        </DataSet>'''

        result = _parse_bnr_xml(xml_content)

        assert '2025-12-15' not in result

    def test_handles_invalid_xml(self):
        """Should return empty dict for invalid XML"""
        result = _parse_bnr_xml(b'not valid xml')
        assert result == {}

    def test_skips_invalid_rate_values(self):
        """Should skip rates with invalid values"""
        xml_content = b'''<?xml version="1.0" encoding="utf-8"?>
        <DataSet xmlns="http://www.bnr.ro/xsd">
            <Body>
                <Cube date="2025-12-15">
                    <Rate currency="EUR">4.9700</Rate>
                    <Rate currency="USD">invalid</Rate>
                </Cube>
            </Body>
        </DataSet>'''

        result = _parse_bnr_xml(xml_content)

        assert result['2025-12-15']['EUR'] == 4.9700
        assert 'USD' not in result['2025-12-15']


# ============== CURRENCY CONVERSION TESTS ==============

class TestConvertCurrency:
    """Tests for convert_currency() function."""

    def test_same_currency_no_conversion(self):
        """Same currency should return original amount"""
        amount, rate = convert_currency(100.00, 'EUR', 'EUR', '2025-12-15')

        assert amount == 100.00
        assert rate == 1.0

    @patch('core.services.currency_converter.get_exchange_rate')
    def test_eur_to_ron(self, mock_rate):
        """Should convert EUR to RON correctly"""
        mock_rate.side_effect = lambda c, d: {'EUR': 4.97, 'RON': 1.0}.get(c)

        amount, rate = convert_currency(100.00, 'EUR', 'RON', '2025-12-15')

        assert amount == 497.00
        assert rate == 4.97

    @patch('core.services.currency_converter.get_exchange_rate')
    def test_ron_to_eur(self, mock_rate):
        """Should convert RON to EUR correctly"""
        mock_rate.side_effect = lambda c, d: {'EUR': 4.97, 'RON': 1.0}.get(c)

        amount, rate = convert_currency(497.00, 'RON', 'EUR', '2025-12-15')

        assert amount == 100.00
        assert round(rate, 6) == round(1 / 4.97, 6)

    @patch('core.services.currency_converter.get_exchange_rate')
    def test_returns_none_on_missing_rate(self, mock_rate):
        """Should return None if rate not available"""
        mock_rate.return_value = None

        amount, rate = convert_currency(100.00, 'XYZ', 'RON', '2025-12-15')

        assert amount is None
        assert rate is None


# ============== EUR RON CONVERSION TESTS ==============

class TestGetEurRonConversion:
    """Tests for get_eur_ron_conversion() function."""

    @patch('core.services.currency_converter.get_exchange_rate')
    def test_ron_invoice(self, mock_rate):
        """RON invoice should calculate EUR value"""
        mock_rate.return_value = 4.97

        result = get_eur_ron_conversion(1000.00, 'RON', '2025-12-15')

        assert result['value_ron'] == 1000.00
        assert result['value_eur'] == round(1000.00 / 4.97, 2)
        assert result['exchange_rate'] == 4.97
        assert result['original_currency'] == 'RON'

    @patch('core.services.currency_converter.get_exchange_rate')
    def test_eur_invoice(self, mock_rate):
        """EUR invoice should calculate RON value"""
        mock_rate.return_value = 4.97

        result = get_eur_ron_conversion(100.00, 'EUR', '2025-12-15')

        assert result['value_eur'] == 100.00
        assert result['value_ron'] == 497.00
        assert result['exchange_rate'] == 4.97

    @patch('core.services.currency_converter.get_exchange_rate')
    def test_usd_invoice(self, mock_rate):
        """USD invoice should convert through RON"""
        def rate_side_effect(currency, date):
            rates = {'EUR': 4.97, 'USD': 4.50, 'RON': 1.0}
            return rates.get(currency)

        mock_rate.side_effect = rate_side_effect

        result = get_eur_ron_conversion(100.00, 'USD', '2025-12-15')

        assert result['value_ron'] == 450.00  # 100 * 4.50
        assert result['value_eur'] == round(450.00 / 4.97, 2)

    @patch('core.services.currency_converter.get_exchange_rate')
    def test_missing_eur_rate(self, mock_rate):
        """Should return None values if EUR rate missing"""
        mock_rate.return_value = None

        result = get_eur_ron_conversion(100.00, 'RON', '2025-12-15')

        assert result['value_ron'] is None
        assert result['value_eur'] is None

    def test_preserves_rate_date(self):
        """Should preserve the requested date"""
        with patch('core.services.currency_converter.get_exchange_rate', return_value=4.97):
            result = get_eur_ron_conversion(100.00, 'RON', '2025-12-15')

        assert result['rate_date'] == '2025-12-15'


# ============== FETCH RATES TESTS ==============

class TestFetchRatesForYear:
    """Tests for _fetch_rates_for_year() function."""

    @patch('core.services.currency_converter.requests.get')
    def test_uses_both_urls_for_current_year(self, mock_get):
        """Should try yearly archive first, then current URL for current year"""
        mock_response = MagicMock()
        mock_response.content = b'''<?xml version="1.0"?>
        <DataSet xmlns="http://www.bnr.ro/xsd"><Body></Body></DataSet>'''
        mock_get.return_value = mock_response

        current_year = datetime.now().year
        _fetch_rates_for_year(current_year)

        # Should call both yearly archive and current URL
        assert mock_get.call_count == 2
        call_urls = [str(c) for c in mock_get.call_args_list]
        assert any(str(current_year) in u for u in call_urls)
        assert any(BNR_CURRENT_URL in u for u in call_urls)

    @patch('core.services.currency_converter.requests.get')
    def test_uses_yearly_url_for_past_years(self, mock_get):
        """Should use yearly archive URL for past years"""
        mock_response = MagicMock()
        mock_response.content = b'''<?xml version="1.0"?>
        <DataSet xmlns="http://www.bnr.ro/xsd"><Body></Body></DataSet>'''
        mock_get.return_value = mock_response

        _fetch_rates_for_year(2023)

        mock_get.assert_called_once()
        assert '2023' in str(mock_get.call_args)

    @patch('core.services.currency_converter.requests.get')
    def test_handles_network_error(self, mock_get):
        """Should return empty dict on network error"""
        mock_get.side_effect = Exception('Network error')

        result = _fetch_rates_for_year(2025)

        assert result == {}


# ============== CACHE TESTS ==============

class TestClearCache:
    """Tests for clear_cache() function."""

    @patch('core.services.currency_converter._fetch_rates_for_year')
    def test_clears_cache(self, mock_fetch):
        """clear_cache should force re-fetch"""
        mock_fetch.return_value = {'2025-12-15': {'EUR': 4.97}}

        # First call
        get_exchange_rate('EUR', '2025-12-15')
        assert mock_fetch.call_count == 1

        # Clear and call again
        clear_cache()
        get_exchange_rate('EUR', '2025-12-15')
        assert mock_fetch.call_count == 2


# ============== EDGE CASES ==============

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_ron_uppercase(self):
        """RON in uppercase"""
        rate = get_exchange_rate('RON', '2025-12-15')
        assert rate == 1.0

    def test_empty_date(self):
        """Empty date string"""
        rate = get_exchange_rate('EUR', '')
        assert rate is None

    def test_currency_case_insensitive(self):
        """Currency codes should be case-insensitive"""
        with patch('core.services.currency_converter._fetch_rates_for_year') as mock:
            mock.return_value = {'2025-12-15': {'EUR': 4.97}}

            rate_upper = get_exchange_rate('EUR', '2025-12-15')
            clear_cache()
            rate_lower = get_exchange_rate('eur', '2025-12-15')

            assert rate_upper == rate_lower

    @patch('core.services.currency_converter.get_exchange_rate')
    def test_conversion_rounds_to_2_decimals(self, mock_rate):
        """Conversion should round to 2 decimal places"""
        mock_rate.side_effect = lambda c, d: {'EUR': 4.9733, 'RON': 1.0}.get(c)

        amount, rate = convert_currency(100.00, 'EUR', 'RON', '2025-12-15')

        assert amount == 497.33  # Rounded


# Run with: pytest tests/test_currency_converter.py -v
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
