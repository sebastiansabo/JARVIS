"""HR Events route package — imports all sub-modules to register routes on events_bp."""
from .. import events_bp   # noqa: F401 — re-exported for import-integrity tests
from . import bonuses      # noqa: F401
from . import events       # noqa: F401
from . import employees    # noqa: F401
from . import summary      # noqa: F401
from . import organization # noqa: F401
from . import master_data  # noqa: F401
from . import bonus_types  # noqa: F401
from . import export       # noqa: F401
from . import organigram   # noqa: F401
