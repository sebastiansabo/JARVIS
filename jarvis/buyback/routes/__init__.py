"""Buyback route submodules — imported for their side effect of registering
@buyback_bp.route decorators onto the shared blueprint (buyback/__init__.py).
"""
from . import records  # noqa: F401
