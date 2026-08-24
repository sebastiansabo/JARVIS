"""Foi de Parcurs routes — imports all sub-modules to register routes."""
from .. import foi_parcurs_bp  # noqa: F401 — re-exported for import-integrity
from . import contracts         # noqa: F401
from . import contract_configs  # noqa: F401
from . import clients           # noqa: F401
from . import vehicles          # noqa: F401
from . import settings          # noqa: F401
from . import inspections       # noqa: F401
from . import test_drive        # noqa: F401
from . import pdf               # noqa: F401
from . import export            # noqa: F401
from . import route_sheet       # noqa: F401
from . import session_import    # noqa: F401
