"""
Shared base types for e-Factura services.
"""
import os
from dataclasses import dataclass
from typing import Any, Optional

from core.utils.logging_config import get_logger

MOCK_MODE = os.environ.get('EFACTURA_MOCK_MODE', 'true').lower() == 'true'


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None


def _iso(v) -> Optional[str]:
    """Safely convert datetime or already-ISO-string to ISO string.

    dict_from_row() pre-converts datetimes to ISO strings, so model
    attributes may be strings rather than datetime objects.  Calling
    .isoformat() on a string raises AttributeError, so we guard with
    hasattr before calling.
    """
    if v is None:
        return None
    return v.isoformat() if hasattr(v, 'isoformat') else v
