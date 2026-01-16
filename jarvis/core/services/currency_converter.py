"""
BNR Currency Converter Module

Fetches exchange rates from the National Bank of Romania (BNR) API
and provides currency conversion functionality.

BNR XML API endpoints:
- Current rates: https://www.bnr.ro/nbrfxrates.xml
- Historical rates by year: https://www.bnr.ro/files/xml/years/nbrfxrates{YEAR}.xml

All rates are RON-based (how many RON per 1 unit of foreign currency).
"""

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, Tuple
import requests

# BNR XML API URLs
BNR_CURRENT_URL = "https://www.bnr.ro/nbrfxrates.xml"
BNR_YEARLY_URL = "https://www.bnr.ro/files/xml/years/nbrfxrates{year}.xml"

# XML namespace used by BNR
BNR_NS = {"bnr": "http://www.bnr.ro/xsd"}

# Simple in-memory cache for exchange rates
# Structure: {year: {date_str: {currency: rate}}}
_rate_cache = {}


def get_exchange_rate(currency: str, date: str) -> Optional[float]:
    """
    Get the BNR exchange rate for a currency on a specific date.

    Args:
        currency: Currency code (e.g., 'EUR', 'USD')
        date: Date string in YYYY-MM-DD format

    Returns:
        Exchange rate (RON per 1 unit of currency) or None if not found

    Note: BNR does not publish rates on weekends/holidays.
    For non-banking days, returns the most recent available rate.
    """
    currency = currency.upper()

    # RON to RON is always 1
    if currency == 'RON':
        return 1.0

    # Parse the date
    try:
        target_date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return None

    year = target_date.year

    # Try to get rate for the exact date, fallback to previous days
    # BNR doesn't publish on weekends/holidays
    for days_back in range(10):  # Try up to 10 days back
        check_date = target_date - timedelta(days=days_back)
        check_date_str = check_date.strftime('%Y-%m-%d')
        check_year = check_date.year

        rate = _get_rate_from_cache_or_fetch(currency, check_date_str, check_year)
        if rate is not None:
            return rate

    return None


def _get_rate_from_cache_or_fetch(currency: str, date: str, year: int) -> Optional[float]:
    """Get rate from cache or fetch from BNR API."""
    global _rate_cache

    # Check cache first
    if year in _rate_cache and date in _rate_cache[year]:
        rates = _rate_cache[year][date]
        return rates.get(currency)

    # Fetch rates for the year
    rates_by_date = _fetch_rates_for_year(year)

    if date in rates_by_date:
        return rates_by_date[date].get(currency)

    return None


def _fetch_rates_for_year(year: int) -> dict:
    """
    Fetch all exchange rates for a specific year from BNR.

    Returns dict: {date_str: {currency: rate}}
    """
    global _rate_cache

    # Already fetched this year
    if year in _rate_cache:
        return _rate_cache[year]

    current_year = datetime.now().year

    # Use current rates URL for current year, yearly archive for past years
    if year == current_year:
        url = BNR_CURRENT_URL
    else:
        url = BNR_YEARLY_URL.format(year=year)

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        rates_by_date = _parse_bnr_xml(response.content)
        _rate_cache[year] = rates_by_date

        return rates_by_date
    except Exception as e:
        print(f"Error fetching BNR rates for {year}: {e}")
        _rate_cache[year] = {}
        return {}


def _parse_bnr_xml(xml_content: bytes) -> dict:
    """
    Parse BNR XML response and extract rates.

    Returns dict: {date_str: {currency: rate}}
    """
    rates_by_date = {}

    try:
        root = ET.fromstring(xml_content)

        # Find all Cube elements (each contains rates for one date)
        for cube in root.findall('.//bnr:Cube', BNR_NS):
            date_str = cube.get('date')
            if not date_str:
                continue

            rates = {}

            # Extract all rates for this date
            for rate_elem in cube.findall('bnr:Rate', BNR_NS):
                currency = rate_elem.get('currency')
                if not currency:
                    continue

                try:
                    rate_value = float(rate_elem.text)

                    # Handle multiplier (e.g., HUF is quoted per 100 units)
                    multiplier = rate_elem.get('multiplier')
                    if multiplier:
                        rate_value = rate_value / float(multiplier)

                    rates[currency] = rate_value
                except (ValueError, TypeError):
                    continue

            if rates:
                rates_by_date[date_str] = rates

    except ET.ParseError as e:
        print(f"Error parsing BNR XML: {e}")

    return rates_by_date


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    date: str
) -> Tuple[Optional[float], Optional[float]]:
    """
    Convert amount from one currency to another using BNR rates.

    Args:
        amount: Amount to convert
        from_currency: Source currency code (e.g., 'EUR', 'RON')
        to_currency: Target currency code
        date: Date for the exchange rate (YYYY-MM-DD)

    Returns:
        Tuple of (converted_amount, exchange_rate) or (None, None) if conversion failed
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    # Same currency, no conversion needed
    if from_currency == to_currency:
        return amount, 1.0

    # Get rates (all rates are RON-based)
    from_rate = get_exchange_rate(from_currency, date)
    to_rate = get_exchange_rate(to_currency, date)

    if from_rate is None or to_rate is None:
        return None, None

    # Convert: first to RON, then to target currency
    # amount_in_ron = amount * from_rate
    # converted = amount_in_ron / to_rate

    # Combined rate
    rate = from_rate / to_rate
    converted = amount * rate

    return round(converted, 2), round(rate, 6)


def get_eur_ron_conversion(
    amount: float,
    currency: str,
    date: str
) -> dict:
    """
    Get both EUR and RON values for an invoice amount.

    Args:
        amount: Invoice amount
        currency: Invoice currency
        date: Invoice date (YYYY-MM-DD)

    Returns:
        dict with:
            - value_ron: Amount in RON
            - value_eur: Amount in EUR
            - exchange_rate: Rate used (EUR/RON)
            - rate_date: Date of the rate used
            - original_currency: Original currency
    """
    currency = currency.upper()

    result = {
        'value_ron': None,
        'value_eur': None,
        'exchange_rate': None,
        'rate_date': date,
        'original_currency': currency
    }

    # Get EUR/RON rate
    eur_rate = get_exchange_rate('EUR', date)

    if eur_rate is None:
        return result

    result['exchange_rate'] = eur_rate

    if currency == 'RON':
        result['value_ron'] = round(amount, 2)
        result['value_eur'] = round(amount / eur_rate, 2)
    elif currency == 'EUR':
        result['value_eur'] = round(amount, 2)
        result['value_ron'] = round(amount * eur_rate, 2)
    else:
        # For other currencies (USD, GBP, etc.), convert to both
        currency_rate = get_exchange_rate(currency, date)
        if currency_rate:
            # Convert to RON first
            value_ron = amount * currency_rate
            result['value_ron'] = round(value_ron, 2)
            result['value_eur'] = round(value_ron / eur_rate, 2)

    return result


def clear_cache():
    """Clear the rate cache (useful for testing or refreshing data)."""
    global _rate_cache
    _rate_cache = {}


# Test function
if __name__ == '__main__':
    # Test with a sample date
    test_date = '2025-12-09'

    print(f"Testing BNR exchange rates for {test_date}")
    print("-" * 40)

    # Get EUR rate
    eur_rate = get_exchange_rate('EUR', test_date)
    print(f"EUR/RON: {eur_rate}")

    # Get USD rate
    usd_rate = get_exchange_rate('USD', test_date)
    print(f"USD/RON: {usd_rate}")

    # Test conversion
    print("\nConversion test:")
    print(f"100 EUR -> RON: {convert_currency(100, 'EUR', 'RON', test_date)}")
    print(f"100 RON -> EUR: {convert_currency(100, 'RON', 'EUR', test_date)}")

    # Test full conversion info
    print("\nFull conversion info for 1000 EUR invoice:")
    result = get_eur_ron_conversion(1000, 'EUR', test_date)
    print(result)

    print("\nFull conversion info for 5000 RON invoice:")
    result = get_eur_ron_conversion(5000, 'RON', test_date)
    print(result)
