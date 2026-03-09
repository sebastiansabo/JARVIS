#!/usr/bin/env python3
"""Re-sync BioStar events for a given date range.

Fixes the event ID collision bug where BioStar recycled event IDs
on ~March 1 2026, causing ON CONFLICT to silently drop new events
whose IDs matched old ones.

Prerequisites:
  - Migration 002_fix_event_dedup_key.sql must be applied first
    (changes unique index from biostar_event_id to composite
     biostar_event_id + event_datetime::date)

Usage:
  cd jarvis
  DATABASE_URL="postgresql://..." python3 ../scripts/resync_biostar_events.py [--days 90]
"""
import os
import sys
import argparse
from datetime import datetime, timedelta, timezone

# Add jarvis to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

UTC = timezone.utc


def main():
    parser = argparse.ArgumentParser(description='Re-sync BioStar events')
    parser.add_argument('--days', type=int, default=90, help='Days back to re-sync (default: 90)')
    parser.add_argument('--start', type=str, help='Explicit start date (YYYY-MM-DD), overrides --days')
    parser.add_argument('--end', type=str, help='Explicit end date (YYYY-MM-DD), default: now')
    parser.add_argument('--dry-run', action='store_true', help='Only count, do not insert')
    args = parser.parse_args()

    if not os.environ.get('DATABASE_URL'):
        print('ERROR: DATABASE_URL environment variable required')
        sys.exit(1)

    from core.connectors.biostar.services.biostar_sync_service import BioStarSyncService

    svc = BioStarSyncService()

    # Determine date range
    if args.start:
        start_dt = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=UTC)
    else:
        start_dt = datetime.now(UTC) - timedelta(days=args.days)

    if args.end:
        end_dt = datetime.strptime(args.end, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=UTC)
    else:
        end_dt = datetime.now(UTC)

    start_str = start_dt.strftime('%Y-%m-%dT00:00:00.00Z')
    end_str = end_dt.strftime('%Y-%m-%dT%H:%M:%S.00Z')

    print(f'Re-syncing BioStar events:')
    print(f'  Range: {start_str} → {end_str}')
    print(f'  Days:  {(end_dt - start_dt).days}')
    print()

    if args.dry_run:
        # Just count what BioStar API has
        from core.connectors.biostar.client.biostar_client import BioStarClient
        from core.connectors.biostar.config import EVENTS_PAGE_SIZE
        import json

        # Get connection details
        from core.connectors.repositories.connector_repository import ConnectorRepository
        connector = ConnectorRepository().get_by_type('biostar')
        if not connector:
            print('ERROR: No BioStar connector configured')
            sys.exit(1)
        cfg = connector.get('config') or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        creds = connector.get('credentials') or {}
        if isinstance(creds, str):
            creds = json.loads(creds)

        client = BioStarClient(
            host=cfg['host'], port=cfg['port'],
            login_id=creds['login_id'], password=creds['password'],
            verify_ssl=cfg.get('verify_ssl', False),
        )
        client.login()

        total = 0
        offset = 0
        while True:
            result = client.search_events(start_str, end_str, offset=offset, limit=EVENTS_PAGE_SIZE)
            rows = result.get('EventCollection', {}).get('rows', [])
            total += len(rows)
            if len(rows) < EVENTS_PAGE_SIZE:
                break
            offset += EVENTS_PAGE_SIZE

        print(f'[DRY RUN] BioStar API has {total} raw events in range')
        client.close()
        return

    # Actual sync
    result = svc.sync_events(start_date=start_str, end_date=end_str)

    if result.get('success'):
        data = result.get('data', {})
        print(f'  Fetched:  {data.get("fetched", 0)}')
        print(f'  Inserted: {data.get("inserted", 0)} (newly recovered)')
        print(f'  Skipped:  {data.get("skipped", 0)} (already in DB)')
        print()
        print('Done.')
    else:
        print(f'ERROR: {result.get("error", "Unknown error")}')
        sys.exit(1)


if __name__ == '__main__':
    main()
