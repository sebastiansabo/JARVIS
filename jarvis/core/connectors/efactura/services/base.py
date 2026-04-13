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
