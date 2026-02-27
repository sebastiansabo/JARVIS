"""BioStar 2 Connector Module — Access control and time & attendance integration."""

from flask import Blueprint

biostar_bp = Blueprint(
    'biostar',
    __name__,
    url_prefix='/biostar',
)

from . import routes  # noqa: F401, E402

__all__ = ['biostar_bp']
