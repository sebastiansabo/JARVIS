"""Identity module — unified employee mapping across HR connectors.

Provides a single admin surface that orchestrates Sincron HR and BioStar/Pontaje
employee mappings (both pointing to users.id). Exposes a per-user unified view,
a 5-step auto-map pipeline, and consistent manual-mapping endpoints.

Strictly additive: does not modify sincron_employees or biostar_employees
schemas, and does not replace the existing per-connector routes.
"""

from flask import Blueprint

identity_bp = Blueprint(
    'identity',
    __name__,
    url_prefix='/identity',
)

from . import routes  # noqa: F401, E402

__all__ = ['identity_bp']
