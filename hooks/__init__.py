"""
JARVIS Development Hooks Package

Automated validation hooks for financial code quality assurance.
These hooks run automatically after code generation to validate:
- Testing (80%+ coverage for accounting)
- Architecture (layer isolation)
- Modularity (duplicate entity detection)
- Performance (N+1 queries, batching)
- Cache (TTL validation)
- Database (ACID compliance, connection pool)
- Resources (memory, unbounded loops)
- Financial Safety (audit trails, immutability, idempotency)
"""

from .master_hook import MasterHook, run_all_hooks
from .testing_hook import TestingHook
from .architecture_hook import ArchitectureHook
from .modularity_hook import ModularityHook
from .performance_hook import PerformanceHook
from .cache_hook import CacheHook
from .database_hook import DatabaseHook
from .resources_hook import ResourcesHook

__all__ = [
    'MasterHook',
    'run_all_hooks',
    'TestingHook',
    'ArchitectureHook',
    'ModularityHook',
    'PerformanceHook',
    'CacheHook',
    'DatabaseHook',
    'ResourcesHook',
]

__version__ = '1.0.0'
