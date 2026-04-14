"""
Invoice Repository

Database operations for e-Factura invoices and related entities.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple

from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger
from ..config import InvoiceDirection, ArtifactType
from ..models import (
    Invoice,
    InvoiceExternalRef,
    InvoiceArtifact,
)
from ._invoice_base import _EFacturaInvoiceBase

logger = get_logger('jarvis.accounting.efactura.repo.invoice')


class EFacturaInvoiceRepository(_EFacturaInvoiceBase):
    """Repository for Invoice and related entities."""

    # ============================================
    # Unallocated Invoices (for JARVIS integration)
    # ============================================

    def get_by_message_id_simple(self, message_id: str) -> Optional[Invoice]:
        """Get invoice by ANAF message ID only (simpler version for import)."""
        row = self.query_one("""
            SELECT i.* FROM efactura_invoices i
            JOIN efactura_invoice_refs r ON r.invoice_id = i.id
            WHERE r.message_id = %s
        """, (message_id,))
        return self._row_to_invoice(row) if row else None

    def ignore_invoice(self, invoice_id: int, ignored: bool = True) -> bool:
        """Mark an invoice as ignored (soft delete)."""
        try:
            self.execute("""
                UPDATE efactura_invoices
                SET ignored = %s, updated_at = NOW()
                WHERE id = %s
            """, (ignored, invoice_id))
            logger.info(
                f"Invoice {'ignored' if ignored else 'restored'}",
                extra={'invoice_id': invoice_id}
            )
            return True
        except Exception as e:
            logger.error(f"Failed to ignore invoice: {e}")
            return False

    def supplier_has_hidden_types(self, partner_name: str) -> bool:
        """
        Check if a partner has ONLY hidden types (all types have hide_in_filter=TRUE).
        Returns False if the partner has any non-hidden type (mixed types = not hidden).
        """
        if not partner_name:
            return False

        try:
            result = self.query_one("""
                SELECT
                    EXISTS (
                        SELECT 1
                        FROM efactura_supplier_mappings sm
                        JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm.id
                        JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                        WHERE LOWER(sm.partner_name) = LOWER(%s)
                            AND sm.is_active = TRUE
                            AND pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                    ) as has_hidden_types,
                    EXISTS (
                        SELECT 1
                        FROM efactura_supplier_mappings sm
                        JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm.id
                        JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                        WHERE LOWER(sm.partner_name) = LOWER(%s)
                            AND sm.is_active = TRUE
                            AND pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                    ) as has_visible_types
            """, (partner_name, partner_name))
            if not result:
                return False
            return result['has_hidden_types'] and not result['has_visible_types']
        except Exception as e:
            logger.error(f"Failed to check partner hidden types: {e}")
            return False

    def auto_hide_if_typed(self, invoice_id: int, partner_name: str) -> bool:
        """
        Automatically hide an invoice if its partner has types with hide_in_filter=TRUE.
        Skips invoices that have a manual type override.
        """
        row = self.query_one(
            'SELECT type_override FROM efactura_invoices WHERE id = %s', (invoice_id,)
        )
        if row and row.get('type_override'):
            return False  # Has manual override, skip auto-hide

        if self.supplier_has_hidden_types(partner_name):
            logger.info(
                "Auto-hiding invoice due to partner having hidden types",
                extra={'invoice_id': invoice_id, 'partner_name': partner_name}
            )
            return self.ignore_invoice(invoice_id, ignored=True)
        return False

    def auto_hide_all_by_supplier(self, partner_name: str) -> int:
        """
        Auto-hide all unallocated, non-ignored invoices for a partner.
        Only affects invoices without manual type override.
        """
        if not partner_name:
            return 0

        try:
            count = self.execute("""
                UPDATE efactura_invoices
                SET ignored = TRUE, updated_at = NOW()
                WHERE LOWER(partner_name) = LOWER(%s)
                    AND jarvis_invoice_id IS NULL
                    AND ignored = FALSE
                    AND deleted_at IS NULL
                    AND type_override IS NULL
            """, (partner_name,))
            if count > 0:
                logger.info(
                    f"Auto-hidden {count} invoices for partner with hidden types",
                    extra={'partner_name': partner_name, 'count': count}
                )
            return count
        except Exception as e:
            logger.error(f"Failed to auto-hide invoices for partner: {e}")
            return 0

    def update_overrides(
        self,
        invoice_id: int,
        type_override: Optional[str] = None,
        department_override: Optional[str] = None,
        subdepartment_override: Optional[str] = None,
        department_override_2: Optional[str] = None,
        subdepartment_override_2: Optional[str] = None,
        observer_user_ids: Optional[List[int]] = None,
    ) -> bool:
        """Update invoice-level overrides for Type, Department, Subdepartment, and Observers.

        Passing observer_user_ids=None leaves the existing value untouched.
        Passing an empty list clears stored observers.
        """
        try:
            if observer_user_ids is None:
                self.execute("""
                    UPDATE efactura_invoices
                    SET type_override = %s,
                        department_override = %s,
                        subdepartment_override = %s,
                        department_override_2 = %s,
                        subdepartment_override_2 = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (type_override, department_override, subdepartment_override,
                      department_override_2, subdepartment_override_2, invoice_id))
            else:
                normalized = []
                seen = set()
                for raw in observer_user_ids:
                    try:
                        uid = int(raw)
                    except (TypeError, ValueError):
                        continue
                    if uid in seen:
                        continue
                    seen.add(uid)
                    normalized.append(uid)
                stored_observers = normalized if normalized else None
                self.execute("""
                    UPDATE efactura_invoices
                    SET type_override = %s,
                        department_override = %s,
                        subdepartment_override = %s,
                        department_override_2 = %s,
                        subdepartment_override_2 = %s,
                        observer_user_ids = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (type_override, department_override, subdepartment_override,
                      department_override_2, subdepartment_override_2,
                      stored_observers, invoice_id))
            logger.info(
                f"Invoice overrides updated",
                extra={
                    'invoice_id': invoice_id,
                    'type_override': type_override,
                    'department_override': department_override,
                    'subdepartment_override': subdepartment_override,
                    'department_override_2': department_override_2,
                    'subdepartment_override_2': subdepartment_override_2,
                    'observers_updated': observer_user_ids is not None,
                }
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update invoice overrides: {e}")
            return False

    def bulk_update_overrides(
        self,
        invoice_ids: List[int],
        updates: Dict[str, Any],
    ) -> int:
        """Bulk update invoice-level overrides for multiple invoices."""
        if not invoice_ids or not updates:
            return 0

        allowed_fields = {'type_override', 'department_override', 'subdepartment_override',
                          'department_override_2', 'subdepartment_override_2'}
        set_clauses = []
        params = []

        for field, value in updates.items():
            if field in allowed_fields:
                set_clauses.append(f"{field} = %s")
                params.append(value)

        if not set_clauses:
            return 0

        set_clauses.append("updated_at = NOW()")
        params.append(invoice_ids)

        try:
            count = self.execute(f"""
                UPDATE efactura_invoices
                SET {', '.join(set_clauses)}
                WHERE id = ANY(%s)
            """, params)
            logger.info(
                f"Bulk updated {count} invoice overrides",
                extra={'invoice_ids': invoice_ids, 'updates': updates}
            )
            return count
        except Exception as e:
            logger.error(f"Failed to bulk update invoice overrides: {e}")
            return 0

    # Valid sort columns mapping (frontend name -> DB column)
    SORT_COLUMNS = {
        'company': 'i.company_id',
        'direction': 'i.direction',
        'invoice_number': 'i.invoice_number',
        'partner_name': 'i.partner_name',
        'partner_cif': 'i.partner_cif',
        'type': 'i.type_override',
        'department': 'COALESCE(i.department_override, sm.department)',
        'subdepartment': 'COALESCE(i.subdepartment_override, sm.subdepartment)',
        'issue_date': 'i.issue_date',
        'amount': 'i.total_amount',
        'total_amount': 'i.total_amount',
        'vat': 'i.total_vat',
        'total_vat': 'i.total_vat',
        'currency': 'i.currency',
        'imported': 'i.created_at',
        'created_at': 'i.created_at',
    }

    def list_unallocated(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        hide_typed: bool = False,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = 'issue_date',
        sort_dir: str = 'desc',
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List invoices that haven't been sent to the main Invoice Module.
        Unallocated = jarvis_invoice_id IS NULL AND ignored = FALSE AND deleted_at IS NULL
        """
        conditions = ['i.jarvis_invoice_id IS NULL', 'i.ignored = FALSE', 'i.deleted_at IS NULL']
        params = {'limit': limit, 'offset': offset}

        if cif_owner:
            conditions.append('i.cif_owner = %(cif_owner)s')
            params['cif_owner'] = cif_owner
        if company_id is not None:
            conditions.append('i.company_id = %(company_id)s')
            params['company_id'] = company_id
        if direction is not None:
            conditions.append('i.direction = %(direction)s')
            params['direction'] = direction.value
        if start_date:
            conditions.append('i.issue_date >= %(start_date)s')
            params['start_date'] = start_date
        if end_date:
            conditions.append('i.issue_date <= %(end_date)s')
            params['end_date'] = end_date
        if search:
            words = [w.strip() for w in search.split() if w.strip()]
            for i, word in enumerate(words):
                param_name = f'search_{i}'
                conditions.append(
                    f"(i.invoice_number ILIKE %({param_name})s OR i.partner_name ILIKE %({param_name})s OR i.partner_cif ILIKE %({param_name})s)"
                )
                params[param_name] = f'%{word}%'
        if hide_typed:
            conditions.append("""
                NOT (
                    -- All types are hidden via override (has hidden AND no non-hidden)
                    (i.type_override IS NOT NULL AND EXISTS (
                        SELECT 1 FROM efactura_supplier_types pt
                        WHERE pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                            AND i.type_override ILIKE '%%' || pt.name || '%%'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM efactura_supplier_types pt
                        WHERE pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                            AND i.type_override ILIKE '%%' || pt.name || '%%'
                    ))
                    OR
                    -- All types are hidden via supplier mapping (company-specific > global)
                    (i.type_override IS NULL AND EXISTS (
                        SELECT 1 FROM efactura_supplier_mapping_types smt
                        JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                        WHERE smt.mapping_id = (
                            SELECT sm2.id FROM efactura_supplier_mappings sm2
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND (sm2.company_id IS NULL OR sm2.company_id = i.company_id)
                            ORDER BY sm2.company_id IS NULL
                            LIMIT 1
                        )
                        AND pt.is_active = TRUE
                        AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                    ) AND NOT EXISTS (
                        SELECT 1 FROM efactura_supplier_mapping_types smt
                        JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                        WHERE smt.mapping_id = (
                            SELECT sm2.id FROM efactura_supplier_mappings sm2
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND (sm2.company_id IS NULL OR sm2.company_id = i.company_id)
                            ORDER BY sm2.company_id IS NULL
                            LIMIT 1
                        )
                        AND pt.is_active = TRUE
                        AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                    ))
                )
            """)

        where_clause = ' AND '.join(conditions)
        db_column = self.SORT_COLUMNS.get(sort_by, 'i.issue_date')
        sort_direction = 'ASC' if sort_dir.lower() == 'asc' else 'DESC'
        order_clause = f"{db_column} {sort_direction}, i.id {sort_direction}"

        def _work(cursor):
            # Get total count
            cursor.execute(f"""
                SELECT COUNT(*) as total FROM efactura_invoices i
                WHERE {where_clause}
            """, params)
            total = cursor.fetchone()['total']

            # Count hidden by filter if needed
            hidden_by_filter = 0
            if hide_typed:
                base_conditions = [c for c in conditions if 'hide_in_filter' not in c]
                base_where = ' AND '.join(base_conditions)
                cursor.execute(f"""
                    SELECT COUNT(*) as total FROM efactura_invoices i
                    WHERE {base_where}
                """, params)
                total_without_filter = cursor.fetchone()['total']
                hidden_by_filter = total_without_filter - total

            # OPTIMIZED: Fetch invoices and mappings without correlated subquery
            cursor.execute(f"""
                SELECT i.*,
                    sm.id as mapping_id,
                    sm.department as mapping_department,
                    sm.subdepartment as mapping_subdepartment,
                    sm.brand as mapping_brand
                FROM efactura_invoices i
                LEFT JOIN LATERAL (
                    SELECT sm2.* FROM efactura_supplier_mappings sm2
                    WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name) AND sm2.is_active = TRUE
                      AND (sm2.company_id IS NULL OR sm2.company_id = i.company_id)
                    ORDER BY sm2.company_id IS NULL
                    LIMIT 1
                ) sm ON TRUE
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)
            rows = cursor.fetchall()

            # Batch fetch type_names for mapping IDs
            mapping_ids = [r['mapping_id'] for r in rows if r.get('mapping_id')]
            type_names_map = {}
            if mapping_ids:
                cursor.execute("""
                    SELECT smt.mapping_id, array_agg(pt.name ORDER BY pt.name) as type_names
                    FROM efactura_supplier_mapping_types smt
                    JOIN efactura_supplier_types pt ON smt.type_id = pt.id
                    WHERE smt.mapping_id = ANY(%s)
                    GROUP BY smt.mapping_id
                """, (mapping_ids,))
                for type_row in cursor.fetchall():
                    type_names_map[type_row['mapping_id']] = type_row['type_names'] or []

            # Build invoice list with merged data
            invoices = []
            for row in rows:
                inv = self._row_to_invoice(row)
                inv_dict = inv.__dict__.copy()
                mapping_id = row.get('mapping_id')
                type_names = type_names_map.get(mapping_id, []) if mapping_id else []
                inv_dict['type_names'] = type_names
                inv_dict['type_override'] = row.get('type_override')
                inv_dict['type_name'] = row.get('type_override') or (', '.join(type_names) if type_names else None)
                inv_dict['department_override'] = row.get('department_override')
                inv_dict['mapping_department'] = row.get('mapping_department')
                inv_dict['department'] = row.get('department_override') or row.get('mapping_department')
                inv_dict['subdepartment_override'] = row.get('subdepartment_override')
                inv_dict['mapping_subdepartment'] = row.get('mapping_subdepartment')
                inv_dict['subdepartment'] = row.get('subdepartment_override') or row.get('mapping_subdepartment')
                inv_dict['department_override_2'] = row.get('department_override_2')
                inv_dict['subdepartment_override_2'] = row.get('subdepartment_override_2')
                raw_observers = row.get('observer_user_ids')
                inv_dict['observer_user_ids'] = list(raw_observers) if raw_observers else []
                invoices.append(inv_dict)

            return invoices, total, hidden_by_filter
        return self.execute_many(_work)

    def count_unallocated(self, cif_owner: Optional[str] = None) -> int:
        """Count unallocated invoices (excluding ignored and deleted)."""
        if cif_owner:
            row = self.query_one("""
                SELECT COUNT(*) as total FROM efactura_invoices
                WHERE jarvis_invoice_id IS NULL AND ignored = FALSE AND deleted_at IS NULL AND cif_owner = %s
            """, (cif_owner,))
        else:
            row = self.query_one("""
                SELECT COUNT(*) as total FROM efactura_invoices
                WHERE jarvis_invoice_id IS NULL AND ignored = FALSE AND deleted_at IS NULL
            """)
        return row['total']

    def get_unallocated_ids(
        self,
        company_id: Optional[int] = None,
        direction: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        hide_typed: bool = False,
    ) -> List[int]:
        """Get all IDs of unallocated invoices (for select all functionality)."""
        where_clauses = ["i.jarvis_invoice_id IS NULL", "i.deleted_at IS NULL", "i.ignored = FALSE"]
        params = {}

        if company_id:
            where_clauses.append("i.company_id = %(company_id)s")
            params['company_id'] = company_id
        if direction:
            where_clauses.append("i.direction = %(direction)s")
            params['direction'] = direction
        if start_date:
            where_clauses.append("i.issue_date >= %(start_date)s")
            params['start_date'] = start_date
        if end_date:
            where_clauses.append("i.issue_date <= %(end_date)s")
            params['end_date'] = end_date
        if search:
            where_clauses.append("(i.partner_name ILIKE %(search)s OR i.invoice_number ILIKE %(search)s)")
            params['search'] = f"%{search}%"

        if hide_typed:
            where_clauses.append("""
                NOT (
                    (i.type_override IS NOT NULL AND EXISTS (
                        SELECT 1 FROM efactura_supplier_types pt
                        WHERE pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                            AND i.type_override ILIKE '%%' || pt.name || '%%'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM efactura_supplier_types pt
                        WHERE pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                            AND i.type_override ILIKE '%%' || pt.name || '%%'
                    ))
                    OR
                    (i.type_override IS NULL AND EXISTS (
                        SELECT 1 FROM efactura_supplier_mappings sm2
                        JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                        JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                        WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                            AND sm2.is_active = TRUE
                            AND pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                    ) AND NOT EXISTS (
                        SELECT 1 FROM efactura_supplier_mappings sm2
                        JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                        JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                        WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                            AND sm2.is_active = TRUE
                            AND pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                    ))
                )
            """)

        where_clause = " AND ".join(where_clauses)
        rows = self.query_all(
            f"SELECT i.id FROM efactura_invoices i WHERE {where_clause}", params
        )
        return [row['id'] for row in rows]

    # ============================================
    # Hidden Invoices (soft delete / ignored)
    # ============================================

    def list_hidden(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Invoice], int]:
        """List hidden invoices based on type settings."""
        conditions = ['i.deleted_at IS NULL', 'i.jarvis_invoice_id IS NULL']
        params = {'limit': limit, 'offset': offset}

        conditions.append("""
            (
                -- Manually ignored by user
                i.ignored = TRUE
                OR
                -- All types are hidden via override (has hidden type AND no non-hidden type)
                (i.type_override IS NOT NULL AND EXISTS (
                    SELECT 1 FROM efactura_supplier_types pt
                    WHERE pt.is_active = TRUE
                        AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                        AND i.type_override ILIKE '%%' || pt.name || '%%'
                ) AND NOT EXISTS (
                    SELECT 1 FROM efactura_supplier_types pt
                    WHERE pt.is_active = TRUE
                        AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                        AND i.type_override ILIKE '%%' || pt.name || '%%'
                ))
                OR
                -- All types are hidden via supplier mapping (has hidden type AND no non-hidden type)
                (i.type_override IS NULL AND EXISTS (
                    SELECT 1 FROM efactura_supplier_mappings sm2
                    JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                    JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                    WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                        AND sm2.is_active = TRUE
                        AND pt.is_active = TRUE
                        AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                ) AND NOT EXISTS (
                    SELECT 1 FROM efactura_supplier_mappings sm2
                    JOIN efactura_supplier_mapping_types smt ON smt.mapping_id = sm2.id
                    JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                    WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                        AND sm2.is_active = TRUE
                        AND pt.is_active = TRUE
                        AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                ))
            )
        """)

        if cif_owner:
            conditions.append('i.cif_owner = %(cif_owner)s')
            params['cif_owner'] = cif_owner
        if company_id is not None:
            conditions.append('i.company_id = %(company_id)s')
            params['company_id'] = company_id
        if direction is not None:
            conditions.append('i.direction = %(direction)s')
            params['direction'] = direction.value
        if start_date:
            conditions.append('i.issue_date >= %(start_date)s')
            params['start_date'] = start_date
        if end_date:
            conditions.append('i.issue_date <= %(end_date)s')
            params['end_date'] = end_date
        if search:
            words = [w.strip() for w in search.split() if w.strip()]
            for i, word in enumerate(words):
                param_name = f'search_{i}'
                conditions.append(
                    f"(i.invoice_number ILIKE %({param_name})s OR i.partner_name ILIKE %({param_name})s OR i.partner_cif ILIKE %({param_name})s)"
                )
                params[param_name] = f'%{word}%'

        where_clause = ' AND '.join(conditions)

        def _work(cursor):
            cursor.execute(f"""
                SELECT COUNT(*) as total FROM efactura_invoices i
                WHERE {where_clause}
            """, params)
            total = cursor.fetchone()['total']

            cursor.execute(f"""
                SELECT i.*,
                    COALESCE(
                        (SELECT array_agg(pt.name ORDER BY pt.name)
                         FROM efactura_supplier_mapping_types smt
                         JOIN efactura_supplier_types pt ON smt.type_id = pt.id
                         WHERE smt.mapping_id = sm.id),
                        ARRAY[]::text[]
                    ) as type_names
                FROM efactura_invoices i
                LEFT JOIN LATERAL (
                    SELECT sm2.* FROM efactura_supplier_mappings sm2
                    WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name) AND sm2.is_active = TRUE
                      AND (sm2.company_id IS NULL OR sm2.company_id = i.company_id)
                    ORDER BY sm2.company_id IS NULL
                    LIMIT 1
                ) sm ON TRUE
                WHERE {where_clause}
                ORDER BY i.updated_at DESC, i.id DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)

            invoices = []
            for row in cursor.fetchall():
                inv = self._row_to_invoice(row)
                inv_dict = inv.__dict__.copy()
                type_names = row.get('type_names') or []
                inv_dict['type_names'] = type_names
                inv_dict['type_name'] = ', '.join(type_names) if type_names else None
                raw_observers = row.get('observer_user_ids')
                inv_dict['observer_user_ids'] = list(raw_observers) if raw_observers else []
                invoices.append(inv_dict)

            return invoices, total
        return self.execute_many(_work)

    def count_hidden(self) -> int:
        """Count hidden invoices (manually ignored OR all types hidden)."""
        row = self.query_one("""
            SELECT COUNT(*) as total FROM efactura_invoices i
            WHERE i.deleted_at IS NULL
                AND i.jarvis_invoice_id IS NULL
                AND (
                    -- Manually ignored by user
                    i.ignored = TRUE
                    OR
                    -- All types are hidden via override (has hidden AND no non-hidden)
                    (i.type_override IS NOT NULL AND EXISTS (
                        SELECT 1 FROM efactura_supplier_types pt
                        WHERE pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                            AND i.type_override ILIKE '%%' || pt.name || '%%'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM efactura_supplier_types pt
                        WHERE pt.is_active = TRUE
                            AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                            AND i.type_override ILIKE '%%' || pt.name || '%%'
                    ))
                    OR
                    -- All types are hidden via supplier mapping (company-specific > global)
                    (i.type_override IS NULL AND EXISTS (
                        SELECT 1 FROM efactura_supplier_mapping_types smt
                        JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                        WHERE smt.mapping_id = (
                            SELECT sm2.id FROM efactura_supplier_mappings sm2
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND (sm2.company_id IS NULL OR sm2.company_id = i.company_id)
                            ORDER BY sm2.company_id IS NULL
                            LIMIT 1
                        )
                        AND pt.is_active = TRUE
                        AND COALESCE(pt.hide_in_filter, TRUE) = TRUE
                    ) AND NOT EXISTS (
                        SELECT 1 FROM efactura_supplier_mapping_types smt
                        JOIN efactura_supplier_types pt ON pt.id = smt.type_id
                        WHERE smt.mapping_id = (
                            SELECT sm2.id FROM efactura_supplier_mappings sm2
                            WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name)
                                AND sm2.is_active = TRUE
                                AND (sm2.company_id IS NULL OR sm2.company_id = i.company_id)
                            ORDER BY sm2.company_id IS NULL
                            LIMIT 1
                        )
                        AND pt.is_active = TRUE
                        AND COALESCE(pt.hide_in_filter, TRUE) = FALSE
                    ))
                )
        """)
        return row['total']

    def restore_from_hidden(self, invoice_id: int) -> bool:
        """Restore an invoice from hidden (unignore)."""
        return self.ignore_invoice(invoice_id, ignored=False)

    def bulk_hide(self, invoice_ids: List[int]) -> int:
        """Hide multiple invoices (set ignored = TRUE)."""
        if not invoice_ids:
            return 0
        try:
            placeholders = ','.join(['%s'] * len(invoice_ids))
            count = self.execute(f"""
                UPDATE efactura_invoices
                SET ignored = TRUE, updated_at = NOW()
                WHERE id IN ({placeholders}) AND ignored = FALSE AND deleted_at IS NULL
            """, invoice_ids)
            logger.info(f"Bulk hidden {count} invoices")
            return count
        except Exception as e:
            logger.error(f"Failed to bulk hide invoices: {e}")
            return 0

    def bulk_restore_from_hidden(self, invoice_ids: List[int]) -> int:
        """Restore multiple invoices from hidden (set ignored = FALSE)."""
        if not invoice_ids:
            return 0
        try:
            placeholders = ','.join(['%s'] * len(invoice_ids))
            count = self.execute(f"""
                UPDATE efactura_invoices
                SET ignored = FALSE, updated_at = NOW()
                WHERE id IN ({placeholders}) AND ignored = TRUE AND deleted_at IS NULL
            """, invoice_ids)
            logger.info(f"Bulk restored {count} invoices from hidden")
            return count
        except Exception as e:
            logger.error(f"Failed to bulk restore invoices from hidden: {e}")
            return 0

    # ============================================
    # Bin (soft delete / deleted_at)
    # ============================================

    def list_deleted(
        self,
        cif_owner: Optional[str] = None,
        company_id: Optional[int] = None,
        direction: Optional[InvoiceDirection] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List deleted invoices (bin). Deleted = deleted_at IS NOT NULL."""
        conditions = ['i.deleted_at IS NOT NULL']
        params = {'limit': limit, 'offset': offset}

        if cif_owner:
            conditions.append('i.cif_owner = %(cif_owner)s')
            params['cif_owner'] = cif_owner
        if company_id is not None:
            conditions.append('i.company_id = %(company_id)s')
            params['company_id'] = company_id
        if direction is not None:
            conditions.append('i.direction = %(direction)s')
            params['direction'] = direction.value
        if start_date:
            conditions.append('i.issue_date >= %(start_date)s')
            params['start_date'] = start_date
        if end_date:
            conditions.append('i.issue_date <= %(end_date)s')
            params['end_date'] = end_date
        if search:
            words = [w.strip() for w in search.split() if w.strip()]
            for i, word in enumerate(words):
                param_name = f'search_{i}'
                conditions.append(
                    f"(i.invoice_number ILIKE %({param_name})s OR i.partner_name ILIKE %({param_name})s OR i.partner_cif ILIKE %({param_name})s)"
                )
                params[param_name] = f'%{word}%'

        where_clause = ' AND '.join(conditions)

        def _work(cursor):
            cursor.execute(f"""
                SELECT COUNT(*) as total FROM efactura_invoices i
                WHERE {where_clause}
            """, params)
            total = cursor.fetchone()['total']

            cursor.execute(f"""
                SELECT i.*, i.deleted_at,
                    COALESCE(
                        (SELECT array_agg(pt.name ORDER BY pt.name)
                         FROM efactura_supplier_mapping_types smt
                         JOIN efactura_supplier_types pt ON smt.type_id = pt.id
                         WHERE smt.mapping_id = sm.id),
                        ARRAY[]::text[]
                    ) as type_names
                FROM efactura_invoices i
                LEFT JOIN LATERAL (
                    SELECT sm2.* FROM efactura_supplier_mappings sm2
                    WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name) AND sm2.is_active = TRUE
                      AND (sm2.company_id IS NULL OR sm2.company_id = i.company_id)
                    ORDER BY sm2.company_id IS NULL
                    LIMIT 1
                ) sm ON TRUE
                WHERE {where_clause}
                ORDER BY i.deleted_at DESC, i.id DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)

            invoices = []
            for row in cursor.fetchall():
                inv = self._row_to_invoice(row)
                type_names = row.get('type_names') or []
                invoices.append({
                    **inv.__dict__,
                    'deleted_at': row.get('deleted_at'),
                    'type_names': type_names,
                    'type_name': ', '.join(type_names) if type_names else None,
                })

            return invoices, total
        return self.execute_many(_work)

    def count_deleted(self) -> int:
        """Count deleted invoices (bin)."""
        row = self.query_one("""
            SELECT COUNT(*) as total FROM efactura_invoices
            WHERE deleted_at IS NOT NULL
        """)
        return row['total']

    def delete_invoice(self, invoice_id: int) -> bool:
        """Move an invoice to the bin (set deleted_at)."""
        try:
            deleted = self.execute("""
                UPDATE efactura_invoices
                SET deleted_at = NOW(), updated_at = NOW()
                WHERE id = %s AND deleted_at IS NULL
            """, (invoice_id,)) > 0
            if deleted:
                logger.info(f"Invoice {invoice_id} moved to bin")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete invoice: {e}")
            return False

    def restore_from_bin(self, invoice_id: int) -> bool:
        """Restore an invoice from the bin."""
        try:
            restored = self.execute("""
                UPDATE efactura_invoices
                SET deleted_at = NULL, updated_at = NOW()
                WHERE id = %s AND deleted_at IS NOT NULL
            """, (invoice_id,)) > 0
            if restored:
                logger.info(f"Invoice {invoice_id} restored from bin")
            return restored
        except Exception as e:
            logger.error(f"Failed to restore invoice from bin: {e}")
            return False

    def permanent_delete(self, invoice_id: int) -> bool:
        """Permanently delete an invoice from the bin."""
        try:
            deleted = self.execute("""
                DELETE FROM efactura_invoices
                WHERE id = %s AND deleted_at IS NOT NULL
            """, (invoice_id,)) > 0
            if deleted:
                logger.info(f"Invoice {invoice_id} permanently deleted")
            return deleted
        except Exception as e:
            logger.error(f"Failed to permanently delete invoice: {e}")
            return False

    def bulk_delete(self, invoice_ids: List[int]) -> int:
        """Move multiple invoices to the bin."""
        if not invoice_ids:
            return 0
        try:
            placeholders = ','.join(['%s'] * len(invoice_ids))
            count = self.execute(f"""
                UPDATE efactura_invoices
                SET deleted_at = NOW(), updated_at = NOW()
                WHERE id IN ({placeholders}) AND deleted_at IS NULL
            """, invoice_ids)
            logger.info(f"Bulk deleted {count} invoices to bin")
            return count
        except Exception as e:
            logger.error(f"Failed to bulk delete invoices: {e}")
            return 0

    def bulk_restore_from_bin(self, invoice_ids: List[int]) -> int:
        """Restore multiple invoices from the bin."""
        if not invoice_ids:
            return 0
        try:
            placeholders = ','.join(['%s'] * len(invoice_ids))
            count = self.execute(f"""
                UPDATE efactura_invoices
                SET deleted_at = NULL, updated_at = NOW()
                WHERE id IN ({placeholders}) AND deleted_at IS NOT NULL
            """, invoice_ids)
            logger.info(f"Bulk restored {count} invoices from bin")
            return count
        except Exception as e:
            logger.error(f"Failed to bulk restore invoices from bin: {e}")
            return 0

    def bulk_permanent_delete(self, invoice_ids: List[int]) -> int:
        """Permanently delete multiple invoices from the bin."""
        if not invoice_ids:
            return 0
        try:
            placeholders = ','.join(['%s'] * len(invoice_ids))
            count = self.execute(f"""
                DELETE FROM efactura_invoices
                WHERE id IN ({placeholders}) AND deleted_at IS NOT NULL
            """, invoice_ids)
            logger.info(f"Bulk permanently deleted {count} invoices")
            return count
        except Exception as e:
            logger.error(f"Failed to bulk permanently delete invoices: {e}")
            return 0

    def is_allocated(self, invoice_id: int) -> bool:
        """Check if an invoice has been allocated to the main Invoice Module."""
        row = self.query_one(
            'SELECT jarvis_invoice_id FROM efactura_invoices WHERE id = %s', (invoice_id,)
        )
        if row is None:
            return False
        return row['jarvis_invoice_id'] is not None

    def mark_allocated(self, invoice_id: int, jarvis_invoice_id: int):
        """Mark an invoice as allocated to the main Invoice Module."""
        self.execute("""
            UPDATE efactura_invoices
            SET jarvis_invoice_id = %s, updated_at = NOW()
            WHERE id = %s
        """, (jarvis_invoice_id, invoice_id))
        logger.info(
            "Invoice marked as allocated",
            extra={
                'efactura_invoice_id': invoice_id,
                'jarvis_invoice_id': jarvis_invoice_id,
            }
        )

    def get_invoices_for_module(
        self,
        invoice_ids: List[int],
    ) -> List[Dict[str, Any]]:
        """
        Batch fetch invoices for sending to Invoice Module.
        Fetches only unallocated invoices with all columns needed for
        creating main invoices AND allocations.
        """
        if not invoice_ids:
            return []

        rows = self.query_all("""
            SELECT
                i.id,
                i.partner_name,
                i.partner_cif,
                i.invoice_number,
                i.invoice_series,
                i.issue_date,
                i.total_amount,
                i.total_vat,
                i.total_without_vat,
                i.currency,
                i.company_id,
                c.company as company_name,
                i.department_override,
                i.subdepartment_override,
                i.department_override_2,
                i.subdepartment_override_2,
                i.observer_user_ids,
                sm.department as mapping_department,
                sm.subdepartment as mapping_subdepartment,
                sm.brand as mapping_brand,
                (
                    SELECT ds.manager
                    FROM department_structure ds
                    WHERE ds.company = c.company
                        AND ds.department = COALESCE(i.department_override, sm.department)
                    ORDER BY
                        CASE WHEN ds.subdepartment = COALESCE(i.subdepartment_override, sm.subdepartment) THEN 0 ELSE 1 END,
                        ds.id
                    LIMIT 1
                ) as responsible
            FROM efactura_invoices i
            LEFT JOIN companies c ON c.id = i.company_id
            LEFT JOIN LATERAL (
                SELECT sm2.* FROM efactura_supplier_mappings sm2
                WHERE LOWER(i.partner_name) = LOWER(sm2.partner_name) AND sm2.is_active = TRUE
                  AND (sm2.company_id IS NULL OR sm2.company_id = i.company_id)
                ORDER BY sm2.company_id IS NULL
                LIMIT 1
            ) sm ON TRUE
            WHERE i.id = ANY(%s)
            AND i.jarvis_invoice_id IS NULL
            AND i.deleted_at IS NULL
        """, (invoice_ids,))

        result = []
        for row in rows:
            full_number = row['invoice_number']
            if row['invoice_series']:
                full_number = f"{row['invoice_series']}-{row['invoice_number']}"

            effective_department = row['department_override'] or row['mapping_department']
            effective_subdepartment = row['subdepartment_override'] or row['mapping_subdepartment']

            result.append({
                'id': row['id'],
                'partner_name': row['partner_name'],
                'partner_cif': row['partner_cif'],
                'invoice_number': full_number,
                'issue_date': row['issue_date'],
                'total_amount': float(row['total_amount']),
                'total_vat': float(row['total_vat']) if row['total_vat'] else 0.0,
                'total_without_vat': float(row['total_without_vat']) if row['total_without_vat'] else None,
                'currency': row['currency'],
                'company_id': row['company_id'],
                'company_name': row['company_name'],
                'department': effective_department,
                'subdepartment': effective_subdepartment,
                'department_override_2': row['department_override_2'],
                'subdepartment_override_2': row['subdepartment_override_2'],
                'brand': row['mapping_brand'],
                'responsible': row['responsible'],
                'observer_user_ids': list(row['observer_user_ids']) if row.get('observer_user_ids') else [],
            })

        logger.info(
            f"Batch fetched {len(result)} invoices for module (requested: {len(invoice_ids)})"
        )
        return result

    def bulk_mark_allocated(
        self,
        mappings: List[Tuple[int, int]],
    ) -> int:
        """Bulk mark invoices as allocated using unnest for performance."""
        if not mappings:
            return 0

        efactura_ids = [m[0] for m in mappings]
        jarvis_ids = [m[1] for m in mappings]

        def _work(cursor):
            cursor.execute("""
                UPDATE efactura_invoices
                SET
                    jarvis_invoice_id = mapping.jarvis_id,
                    updated_at = NOW()
                FROM (
                    SELECT
                        unnest(%s::int[]) AS efactura_id,
                        unnest(%s::int[]) AS jarvis_id
                ) AS mapping
                WHERE efactura_invoices.id = mapping.efactura_id
            """, (efactura_ids, jarvis_ids))
            updated = cursor.rowcount
            logger.info(f"Bulk marked {updated} invoices as allocated")
            return updated
        return self.execute_many(_work)

    def create_with_refs(
        self,
        invoice: Invoice,
        external_ref: InvoiceExternalRef,
        artifact: InvoiceArtifact,
        xml_content: str,
    ) -> Optional[Invoice]:
        """Create invoice with external reference, artifact, and store XML content."""
        def _work(cursor):
            # Insert invoice
            cursor.execute("""
                INSERT INTO efactura_invoices (
                    cif_owner, company_id, direction, partner_cif, partner_name,
                    invoice_number, invoice_series, issue_date, due_date,
                    total_amount, total_vat, total_without_vat, currency,
                    status, xml_content, created_at, updated_at
                ) VALUES (
                    %(cif_owner)s, %(company_id)s, %(direction)s, %(partner_cif)s, %(partner_name)s,
                    %(invoice_number)s, %(invoice_series)s, %(issue_date)s, %(due_date)s,
                    %(total_amount)s, %(total_vat)s, %(total_without_vat)s, %(currency)s,
                    %(status)s, %(xml_content)s, NOW(), NOW()
                )
                RETURNING id, created_at, updated_at
            """, {
                'cif_owner': invoice.cif_owner,
                'company_id': invoice.company_id,
                'direction': invoice.direction.value,
                'partner_cif': invoice.partner_cif,
                'partner_name': invoice.partner_name,
                'invoice_number': invoice.invoice_number,
                'invoice_series': invoice.invoice_series,
                'issue_date': invoice.issue_date,
                'due_date': invoice.due_date,
                'total_amount': str(invoice.total_amount),
                'total_vat': str(invoice.total_vat),
                'total_without_vat': str(invoice.total_without_vat),
                'currency': invoice.currency,
                'status': invoice.status.value,
                'xml_content': xml_content,
            })

            row = cursor.fetchone()
            invoice.id = row['id']
            invoice.created_at = row['created_at']
            invoice.updated_at = row['updated_at']

            # Insert external reference
            external_ref.invoice_id = invoice.id
            cursor.execute("""
                INSERT INTO efactura_invoice_refs (
                    invoice_id, external_system, message_id,
                    upload_id, download_id, xml_hash,
                    created_at
                ) VALUES (
                    %(invoice_id)s, %(external_system)s, %(message_id)s,
                    %(upload_id)s, %(download_id)s, %(xml_hash)s, NOW()
                )
            """, {
                'invoice_id': external_ref.invoice_id,
                'external_system': external_ref.external_system,
                'message_id': external_ref.message_id,
                'upload_id': external_ref.upload_id,
                'download_id': external_ref.download_id,
                'xml_hash': external_ref.xml_hash,
            })

            # Insert artifact reference
            artifact.invoice_id = invoice.id
            cursor.execute("""
                INSERT INTO efactura_invoice_artifacts (
                    invoice_id, artifact_type, storage_uri,
                    original_filename, mime_type, checksum, size_bytes,
                    created_at
                ) VALUES (
                    %(invoice_id)s, %(artifact_type)s, %(storage_uri)s,
                    %(original_filename)s, %(mime_type)s, %(checksum)s,
                    %(size_bytes)s, NOW()
                )
            """, {
                'invoice_id': artifact.invoice_id,
                'artifact_type': artifact.artifact_type.value,
                'storage_uri': artifact.storage_uri,
                'original_filename': artifact.original_filename,
                'mime_type': artifact.mime_type,
                'checksum': artifact.checksum,
                'size_bytes': artifact.size_bytes,
            })

            logger.info(
                "Invoice created with XML content",
                extra={
                    'invoice_id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'message_id': external_ref.message_id,
                }
            )
            return invoice

        try:
            return self.execute_many(_work)
        except Exception as e:
            logger.error(f"Failed to create invoice: {e}")
            return None

    def get_xml_content(self, invoice_id: int) -> Optional[str]:
        """Get stored XML content for an invoice."""
        row = self.query_one(
            'SELECT xml_content FROM efactura_invoices WHERE id = %s', (invoice_id,)
        )
        if row is None:
            return None
        return row.get('xml_content')
