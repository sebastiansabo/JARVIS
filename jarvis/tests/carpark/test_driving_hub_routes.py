"""Registration smoke test for the CarPark -> Driving Hub push routes
(Task 3): GET .../driving-hub/status and POST .../driving-hub/push.

Mirrors test_dispo_routes.py's registration style: register carpark_bp on a
bare Flask app and inspect app.url_map for the two new rules. This task adds
only thin HTTP glue around the Task 2 service
(carpark/services/driving_hub_push_service.py, covered by
test_driving_hub_push_service.py) and the existing vehicles.py guards
(carpark_edit_required / _verify_vehicle_ownership), so a registration check
is the right level for this file — request-level behavior (ownership guard,
error-dict -> HTTP mapping) is exercised through those existing units.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from carpark import carpark_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(carpark_bp)
    app.config['TESTING'] = True
    return app


def test_driving_hub_routes_registered(app):
    # carpark/__init__.py imports carpark.routes.driving_hub as part of the
    # `from .routes import ...` line, so importing `carpark` above already
    # registered these rules on carpark_bp (and thus on `app`).
    rules = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}

    status_rules = [r for r in rules if r.endswith('/driving-hub/status')]
    push_rules = [r for r in rules if r.endswith('/driving-hub/push')]

    assert status_rules, f'no .../driving-hub/status rule registered; got {sorted(rules)}'
    assert push_rules, f'no .../driving-hub/push rule registered; got {sorted(rules)}'

    assert 'GET' in rules[status_rules[0]]
    assert 'POST' in rules[push_rules[0]]


def test_driving_hub_module_defines_view_functions():
    import carpark.routes.driving_hub as driving_hub_mod

    assert callable(getattr(driving_hub_mod, 'driving_hub_status', None))
    assert callable(getattr(driving_hub_mod, 'push_to_driving_hub', None))
