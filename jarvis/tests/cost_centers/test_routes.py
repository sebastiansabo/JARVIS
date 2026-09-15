"""Route smoke test for the cost-centers blueprint (Task 5).

Uses the real Flask app (`app.py`) so blueprint registration and the
`_accounting_required` decorator are exercised end-to-end, mirroring the
convention in `tests/carpark/test_acting_company.py` /
`tests/carpark/test_photo_upload.py`: import the module-level `app`
instance created at `app.py` import time (`app = create_app()`) rather
than calling `create_app()` again.

Gated on `REAL_DB_AVAILABLE` (see tests/cost_centers/conftest.py) like the
sibling Batch A/B tests in this package, since CI has no real DB.
"""
import pytest
from tests.cost_centers.conftest import REAL_DB_AVAILABLE

pytestmark = pytest.mark.skipif(not REAL_DB_AVAILABLE, reason='no real DB available (CI)')


@pytest.fixture
def client():
    from app import app as flask_app  # module-level Flask instance (app.py: app = create_app())
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def test_cost_centers_requires_auth(client):
    r = client.get('/api/cost-centers/companies')
    assert r.status_code == 401
    assert r.get_json()['success'] is False
