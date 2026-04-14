"""
Supplier Type Repository

Database operations for e-Factura supplier types.
"""

from typing import Optional, List, Dict, Any

from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger

logger = get_logger('jarvis.accounting.efactura.repo.supplier_type')


class SupplierTypeRepository(BaseRepository):
    """Repository for e-Factura supplier types (Service, Merchandise, etc.)."""

    def get_all(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all partner types."""
        if active_only:
            return self.query_all("""
                SELECT id, name, description, is_active,
                       COALESCE(hide_in_filter, TRUE) as hide_in_filter,
                       created_at, updated_at
                FROM efactura_supplier_types
                WHERE is_active = TRUE
                ORDER BY name
            """)
        return self.query_all("""
            SELECT id, name, description, is_active,
                   COALESCE(hide_in_filter, TRUE) as hide_in_filter,
                   created_at, updated_at
            FROM efactura_supplier_types
            ORDER BY name
        """)

    def get_by_id(self, type_id: int) -> Optional[Dict[str, Any]]:
        """Get a single partner type by ID."""
        return self.query_one("""
            SELECT id, name, description, is_active,
                   COALESCE(hide_in_filter, TRUE) as hide_in_filter,
                   created_at, updated_at
            FROM efactura_supplier_types
            WHERE id = %s
        """, (type_id,))

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a single partner type by name."""
        return self.query_one("""
            SELECT id, name, description, is_active,
                   COALESCE(hide_in_filter, TRUE) as hide_in_filter,
                   created_at, updated_at
            FROM efactura_supplier_types
            WHERE name = %s AND is_active = TRUE
        """, (name,))

    def create(
        self,
        name: str,
        description: Optional[str] = None,
        hide_in_filter: bool = True,
    ) -> int:
        """Create a new partner type."""
        row = self.execute("""
            INSERT INTO efactura_supplier_types (name, description, hide_in_filter)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (name, description, hide_in_filter), returning=True)
        type_id = row['id']
        logger.info(f"Created partner type {type_id}: {name}")
        return type_id

    def update(
        self,
        type_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        hide_in_filter: Optional[bool] = None,
    ) -> bool:
        """Update a partner type."""
        updates = ['updated_at = NOW()']
        params = []

        if name is not None:
            updates.append('name = %s')
            params.append(name)
        if description is not None:
            updates.append('description = %s')
            params.append(description if description else None)
        if is_active is not None:
            updates.append('is_active = %s')
            params.append(is_active)
        if hide_in_filter is not None:
            updates.append('hide_in_filter = %s')
            params.append(hide_in_filter)

        params.append(type_id)

        try:
            success = self.execute(f"""
                UPDATE efactura_supplier_types
                SET {', '.join(updates)}
                WHERE id = %s
            """, tuple(params)) > 0
            if success:
                logger.info(f"Updated partner type {type_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to update partner type: {e}")
            return False

    def delete(self, type_id: int) -> bool:
        """Delete a partner type (soft delete by setting is_active = FALSE)."""
        try:
            success = self.execute("""
                UPDATE efactura_supplier_types
                SET is_active = FALSE, updated_at = NOW()
                WHERE id = %s
            """, (type_id,)) > 0
            if success:
                logger.info(f"Soft-deleted partner type {type_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to delete partner type: {e}")
            return False
