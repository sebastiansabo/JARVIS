"""
e-Factura Routes package.

Each sub-module registers routes directly on efactura_bp.
Import order matters: sub-modules must be imported to register their routes.
"""
from . import ui          # noqa: F401
from . import connections  # noqa: F401
from . import invoices     # noqa: F401
from . import sync         # noqa: F401
from . import unallocated  # noqa: F401
from . import duplicates   # noqa: F401
from . import visibility   # noqa: F401
from . import pdf          # noqa: F401
from . import oauth        # noqa: F401
from . import mappings     # noqa: F401
