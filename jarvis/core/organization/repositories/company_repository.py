"""Company Repository - Data access layer for company operations.

Handles company CRUD, VAT management, and company-brand associations.
"""
import re
import time
import logging
from typing import Optional

from database import get_db, get_cursor, release_db
from core.base_repository import BaseRepository
from core.cache import _cache_lock, _is_cache_valid

logger = logging.getLogger('jarvis.core.organization.company_repository')

# In-memory cache for companies
_companies_vat_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300
}


def clear_companies_vat_cache():
    """Clear the companies VAT cache."""
    global _companies_vat_cache
    with _cache_lock:
        _companies_vat_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    logger.debug('Companies VAT cache cleared')


def _normalize_vat(vat: str) -> str:
    """Normalize VAT number for comparison."""
    if not vat:
        return ''
    vat = str(vat).upper().strip()
    prefixes_to_remove = ['CUI:', 'CUI', 'CIF:', 'CIF', 'VAT:', 'VAT', 'TAX ID:', 'TAX ID', 'NR.', 'NR', 'NO.', 'NO']
    for prefix in prefixes_to_remove:
        if vat.startswith(prefix):
            vat = vat[len(prefix):].strip()
    vat = re.sub(r'[\s\-\./:]+', '', vat)
    return vat


def _extract_vat_numbers(vat: str) -> str:
    """Extract just the numeric portion of a VAT number."""
    if not vat:
        return ''
    return re.sub(r'[^0-9]', '', str(vat))


class CompanyRepository(BaseRepository):
    """Repository for company data access operations."""

    # --- Company CRUD (by ID) ---

    def get_all(self) -> list[dict]:
        """Get all companies (with caching)."""
        global _companies_vat_cache

        if _is_cache_valid(_companies_vat_cache):
            return _companies_vat_cache['data']

        results = self.query_all('SELECT * FROM companies ORDER BY company')

        _companies_vat_cache['data'] = results
        _companies_vat_cache['timestamp'] = time.time()
        return results

    def get(self, company_id: int) -> Optional[dict]:
        """Get a specific company by ID."""
        return self.query_one('SELECT * FROM companies WHERE id = %s', (company_id,))

    def save(self, company: str, vat: str = None) -> int:
        """Create a new company. Returns company ID."""
        try:
            result = self.execute('''
                INSERT INTO companies (company, vat)
                VALUES (%s, %s)
                RETURNING id
            ''', (company, vat), returning=True)
            clear_companies_vat_cache()
            return result['id']
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError(f"Company '{company}' already exists")
            raise

    def update(self, company_id: int, company: str = None, vat: str = None) -> bool:
        """Update a company. Returns True if updated."""
        updates = []
        params = []
        if company is not None:
            updates.append('company = %s')
            params.append(company)
        if vat is not None:
            updates.append('vat = %s')
            params.append(vat)
        if not updates:
            return False

        params.append(company_id)
        try:
            rowcount = self.execute(
                f'UPDATE companies SET {", ".join(updates)} WHERE id = %s', params
            )
            if rowcount > 0:
                clear_companies_vat_cache()
            return rowcount > 0
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError(f"Company name '{company}' already exists")
            raise

    def delete(self, company_id: int) -> bool:
        """Delete a company by ID."""
        rowcount = self.execute('DELETE FROM companies WHERE id = %s', (company_id,))
        if rowcount > 0:
            clear_companies_vat_cache()
        return rowcount > 0

    # --- Company VAT operations (by name) ---

    def get_all_with_vat_and_brands(self) -> list[dict]:
        """Get all companies with VAT numbers and brand associations."""
        # This method needs multiple queries on the same connection
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('SELECT id, company, vat FROM companies ORDER BY company')
            companies = [dict(row) for row in cursor.fetchall()]

            cursor.execute('''
                SELECT cb.id as cb_id, cb.company_id, b.id as brand_id, b.name as brand
                FROM company_brands cb
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.is_active = TRUE AND b.is_active = TRUE
                ORDER BY b.name
            ''')
            brands_rows = cursor.fetchall()

            brands_by_company = {}
            for row in brands_rows:
                cid = row['company_id']
                if cid not in brands_by_company:
                    brands_by_company[cid] = []
                brands_by_company[cid].append({
                    'id': row['cb_id'],
                    'brand_id': row['brand_id'],
                    'brand': row['brand']
                })

            for company in companies:
                company_brands = brands_by_company.get(company['id'], [])
                company['brands_list'] = company_brands
                company['brands'] = ', '.join(b['brand'] for b in company_brands) if company_brands else ''

            return companies
        finally:
            release_db(conn)

    def add_with_vat(self, company: str, vat: str) -> bool:
        """Add a new company with VAT number."""
        try:
            self.execute('''
                INSERT INTO companies (company, vat)
                VALUES (%s, %s)
            ''', (company, vat))
            clear_companies_vat_cache()
            return True
        except Exception:
            return False

    def update_vat(self, company_name: str, vat: str) -> bool:
        """Update VAT for a company by name."""
        rowcount = self.execute(
            'UPDATE companies SET vat = %s WHERE company = %s', (vat, company_name)
        )
        if rowcount > 0:
            clear_companies_vat_cache()
        return rowcount > 0

    def delete_by_name(self, company_name: str) -> bool:
        """Delete a company by name."""
        rowcount = self.execute(
            'DELETE FROM companies WHERE company = %s', (company_name,)
        )
        if rowcount > 0:
            clear_companies_vat_cache()
        return rowcount > 0

    def match_by_vat(self, invoice_vat: str) -> Optional[dict]:
        """Find company matching the given VAT number.

        Uses multiple matching strategies:
        1. Exact match after normalization
        2. Numeric-only match
        """
        if not invoice_vat:
            return None

        normalized_invoice_vat = _normalize_vat(invoice_vat)
        invoice_numbers_only = _extract_vat_numbers(invoice_vat)

        companies = self.get_all_with_vat_and_brands()

        for company in companies:
            company_vat = company.get('vat', '')
            if _normalize_vat(company_vat) == normalized_invoice_vat:
                return company

        if invoice_numbers_only:
            for company in companies:
                company_vat = company.get('vat', '')
                company_numbers = _extract_vat_numbers(company_vat)
                if company_numbers and company_numbers == invoice_numbers_only:
                    return company

        return None
