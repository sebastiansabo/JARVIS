"""Base Connector — Abstract interface for marketplace publishing.

All platform connectors must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseConnector(ABC):
    """Abstract base class for marketplace connectors."""

    @abstractmethod
    def publish(self, vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
        """Publish a vehicle listing to the platform.

        Returns: { external_id, external_url, success, error? }
        """
        ...

    @abstractmethod
    def update(self, external_id: str, vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing listing.

        Returns: { success, error? }
        """
        ...

    @abstractmethod
    def deactivate(self, external_id: str) -> Dict[str, Any]:
        """Deactivate a listing (make it invisible but not deleted).

        Returns: { success, error? }
        """
        ...

    @abstractmethod
    def delete(self, external_id: str) -> Dict[str, Any]:
        """Permanently delete a listing from the platform.

        Returns: { success, error? }
        """
        ...

    @abstractmethod
    def get_stats(self, external_id: str) -> Dict[str, Any]:
        """Fetch listing statistics (views, inquiries).

        Returns: { views, inquiries, status? }
        """
        ...

    def health_check(self) -> bool:
        """Check if the platform API is reachable."""
        return True
