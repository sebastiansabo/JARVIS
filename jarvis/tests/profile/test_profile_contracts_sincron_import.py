"""Regression for the GET /profile/api/contracts 500.

The handler does `from core.connectors.sincron.repositories import SincronRepository`
(package-level, matching every other repositories/__init__ in the codebase).
That package's __init__ was empty (0 bytes) and never re-exported the class, so
the import raised `ImportError: cannot import name 'SincronRepository'`, swallowed
into a generic HTTP 500 for EVERY user opening the Edit-Profile → Contracts view.

Must run in a WARM context: a cold import of anything under core.connectors
trips a pre-existing init_db-on-import circular-import trap (core.connectors
eagerly imports blueprints), which masks the real error. So this shells out to a
subprocess that boots the app first (production-equivalent import order), then
performs the handler's exact package-level import. Skips when the local DB the
app boot needs isn't reachable.
"""
import os
import subprocess
import sys

import pytest

_JARVIS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def test_profile_contracts_sincron_package_export():
    code = (
        'import app\n'  # warm the full app so imports resolve in production order
        'from core.connectors.sincron.repositories import SincronRepository\n'
        "assert SincronRepository.__name__ == 'SincronRepository'\n"
        "print('EXPORT_OK')\n"
    )
    env = dict(os.environ)
    env.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
    proc = subprocess.run(
        [sys.executable, '-c', code],
        cwd=_JARVIS_ROOT, env=env, capture_output=True, text=True,
    )
    stderr = proc.stderr.lower()
    if 'could not connect' in stderr or 'connection refused' in stderr or 'does not exist' in stderr:
        pytest.skip('local DB needed for warm app-boot import test is not reachable')
    assert proc.returncode == 0 and 'EXPORT_OK' in proc.stdout, (
        'package-level import of SincronRepository failed (empty repositories '
        f'__init__ regressed?):\n{proc.stderr[-600:]}'
    )
