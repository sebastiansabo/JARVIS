"""Sincron connector repositories.

Re-export the repository classes so callers can import them from the package
(`from core.connectors.sincron.repositories import SincronRepository`), mirroring
every other repositories/ package in the codebase. An empty __init__ here made
that import raise ImportError, which surfaced as an HTTP 500 on
GET /profile/api/contracts.
"""
from .sincron_repository import SincronRepository

__all__ = ['SincronRepository']
