"""Vendor Mapping Repository - Data access for vendor mappings.

Wraps the existing database functions in a repository pattern.
"""
from typing import Optional, List, Dict, Any

from ..database import (
    get_all_vendor_mappings,
    get_vendor_mapping,
    create_vendor_mapping,
    update_vendor_mapping,
    delete_vendor_mapping,
    seed_vendor_mappings,
)


class VendorMappingRepository:
    """Repository for vendor mapping data access operations."""

    def get_all(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all vendor mappings.

        Args:
            active_only: If True, only return active mappings

        Returns:
            List of mapping dictionaries
        """
        return get_all_vendor_mappings(active_only=active_only)

    def get_by_id(self, mapping_id: int) -> Optional[Dict[str, Any]]:
        """Get a single vendor mapping by ID.

        Args:
            mapping_id: The mapping ID

        Returns:
            Mapping dict or None if not found
        """
        return get_vendor_mapping(mapping_id)

    def create(
        self,
        pattern: str,
        supplier_name: str,
        supplier_vat: str = None,
        template_id: int = None
    ) -> int:
        """Create a new vendor mapping.

        Args:
            pattern: Regex pattern to match
            supplier_name: Supplier name to assign
            supplier_vat: Supplier VAT number
            template_id: Invoice template ID

        Returns:
            The new mapping ID
        """
        return create_vendor_mapping(
            pattern=pattern,
            supplier_name=supplier_name,
            supplier_vat=supplier_vat,
            template_id=template_id
        )

    def update(
        self,
        mapping_id: int,
        pattern: str = None,
        supplier_name: str = None,
        supplier_vat: str = None,
        template_id: int = None,
        is_active: bool = None
    ) -> bool:
        """Update a vendor mapping.

        Args:
            mapping_id: The mapping ID
            pattern: New regex pattern
            supplier_name: New supplier name
            supplier_vat: New supplier VAT
            template_id: New template ID
            is_active: Whether mapping is active

        Returns:
            True if successful
        """
        return update_vendor_mapping(
            mapping_id,
            pattern=pattern,
            supplier_name=supplier_name,
            supplier_vat=supplier_vat,
            template_id=template_id,
            is_active=is_active
        )

    def delete(self, mapping_id: int) -> bool:
        """Delete a vendor mapping.

        Args:
            mapping_id: The mapping ID

        Returns:
            True if successful
        """
        return delete_vendor_mapping(mapping_id)

    def seed_defaults(self) -> None:
        """Seed default vendor mappings if none exist."""
        seed_vendor_mappings()
