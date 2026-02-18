"""Summary repository - aggregation queries by company, department, brand, supplier."""
import time
import logging

from core.base_repository import BaseRepository
from core.cache import (
    _cache_lock,
    _enforce_summary_cache_limit as _enforce_summary_cache_limit_generic,
)

logger = logging.getLogger('jarvis.summaries')

# In-memory cache for summary queries (By Company, By Department, By Brand tabs)
_summary_cache = {
    'company': {},
    'department': {},
    'brand': {},
    'supplier': {},
    'ttl': 60  # 1 minute TTL
}


def clear_summary_cache():
    """Clear the summary cache only."""
    global _summary_cache
    with _cache_lock:
        _summary_cache = {'company': {}, 'department': {}, 'brand': {}, 'supplier': {}, 'ttl': 60}
    logger.debug('Summary cache cleared')


def _enforce_summary_cache_limit(cache_type):
    _enforce_summary_cache_limit_generic(_summary_cache, cache_type)


def cleanup_expired_caches():
    from core.cache import cleanup_expired_caches as _cleanup
    _cleanup(_summary_cache)


class SummaryRepository(BaseRepository):

    def by_company(self, start_date=None, end_date=None, department=None,
                   subdepartment=None, brand=None):
        """Get total allocation values grouped by company."""
        cache_key = f"{start_date}:{end_date}:{department}:{subdepartment}:{brand}"
        cache_entry = _summary_cache['company'].get(cache_key)

        if cache_entry and (time.time() - cache_entry['timestamp']) < _summary_cache['ttl']:
            return cache_entry['data']

        query = '''
            SELECT
                a.company,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                    THEN a.allocation_value * i.value_ron / i.invoice_value
                    ELSE a.allocation_value END) as total_value_ron,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                    THEN a.allocation_value * i.value_eur / i.invoice_value
                    ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END) as total_value_eur,
                COUNT(DISTINCT a.invoice_id) as invoice_count,
                AVG(COALESCE(i.exchange_rate, 5.0)) as avg_exchange_rate
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE i.deleted_at IS NULL
        '''
        params = []

        if start_date:
            query += ' AND i.invoice_date >= %s'
            params.append(start_date)
        if end_date:
            query += ' AND i.invoice_date <= %s'
            params.append(end_date)
        if department:
            query += ' AND a.department = %s'
            params.append(department)
        if subdepartment:
            query += ' AND a.subdepartment = %s'
            params.append(subdepartment)
        if brand:
            query += ' AND a.brand = %s'
            params.append(brand)

        query += ' GROUP BY a.company ORDER BY total_value_ron DESC'

        results = self.query_all(query, params)

        _summary_cache['company'][cache_key] = {'data': results, 'timestamp': time.time()}
        _enforce_summary_cache_limit('company')

        return results

    def by_department(self, company=None, start_date=None, end_date=None,
                      department=None, subdepartment=None, brand=None):
        """Get total allocation values grouped by department."""
        cache_key = f"{company}:{start_date}:{end_date}:{department}:{subdepartment}:{brand}"
        cache_entry = _summary_cache['department'].get(cache_key)

        if cache_entry and (time.time() - cache_entry['timestamp']) < _summary_cache['ttl']:
            return cache_entry['data']

        query = '''
            SELECT
                a.company,
                a.department,
                a.subdepartment,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                    THEN a.allocation_value * i.value_ron / i.invoice_value
                    ELSE a.allocation_value END) as total_value_ron,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                    THEN a.allocation_value * i.value_eur / i.invoice_value
                    ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END) as total_value_eur,
                COUNT(DISTINCT a.invoice_id) as invoice_count,
                AVG(COALESCE(i.exchange_rate, 5.0)) as avg_exchange_rate
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE i.deleted_at IS NULL
        '''
        params = []

        if company:
            query += ' AND a.company = %s'
            params.append(company)
        if start_date:
            query += ' AND i.invoice_date >= %s'
            params.append(start_date)
        if end_date:
            query += ' AND i.invoice_date <= %s'
            params.append(end_date)
        if department:
            query += ' AND a.department = %s'
            params.append(department)
        if subdepartment:
            query += ' AND a.subdepartment = %s'
            params.append(subdepartment)
        if brand:
            query += ' AND a.brand = %s'
            params.append(brand)

        query += ' GROUP BY a.company, a.department, a.subdepartment ORDER BY total_value_ron DESC'

        results = self.query_all(query, params)

        _summary_cache['department'][cache_key] = {'data': results, 'timestamp': time.time()}
        _enforce_summary_cache_limit('department')

        return results

    def by_brand(self, company=None, start_date=None, end_date=None,
                 department=None, subdepartment=None, brand=None):
        """Get total allocation values grouped by brand with invoice details."""
        cache_key = f"{company}:{start_date}:{end_date}:{department}:{subdepartment}:{brand}"
        cache_entry = _summary_cache['brand'].get(cache_key)

        if cache_entry and (time.time() - cache_entry['timestamp']) < _summary_cache['ttl']:
            return cache_entry['data']

        query = '''
            SELECT a.brand,
                   SUM(CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                       THEN a.allocation_value * i.value_ron / i.invoice_value
                       ELSE a.allocation_value END) as total_value_ron,
                   SUM(CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                       THEN a.allocation_value * i.value_eur / i.invoice_value
                       ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END) as total_value_eur,
                   COUNT(DISTINCT a.invoice_id) as invoice_count,
                   AVG(COALESCE(i.exchange_rate, 5.0)) as avg_exchange_rate,
                   STRING_AGG(DISTINCT i.invoice_number, ', ') as invoice_numbers,
                   JSON_AGG(JSON_BUILD_OBJECT(
                       'department', a.department,
                       'subdepartment', a.subdepartment,
                       'brand', a.brand,
                       'value', a.allocation_value,
                       'value_ron', CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                           THEN a.allocation_value * i.value_ron / i.invoice_value
                           ELSE a.allocation_value END,
                       'value_eur', CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                           THEN a.allocation_value * i.value_eur / i.invoice_value
                           ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END,
                       'percent', ROUND(a.allocation_percent),
                       'reinvoice_to', a.reinvoice_to,
                       'reinvoice_brand', a.reinvoice_brand,
                       'reinvoice_department', a.reinvoice_department,
                       'reinvoice_subdepartment', a.reinvoice_subdepartment,
                       'currency', i.currency
                   )) as split_values
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE i.deleted_at IS NULL
        '''
        params = []

        if company:
            query += ' AND a.company = %s'
            params.append(company)
        if start_date:
            query += ' AND i.invoice_date >= %s'
            params.append(start_date)
        if end_date:
            query += ' AND i.invoice_date <= %s'
            params.append(end_date)
        if department:
            query += ' AND a.department = %s'
            params.append(department)
        if subdepartment:
            query += ' AND a.subdepartment = %s'
            params.append(subdepartment)
        if brand:
            query += ' AND a.brand = %s'
            params.append(brand)

        query += ' GROUP BY a.brand ORDER BY total_value_ron DESC'

        results = self.query_all(query, params)

        _summary_cache['brand'][cache_key] = {'data': results, 'timestamp': time.time()}
        _enforce_summary_cache_limit('brand')

        return results

    def by_supplier(self, company=None, start_date=None, end_date=None,
                    department=None, subdepartment=None, brand=None):
        """Get allocation values grouped by supplier."""
        cache_key = f"{company}:{start_date}:{end_date}:{department}:{subdepartment}:{brand}"
        cache_entry = _summary_cache['supplier'].get(cache_key)

        if cache_entry and (time.time() - cache_entry['timestamp']) < _summary_cache['ttl']:
            return cache_entry['data']

        query = '''
            SELECT
                i.supplier,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                    THEN a.allocation_value * i.value_ron / i.invoice_value
                    ELSE a.allocation_value END) as total_value_ron,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                    THEN a.allocation_value * i.value_eur / i.invoice_value
                    ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END) as total_value_eur,
                COUNT(DISTINCT a.invoice_id) as invoice_count,
                AVG(COALESCE(i.exchange_rate, 5.0)) as avg_exchange_rate
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE i.deleted_at IS NULL
        '''
        params = []

        if company:
            query += ' AND a.company = %s'
            params.append(company)
        if start_date:
            query += ' AND i.invoice_date >= %s'
            params.append(start_date)
        if end_date:
            query += ' AND i.invoice_date <= %s'
            params.append(end_date)
        if department:
            query += ' AND a.department = %s'
            params.append(department)
        if subdepartment:
            query += ' AND a.subdepartment = %s'
            params.append(subdepartment)
        if brand:
            query += ' AND a.brand = %s'
            params.append(brand)

        query += ' GROUP BY i.supplier ORDER BY total_value_ron DESC'

        results = self.query_all(query, params)

        _summary_cache['supplier'][cache_key] = {'data': results, 'timestamp': time.time()}
        _enforce_summary_cache_limit('supplier')

        return results
