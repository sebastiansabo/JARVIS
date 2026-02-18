"""Allocation repository - CRUD, reinvoice destinations."""
import logging
from decimal import Decimal

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.allocations')


class AllocationRepository(BaseRepository):

    def get_by_company(self, company):
        """Get all allocations for a specific company."""
        return self.query_all('''
            SELECT a.*, i.supplier, i.invoice_number, i.invoice_date
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE a.company = %s
            ORDER BY i.invoice_date DESC
        ''', (company,))

    def get_by_department(self, company, department):
        """Get all allocations for a specific department."""
        return self.query_all('''
            SELECT a.*, i.supplier, i.invoice_number, i.invoice_date
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE a.company = %s AND a.department = %s
            ORDER BY i.invoice_date DESC
        ''', (company, department))

    def update(self, allocation_id, company=None, brand=None, department=None,
               subdepartment=None, allocation_percent=None, allocation_value=None,
               responsible=None, reinvoice_to=None, reinvoice_brand=None,
               reinvoice_department=None, reinvoice_subdepartment=None, comment=None):
        """Update an existing allocation."""
        updates = []
        params = []

        field_map = {
            'company': company, 'brand': brand, 'department': department,
            'subdepartment': subdepartment, 'allocation_percent': allocation_percent,
            'allocation_value': allocation_value, 'responsible': responsible,
            'reinvoice_to': reinvoice_to, 'reinvoice_brand': reinvoice_brand,
            'reinvoice_department': reinvoice_department,
            'reinvoice_subdepartment': reinvoice_subdepartment, 'comment': comment,
        }

        for field, value in field_map.items():
            if value is not None:
                updates.append(f'{field} = %s')
                params.append(value)

        if not updates:
            return False

        params.append(allocation_id)
        query = f"UPDATE allocations SET {', '.join(updates)} WHERE id = %s"
        return self.execute(query, params) > 0

    def delete(self, allocation_id):
        """Delete an allocation."""
        return self.execute('DELETE FROM allocations WHERE id = %s', (allocation_id,)) > 0

    def update_comment(self, allocation_id, comment):
        """Update just the comment for an allocation."""
        return self.execute('UPDATE allocations SET comment = %s WHERE id = %s',
                            (comment, allocation_id)) > 0

    def add(self, invoice_id, company, department, allocation_percent,
            allocation_value, brand=None, subdepartment=None, responsible=None,
            reinvoice_to=None, reinvoice_brand=None, reinvoice_department=None,
            reinvoice_subdepartment=None):
        """Add a new allocation to an invoice. Returns allocation ID."""
        def _work(cursor):
            responsible_user_id = None
            if responsible:
                cursor.execute('SELECT id FROM users WHERE LOWER(name) = LOWER(%s) LIMIT 1', (responsible,))
                user_row = cursor.fetchone()
                if user_row:
                    responsible_user_id = user_row['id']

            cursor.execute('''
                INSERT INTO allocations (invoice_id, company, brand, department, subdepartment,
                    allocation_percent, allocation_value, responsible, responsible_user_id, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (invoice_id, company, brand, department, subdepartment,
                  allocation_percent, allocation_value, responsible, responsible_user_id, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def update_invoice_allocations(self, invoice_id, allocations):
        """Replace all allocations for an invoice with new ones (transactional)."""
        def _work(cursor):
            cursor.execute('SELECT invoice_value, subtract_vat, net_value FROM invoices WHERE id = %s', (invoice_id,))
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Invoice {invoice_id} not found")
            invoice_value = Decimal(str(result['invoice_value']))
            base_value = Decimal(str(result['net_value'])) if result['subtract_vat'] and result['net_value'] else invoice_value

            cursor.execute('DELETE FROM allocations WHERE invoice_id = %s', (invoice_id,))

            for alloc in allocations:
                allocation_percent = Decimal(str(alloc['allocation_percent']))
                gross_allocation_value = base_value * allocation_percent / 100

                reinvoice_dests = alloc.get('reinvoice_destinations', [])
                total_reinvoice_percent = sum(Decimal(str(rd.get('percentage', 0))) for rd in reinvoice_dests)
                net_percent = max(0, 100 - total_reinvoice_percent)
                allocation_value = gross_allocation_value * net_percent / 100

                responsible = alloc.get('responsible')
                responsible_user_id = None
                if responsible:
                    cursor.execute('SELECT id FROM users WHERE LOWER(name) = LOWER(%s) LIMIT 1', (responsible,))
                    user_row = cursor.fetchone()
                    if user_row:
                        responsible_user_id = user_row['id']

                cursor.execute('''
                    INSERT INTO allocations (invoice_id, company, brand, department, subdepartment,
                        allocation_percent, allocation_value, responsible, responsible_user_id, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, locked, comment)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    invoice_id,
                    alloc['company'],
                    alloc.get('brand'),
                    alloc['department'],
                    alloc.get('subdepartment'),
                    allocation_percent,
                    allocation_value,
                    responsible,
                    responsible_user_id,
                    alloc.get('reinvoice_to'),
                    alloc.get('reinvoice_brand'),
                    alloc.get('reinvoice_department'),
                    alloc.get('reinvoice_subdepartment'),
                    alloc.get('locked', False),
                    alloc.get('comment')
                ))
                allocation_id = cursor.fetchone()['id']

                for rd in reinvoice_dests:
                    rd_value = gross_allocation_value * Decimal(str(rd['percentage'])) / 100
                    cursor.execute('''
                        INSERT INTO reinvoice_destinations
                        (allocation_id, company, brand, department, subdepartment, percentage, value)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        allocation_id,
                        rd['company'],
                        rd.get('brand'),
                        rd.get('department'),
                        rd.get('subdepartment'),
                        rd['percentage'],
                        rd_value
                    ))

            from accounting.invoices.repositories.invoice_repository import clear_invoices_cache
            clear_invoices_cache()
            return True
        return self.execute_many(_work)

    def get_reinvoice_destinations(self, allocation_id):
        """Get all reinvoice destinations for an allocation."""
        return self.query_all('''
            SELECT * FROM reinvoice_destinations WHERE allocation_id = %s ORDER BY id
        ''', (allocation_id,))

    def save_reinvoice_destinations(self, allocation_id, destinations, allocation_value=None):
        """Replace all reinvoice destinations for an allocation."""
        def _work(cursor):
            cursor.execute('DELETE FROM reinvoice_destinations WHERE allocation_id = %s', (allocation_id,))

            for dest in destinations:
                dest_value = None
                if allocation_value is not None and dest.get('percentage'):
                    dest_value = Decimal(str(allocation_value)) * Decimal(str(dest['percentage'])) / 100
                cursor.execute('''
                    INSERT INTO reinvoice_destinations
                    (allocation_id, company, brand, department, subdepartment, percentage, value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    allocation_id,
                    dest['company'],
                    dest.get('brand'),
                    dest.get('department'),
                    dest.get('subdepartment'),
                    dest['percentage'],
                    dest_value or dest.get('value')
                ))
            return True
        return self.execute_many(_work)

    def save_reinvoice_destinations_batch(self, allocation_destinations):
        """Save reinvoice destinations for multiple allocations in a single transaction."""
        def _work(cursor):
            for allocation_id, destinations, allocation_value in allocation_destinations:
                cursor.execute('DELETE FROM reinvoice_destinations WHERE allocation_id = %s', (allocation_id,))

                for dest in destinations:
                    dest_value = Decimal(str(allocation_value)) * Decimal(str(dest['percentage'])) / 100 if allocation_value else dest.get('value')
                    cursor.execute('''
                        INSERT INTO reinvoice_destinations
                        (allocation_id, company, brand, department, subdepartment, percentage, value)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        allocation_id,
                        dest['company'],
                        dest.get('brand'),
                        dest.get('department'),
                        dest.get('subdepartment'),
                        dest['percentage'],
                        dest_value
                    ))
            return True
        return self.execute_many(_work)
