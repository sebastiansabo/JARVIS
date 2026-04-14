"""
Supplier Mapping Repository

Database operations for e-Factura supplier mappings.
"""

from typing import Optional, List, Dict, Any, Tuple

from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger

logger = get_logger('jarvis.accounting.efactura.repo.supplier_mapping')


class SupplierMappingRepository(BaseRepository):
    """Repository for e-Factura supplier mappings."""

    def get_all(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all supplier mappings with their types."""
        where_clause = "WHERE m.is_active = TRUE" if active_only else ""
        rows = self.query_all(f"""
            SELECT m.id, m.partner_name, m.partner_cif, m.supplier_name, m.supplier_note,
                   m.supplier_vat, m.kod_konto, m.type_id, m.is_active, m.created_at, m.updated_at,
                   m.brand, m.department, m.subdepartment,
                   m.company_id, co.company as company_name,
                   COALESCE(
                       (SELECT array_agg(pt.id ORDER BY pt.name)
                        FROM efactura_supplier_mapping_types smt
                        JOIN efactura_supplier_types pt ON smt.type_id = pt.id
                        WHERE smt.mapping_id = m.id),
                       ARRAY[]::integer[]
                   ) as type_ids,
                   COALESCE(
                       (SELECT array_agg(pt.name ORDER BY pt.name)
                        FROM efactura_supplier_mapping_types smt
                        JOIN efactura_supplier_types pt ON smt.type_id = pt.id
                        WHERE smt.mapping_id = m.id),
                       ARRAY[]::text[]
                   ) as type_names
            FROM efactura_supplier_mappings m
            LEFT JOIN companies co ON co.id = m.company_id
            {where_clause}
            ORDER BY m.partner_name
        """)
        results = []
        for row in rows:
            row['type_ids'] = list(row['type_ids']) if row['type_ids'] else []
            row['type_names'] = list(row['type_names']) if row['type_names'] else []
            row['type_name'] = row['type_names'][0] if row['type_names'] else None
            results.append(row)
        return results

    def get_by_id(self, mapping_id: int) -> Optional[Dict[str, Any]]:
        """Get a single supplier mapping by ID with its types."""
        row = self.query_one("""
            SELECT m.id, m.partner_name, m.partner_cif, m.supplier_name, m.supplier_note,
                   m.supplier_vat, m.kod_konto, m.type_id, m.is_active, m.created_at, m.updated_at,
                   m.brand, m.department, m.subdepartment,
                   m.company_id, co.company as company_name,
                   COALESCE(
                       (SELECT array_agg(pt.id ORDER BY pt.name)
                        FROM efactura_supplier_mapping_types smt
                        JOIN efactura_supplier_types pt ON smt.type_id = pt.id
                        WHERE smt.mapping_id = m.id),
                       ARRAY[]::integer[]
                   ) as type_ids,
                   COALESCE(
                       (SELECT array_agg(pt.name ORDER BY pt.name)
                        FROM efactura_supplier_mapping_types smt
                        JOIN efactura_supplier_types pt ON smt.type_id = pt.id
                        WHERE smt.mapping_id = m.id),
                       ARRAY[]::text[]
                   ) as type_names
            FROM efactura_supplier_mappings m
            LEFT JOIN companies co ON co.id = m.company_id
            WHERE m.id = %s
        """, (mapping_id,))
        if not row:
            return None
        row['type_ids'] = list(row['type_ids']) if row['type_ids'] else []
        row['type_names'] = list(row['type_names']) if row['type_names'] else []
        row['type_name'] = row['type_names'][0] if row['type_names'] else None
        return row

    def find_by_supplier(
        self,
        partner_name: str,
        partner_cif: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a mapping by partner name and optionally CIF."""
        if partner_cif:
            row = self.query_one("""
                SELECT m.id, m.partner_name, m.partner_cif, m.supplier_name, m.supplier_note,
                       m.supplier_vat, m.kod_konto, m.type_id, m.is_active, m.created_at, m.updated_at,
                       pt.name as type_name
                FROM efactura_supplier_mappings m
                LEFT JOIN efactura_supplier_types pt ON m.type_id = pt.id
                WHERE LOWER(m.partner_name) = LOWER(%s) AND m.partner_cif = %s AND m.is_active = TRUE
                LIMIT 1
            """, (partner_name, partner_cif))
            if row:
                return row

        return self.query_one("""
            SELECT m.id, m.partner_name, m.partner_cif, m.supplier_name, m.supplier_note,
                   m.supplier_vat, m.kod_konto, m.type_id, m.is_active, m.created_at, m.updated_at,
                   pt.name as type_name
            FROM efactura_supplier_mappings m
            LEFT JOIN efactura_supplier_types pt ON m.type_id = pt.id
            WHERE LOWER(m.partner_name) = LOWER(%s) AND m.is_active = TRUE
            LIMIT 1
        """, (partner_name,))

    def create(
        self,
        partner_name: str,
        supplier_name: str,
        partner_cif: Optional[str] = None,
        supplier_note: Optional[str] = None,
        supplier_vat: Optional[str] = None,
        kod_konto: Optional[str] = None,
        type_id: Optional[int] = None,
        type_ids: Optional[List[int]] = None,
        department: Optional[str] = None,
        subdepartment: Optional[str] = None,
        brand: Optional[str] = None,
        company_id: Optional[int] = None,
    ) -> int:
        """Create a new supplier mapping."""
        def _work(cursor):
            cursor.execute("""
                INSERT INTO efactura_supplier_mappings
                (partner_name, partner_cif, supplier_name, supplier_note, supplier_vat, kod_konto, type_id, department, subdepartment, brand, company_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (partner_name, partner_cif, supplier_name, supplier_note, supplier_vat, kod_konto, type_id, department, subdepartment, brand, company_id))
            mapping_id = cursor.fetchone()['id']

            # Insert types into junction table
            if type_ids:
                for tid in type_ids:
                    cursor.execute("""
                        INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
                        VALUES (%s, %s)
                        ON CONFLICT (mapping_id, type_id) DO NOTHING
                    """, (mapping_id, tid))
            elif type_id:
                cursor.execute("""
                    INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
                    VALUES (%s, %s)
                    ON CONFLICT (mapping_id, type_id) DO NOTHING
                """, (mapping_id, type_id))

            logger.info(f"Created supplier mapping {mapping_id}: {partner_name} -> {supplier_name}")
            return mapping_id
        return self.execute_many(_work)

    def update(
        self,
        mapping_id: int,
        partner_name: Optional[str] = None,
        partner_cif: Optional[str] = None,
        supplier_name: Optional[str] = None,
        supplier_note: Optional[str] = None,
        supplier_vat: Optional[str] = None,
        kod_konto: Optional[str] = None,
        type_id: Optional[int] = None,
        type_ids: Optional[List[int]] = None,
        is_active: Optional[bool] = None,
        department: Optional[str] = None,
        subdepartment: Optional[str] = None,
        brand: Optional[str] = None,
        company_id: object = 'NOT_SET',
    ) -> bool:
        """Update a supplier mapping."""
        def _work(cursor):
            updates = ['updated_at = NOW()']
            params = []

            if partner_name is not None:
                updates.append('partner_name = %s')
                params.append(partner_name)
            if partner_cif is not None:
                updates.append('partner_cif = %s')
                params.append(partner_cif if partner_cif else None)
            if supplier_name is not None:
                updates.append('supplier_name = %s')
                params.append(supplier_name)
            if supplier_note is not None:
                updates.append('supplier_note = %s')
                params.append(supplier_note if supplier_note else None)
            if supplier_vat is not None:
                updates.append('supplier_vat = %s')
                params.append(supplier_vat if supplier_vat else None)
            if kod_konto is not None:
                updates.append('kod_konto = %s')
                params.append(kod_konto if kod_konto else None)
            if type_id is not None:
                updates.append('type_id = %s')
                params.append(type_id if type_id else None)
            if is_active is not None:
                updates.append('is_active = %s')
                params.append(is_active)
            if department is not None:
                updates.append('department = %s')
                params.append(department if department else None)
            if subdepartment is not None:
                updates.append('subdepartment = %s')
                params.append(subdepartment if subdepartment else None)
            if brand is not None:
                updates.append('brand = %s')
                params.append(brand if brand else None)
            if company_id != 'NOT_SET':
                updates.append('company_id = %s')
                params.append(company_id if company_id else None)

            params.append(mapping_id)

            cursor.execute(f"""
                UPDATE efactura_supplier_mappings
                SET {', '.join(updates)}
                WHERE id = %s
            """, tuple(params))

            success = cursor.rowcount > 0

            # Update types in junction table if type_ids is provided
            if type_ids is not None:
                cursor.execute(
                    'DELETE FROM efactura_supplier_mapping_types WHERE mapping_id = %s',
                    (mapping_id,)
                )
                for tid in type_ids:
                    cursor.execute("""
                        INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
                        VALUES (%s, %s)
                        ON CONFLICT (mapping_id, type_id) DO NOTHING
                    """, (mapping_id, tid))

            if success:
                logger.info(f"Updated supplier mapping {mapping_id}")
            return success
        try:
            return self.execute_many(_work)
        except Exception as e:
            logger.error(f"Failed to update supplier mapping: {e}")
            return False

    def delete(self, mapping_id: int) -> bool:
        """Delete a supplier mapping."""
        try:
            success = self.execute(
                'DELETE FROM efactura_supplier_mappings WHERE id = %s', (mapping_id,)
            ) > 0
            if success:
                logger.info(f"Deleted supplier mapping {mapping_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to delete supplier mapping: {e}")
            return False

    def get_distinct_suppliers(self) -> List[Dict[str, Any]]:
        """Get distinct partner names and CIFs from e-Factura invoices."""
        return self.query_all("""
            SELECT DISTINCT partner_name, partner_cif, COUNT(*) as invoice_count
            FROM efactura_invoices
            WHERE partner_name IS NOT NULL
              AND deleted_at IS NULL
            GROUP BY partner_name, partner_cif
            ORDER BY COUNT(*) DESC, partner_name
        """)

    def migrate_junction_table(self) -> int:
        """One-time migration to create the supplier mapping types junction table."""
        def _work(cursor):
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS efactura_supplier_mapping_types (
                    mapping_id INTEGER NOT NULL REFERENCES efactura_supplier_mappings(id) ON DELETE CASCADE,
                    type_id INTEGER NOT NULL REFERENCES efactura_supplier_types(id) ON DELETE CASCADE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (mapping_id, type_id)
                )
            ''')
            # Need explicit commit for DDL before DML in same transaction
            # (execute_many will commit at end)

            # Migrate existing type_id data
            cursor.execute('''
                INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
                SELECT id, type_id FROM efactura_supplier_mappings
                WHERE type_id IS NOT NULL
                ON CONFLICT (mapping_id, type_id) DO NOTHING
            ''')

            cursor.execute('SELECT COUNT(*) as count FROM efactura_supplier_mapping_types')
            result = cursor.fetchone()
            count = result['count'] if result else 0
            logger.info(f"Junction table migration completed. {count} records in table.")
            return count
        return self.execute_many(_work)

    def bulk_set_types(self, mapping_ids: List[int], type_id: Optional[int]) -> Tuple[int, List[str]]:
        """Bulk set type for multiple supplier mappings."""
        def _work(cursor):
            partner_names = []

            if type_id:
                cursor.execute(
                    "SELECT id, partner_name FROM efactura_supplier_mappings WHERE id = ANY(%s)",
                    (mapping_ids,)
                )
                partner_names = [row['partner_name'] for row in cursor.fetchall()]

            updated_count = 0
            for mid in mapping_ids:
                cursor.execute(
                    "DELETE FROM efactura_supplier_mapping_types WHERE mapping_id = %s", (mid,)
                )
                if type_id:
                    cursor.execute(
                        "INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id) VALUES (%s, %s)",
                        (mid, type_id)
                    )
                cursor.execute(
                    "UPDATE efactura_supplier_mappings SET updated_at = NOW() WHERE id = %s", (mid,)
                )
                updated_count += 1

            logger.info(f"Bulk updated {updated_count} mappings with type_id={type_id}")
            return updated_count, partner_names
        return self.execute_many(_work)

    # ── Cleanup ─────────────────────────────────────────────

    def delete_old_unallocated(self, days: int = 15, cif_owner: str = None) -> int:
        """Permanently delete unallocated invoices older than N days."""
        try:
            sql = """
                DELETE FROM efactura_invoices
                WHERE jarvis_invoice_id IS NULL
                  AND ignored = FALSE
                  AND deleted_at IS NULL
                  AND created_at < NOW() - INTERVAL '%s days'
            """
            params = [days]
            if cif_owner:
                sql += " AND cif_owner = %s"
                params.append(cif_owner)
            count = self.execute(sql, params)
            logger.info(f"Cleaned up {count} old unallocated invoices (>{days} days, cif={cif_owner or 'all'})")
            return count
        except Exception as e:
            logger.error(f"Failed to clean up old unallocated invoices: {e}")
            return 0
