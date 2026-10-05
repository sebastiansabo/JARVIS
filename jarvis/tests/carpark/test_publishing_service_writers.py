"""PublishingService must write last_sync/published_at as datetime objects, not
ISO strings — writing isoformat() strings into the listing timestamp columns is
what let GET /shopify/api/vehicles/<id>/status read back a str and 500 in
listing_freshness (see the _aware hotfix)."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime

from carpark.services.publishing_service import PublishingService


def test_sync_listing_stats_writes_datetime_last_sync(monkeypatch):
    svc = PublishingService()
    captured = {}
    monkeypatch.setattr(svc._pub_repo, 'get_listing',
                        lambda lid: {'id': lid, 'external_listing_id': 'gid://1',
                                     'platform_id': 3, 'vehicle_id': 7,
                                     'views': 0, 'inquiries': 0})
    monkeypatch.setattr(svc._pub_repo, 'get_platform',
                        lambda pid: {'id': pid, 'platform_type': 'x'})

    class FakeConn:
        def get_stats(self, ext):
            return {'views': 5, 'inquiries': 1}

    monkeypatch.setattr(svc, '_get_connector', lambda platform: FakeConn())
    monkeypatch.setattr(svc._pub_repo, 'update_listing',
                        lambda lid, data: captured.update(data) or {'id': lid, **data})
    monkeypatch.setattr(svc._pub_repo, 'log_sync', lambda *a, **k: None)

    svc.sync_listing_stats(1)

    assert isinstance(captured['last_sync'], datetime)  # not an ISO string
