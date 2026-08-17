"""Enable real database access for accounting schema tests."""
import sys
import os

# Restore real psycopg2 if it was mocked by root conftest
# The root conftest mocks psycopg2, but schema tests need real DB access
if 'psycopg2' in sys.modules and hasattr(sys.modules['psycopg2'], '_mock_name'):
    # It's a mock, need to remove it and reimport the real one
    for key in list(sys.modules.keys()):
        if key.startswith('psycopg2'):
            del sys.modules[key]
    # Force reimport of real psycopg2
    import psycopg2  # noqa
    import psycopg2.pool  # noqa
    import psycopg2.extras  # noqa
    import psycopg2.errors  # noqa

# Reload database module to use real psycopg2
if 'database' in sys.modules:
    del sys.modules['database']
