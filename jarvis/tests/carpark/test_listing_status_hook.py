"""The shared best-effort hook both connector routes call after a publish/
unpublish/delete/verify. It must delegate to VehicleService.sync_listing_status
AND swallow any error — a status-sync hiccup must never turn an already-
successful marketplace publish into a reported failure.
"""
from unittest.mock import patch

from carpark.connectors.listing_status_hook import sync_listing_status


def test_hook_delegates_with_args():
    with patch('carpark.connectors.listing_status_hook.VehicleService') as VS:
        sync_listing_status(7, changed_by=3)
        VS.return_value.sync_listing_status.assert_called_once_with(7, changed_by=3)


def test_hook_swallows_errors():
    with patch('carpark.connectors.listing_status_hook.VehicleService') as VS:
        VS.return_value.sync_listing_status.side_effect = RuntimeError('db down')
        sync_listing_status(7, changed_by=3)  # must not raise
