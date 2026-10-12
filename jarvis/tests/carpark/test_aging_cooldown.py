"""Regression: the CarPark aging-stock alert must honor a 7-day per-vehicle
cooldown so a long-unsold car nudges ~weekly instead of every daily run.

Before the fix, `carpark_aging_alerts` re-notified every aged vehicle on every
daily run. The fix gates each vehicle on `smart_notification_state`
(alert_type='carpark_aging') with a 7-day window, mirroring foi_parcurs'
vehicle-expiry cooldown.

Unit-level: DispoRepository.aged_unsold and the database helpers are stubbed, so
a fake cursor drives the cooldown branch without a real database.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock, patch

import tasks.carpark as carpark_tasks


class _FakeCursor:
    """Minimal cursor: `fetchone` returns a configurable cooldown result and
    every execute is recorded so we can assert the state upsert ran."""
    def __init__(self, cooldown_hit):
        self._cooldown_hit = cooldown_hit
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        # The cooldown SELECT is the only fetchone the job issues per vehicle.
        return {'x': 1} if self._cooldown_hit else None


def _run_with(cooldown_hit):
    vehicle = {'id': 501, 'vin': 'VINAGED1', 'brand': 'VW', 'model': 'Golf',
               'days_in_stock': 95, 'salesperson_user_id': 7}
    cursor = _FakeCursor(cooldown_hit)
    notify = MagicMock()

    with patch.object(carpark_tasks, 'logger'), \
         patch('carpark.repositories.dispo_repository.DispoRepository') as Repo, \
         patch('database.get_db', return_value=MagicMock()), \
         patch('database.get_cursor', return_value=cursor), \
         patch('database.release_db'), \
         patch('core.notifications.notify.notify_user', notify):
        Repo.return_value.aged_unsold.return_value = [vehicle]
        carpark_tasks.carpark_aging_alerts()
    return notify, cursor


def test_vehicle_within_cooldown_is_not_renotified():
    notify, cursor = _run_with(cooldown_hit=True)
    notify.assert_not_called()
    # only the cooldown SELECT ran — no INSERT/upsert of state
    assert all('INSERT' not in sql.upper() for sql, _ in cursor.executed)


def test_vehicle_past_cooldown_is_notified_and_recorded():
    notify, cursor = _run_with(cooldown_hit=False)
    notify.assert_called_once()
    # the alert carries the carpark category (so it is mutable in push-manager)
    assert notify.call_args.kwargs.get('category') == 'carpark'
    # and the 7-day state is upserted so the next daily run is suppressed
    assert any('INSERT INTO smart_notification_state' in sql for sql, _ in cursor.executed)
