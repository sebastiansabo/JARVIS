"""CRM routes package — imports all sub-modules to register routes on crm_bp."""
from .. import crm_bp   # noqa: F401 — re-exported for import-integrity tests
from . import imports    # noqa: F401
from . import clients    # noqa: F401
from . import deals      # noqa: F401
from . import lookup     # noqa: F401
