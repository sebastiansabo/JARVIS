"""Template Repository - Data access layer for invoice template operations.

Handles invoice template CRUD with caching.
"""
import time
import logging

from core.base_repository import BaseRepository
from core.cache import _cache_lock, _is_cache_valid

logger = logging.getLogger('jarvis.accounting.templates.repository')

# In-memory cache for templates
_templates_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300
}


def clear_templates_cache():
    """Clear the templates cache."""
    global _templates_cache
    with _cache_lock:
        _templates_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    logger.debug('Templates cache cleared')


class TemplateRepository(BaseRepository):
    """Repository for invoice template data access operations."""

    def get_all(self) -> list[dict]:
        """Get all invoice templates (with caching)."""
        global _templates_cache

        if _is_cache_valid(_templates_cache):
            return _templates_cache['data']

        templates = self.query_all('SELECT * FROM invoice_templates ORDER BY name')

        _templates_cache['data'] = templates
        _templates_cache['timestamp'] = time.time()
        return templates

    def get(self, template_id: int):
        """Get a specific invoice template by ID."""
        return self.query_one('SELECT * FROM invoice_templates WHERE id = %s', (template_id,))

    def get_by_name(self, name: str):
        """Get a specific invoice template by name."""
        return self.query_one('SELECT * FROM invoice_templates WHERE name = %s', (name,))

    def save(self, name: str, supplier: str = None, supplier_vat: str = None,
             customer_vat: str = None, currency: str = 'RON', description: str = None,
             invoice_number_regex: str = None, invoice_date_regex: str = None,
             invoice_value_regex: str = None, date_format: str = '%Y-%m-%d',
             sample_invoice_path: str = None, template_type: str = 'fixed',
             supplier_regex: str = None, supplier_vat_regex: str = None,
             customer_vat_regex: str = None, currency_regex: str = None) -> int:
        """Save a new invoice template. Returns template ID."""
        try:
            result = self.execute('''
                INSERT INTO invoice_templates (
                    name, template_type, supplier, supplier_vat, customer_vat, currency, description,
                    invoice_number_regex, invoice_date_regex, invoice_value_regex,
                    date_format, sample_invoice_path,
                    supplier_regex, supplier_vat_regex, customer_vat_regex, currency_regex
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (name, template_type, supplier, supplier_vat, customer_vat, currency, description,
                  invoice_number_regex, invoice_date_regex, invoice_value_regex,
                  date_format, sample_invoice_path,
                  supplier_regex, supplier_vat_regex, customer_vat_regex, currency_regex),
                returning=True)
            clear_templates_cache()
            return result['id']
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError(f"Template '{name}' already exists")
            raise

    def update(self, template_id: int, name: str = None, supplier: str = None,
               supplier_vat: str = None, customer_vat: str = None, currency: str = None,
               description: str = None, invoice_number_regex: str = None,
               invoice_date_regex: str = None, invoice_value_regex: str = None,
               date_format: str = None, sample_invoice_path: str = None,
               template_type: str = None, supplier_regex: str = None,
               supplier_vat_regex: str = None, customer_vat_regex: str = None,
               currency_regex: str = None) -> bool:
        """Update an existing invoice template."""
        updates = []
        params = []

        field_map = {
            'name': name, 'template_type': template_type, 'supplier': supplier,
            'supplier_vat': supplier_vat, 'customer_vat': customer_vat,
            'currency': currency, 'description': description,
            'invoice_number_regex': invoice_number_regex,
            'invoice_date_regex': invoice_date_regex,
            'invoice_value_regex': invoice_value_regex,
            'date_format': date_format, 'sample_invoice_path': sample_invoice_path,
            'supplier_regex': supplier_regex, 'supplier_vat_regex': supplier_vat_regex,
            'customer_vat_regex': customer_vat_regex, 'currency_regex': currency_regex,
        }

        for field_name, value in field_map.items():
            if value is not None:
                updates.append(f'{field_name} = %s')
                params.append(value)

        if not updates:
            return False

        updates.append('updated_at = CURRENT_TIMESTAMP')
        params.append(template_id)

        updated = self.execute(f"UPDATE invoice_templates SET {', '.join(updates)} WHERE id = %s", params) > 0
        if updated:
            clear_templates_cache()
        return updated

    def delete(self, template_id: int) -> bool:
        """Delete an invoice template."""
        deleted = self.execute('DELETE FROM invoice_templates WHERE id = %s', (template_id,)) > 0
        if deleted:
            clear_templates_cache()
        return deleted
