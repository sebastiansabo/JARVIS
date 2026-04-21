"""HR Courses route package — imports all sub-modules to register routes on courses_bp."""
from .. import courses_bp   # noqa: F401 — re-exported
from . import courses       # noqa: F401
from . import course_types  # noqa: F401
from . import enrollments   # noqa: F401
from . import certifications  # noqa: F401
from . import invoices      # noqa: F401
from . import enrollment_costs  # noqa: F401
