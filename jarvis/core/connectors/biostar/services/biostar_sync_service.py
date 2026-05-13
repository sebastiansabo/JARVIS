"""BioStar 2 sync service — orchestrates user and event synchronization."""

import json
import logging
import random
from datetime import datetime, timedelta

logger = logging.getLogger('jarvis.biostar.sync')

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# BioStar API returns datetimes in UTC; convert to Romania local time
_ROMANIA_TZ = ZoneInfo('Europe/Bucharest')
_UTC = ZoneInfo('UTC')


def _utc_to_local(dt_str):
    """Convert a BioStar UTC datetime string to Romania local time string.

    BioStar API returns '2026-03-02T05:11:23.00Z' (UTC).
    Returns '2026-03-02T07:11:23' (Europe/Bucharest, handles DST).
    """
    if not dt_str:
        return dt_str
    # Strip .00Z suffix and parse
    clean = dt_str.replace('.00Z', '').replace('Z', '')
    try:
        dt = datetime.fromisoformat(clean).replace(tzinfo=_UTC)
        local_dt = dt.astimezone(_ROMANIA_TZ)
        return local_dt.strftime('%Y-%m-%dT%H:%M:%S')
    except (ValueError, TypeError):
        return dt_str  # Return as-is if unparseable


from core.connectors.repositories.connector_repository import ConnectorRepository
from ..client.biostar_client import BioStarClient
from ..repositories.biostar_repository import BioStarRepository
from ..repositories.sync_repo import BioStarSyncRepository
from ..repositories.adjustment_repository import AdjustmentRepository
from ..config import USERS_PAGE_SIZE, EVENTS_PAGE_SIZE, SYNC_EVENTS_DEFAULT_DAYS


class BioStarSyncService:
    """Unified service for BioStar connector operations."""

    def __init__(self):
        self.repo = BioStarRepository()
        self.sync_repo = BioStarSyncRepository()
        self.connector_repo = ConnectorRepository()
        self.adj_repo = AdjustmentRepository()
        self._device_directions = None  # Cache for sync runs
        # Lazy-init; avoids circular import at module level
        self._company_repo = None

    # ── Connection Management ──

    def get_connection_config(self):
        """Get BioStar connector config (masked password)."""
        connector = self.connector_repo.get_by_type('biostar')
        if not connector:
            return None
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)
        creds = connector.get('credentials') or {}
        if isinstance(creds, str):
            creds = json.loads(creds)
        return {
            'id': connector['id'],
            'host': config.get('host', ''),
            'port': config.get('port', 443),
            'login_id': creds.get('login_id', ''),
            'verify_ssl': config.get('verify_ssl', False),
            'status': connector.get('status', 'disconnected'),
            'last_sync': connector.get('last_sync'),
        }

    def save_connection(self, host, port, login_id, password, verify_ssl=False):
        """Save or update BioStar connection config."""
        config = {'host': host, 'port': port, 'verify_ssl': verify_ssl}
        credentials = {'login_id': login_id, 'password': password}

        existing = self.connector_repo.get_by_type('biostar')
        if existing:
            self.connector_repo.update(
                existing['id'],
                config=config,
                credentials=credentials,
                status='disconnected'
            )
            return existing['id']
        else:
            return self.connector_repo.save(
                connector_type='biostar',
                name='BioStar 2',
                status='disconnected',
                config=config,
                credentials=credentials
            )

    def test_connection(self, host=None, port=None, login_id=None, password=None):
        """Test BioStar API connectivity. Uses stored creds if args not provided."""
        if host and login_id and password:
            client = BioStarClient(host, port or 443, login_id, password)
        else:
            client = self._get_client()

        try:
            result = client.test_connection()
            # Update connector status on success
            existing = self.connector_repo.get_by_type('biostar')
            if existing:
                self.connector_repo.update(existing['id'], status='connected')
            return {'success': True, 'data': result}
        except Exception as e:
            existing = self.connector_repo.get_by_type('biostar')
            if existing:
                self.connector_repo.update(existing['id'], status='error', last_error=str(e))
            return {'success': False, 'error': str(e)}
        finally:
            client.close()

    def _get_client(self):
        """Create client from stored connection config."""
        connector = self.connector_repo.get_by_type('biostar')
        if not connector:
            raise ValueError('BioStar connector not configured')
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)
        creds = connector.get('credentials') or {}
        if isinstance(creds, str):
            creds = json.loads(creds)
        return BioStarClient(
            host=config['host'],
            port=config.get('port', 443),
            login_id=creds['login_id'],
            password=creds['password'],
            verify_ssl=config.get('verify_ssl', False),
        )

    def _get_connector_id(self):
        """Get or create the biostar connector row ID."""
        existing = self.connector_repo.get_by_type('biostar')
        return existing['id'] if existing else None

    # ── User Sync ──

    def sync_users(self):
        """Full sync: fetch all BioStar users, upsert, auto-map to JARVIS users."""
        run = self.sync_repo.create_run('users')
        run_id = run['run_id']

        try:
            client = self._get_client()

            # 1. Fetch all users with pagination
            all_users = []
            offset = 0
            while True:
                result = client.get_users(offset=offset, limit=USERS_PAGE_SIZE)
                rows = result.get('UserCollection', {}).get('rows', [])
                all_users.extend(rows)
                if len(rows) < USERS_PAGE_SIZE:
                    break
                offset += USERS_PAGE_SIZE

            records_fetched = len(all_users)

            # 2. Transform to our schema (load group map once for the whole batch)
            self._sync_group_map = self.get_group_company_map()
            employees = [self._transform_user(u) for u in all_users]

            # 3. Bulk upsert
            upsert_result = self.repo.bulk_upsert_employees(employees)

            # 4. Auto-map unmapped employees
            mapping_result = self._auto_map_employees()

            # 5. Update connector status
            connector_id = self._get_connector_id()
            if connector_id:
                self.connector_repo.update(
                    connector_id, status='connected',
                    last_sync=datetime.now()
                )

            self.sync_repo.complete_run(
                run_id, success=True,
                records_fetched=records_fetched,
                records_created=upsert_result['created'],
                records_updated=upsert_result['updated'],
            )

            client.close()
            return {
                'success': True,
                'data': {
                    'fetched': records_fetched,
                    'created': upsert_result['created'],
                    'updated': upsert_result['updated'],
                    'mapped': mapping_result.get('newly_mapped', 0),
                    'unmapped': mapping_result.get('still_unmapped', 0),
                }
            }
        except Exception as e:
            self.sync_repo.complete_run(run_id, success=False, error_summary=str(e))
            self.sync_repo.record_error(run_id, 'SYNC', str(e))
            return {'success': False, 'error': str(e)}

    # Hardcoded fallback — only used if company_aliases table is empty
    _FALLBACK_GROUP_MAP = {
        'AW HOLDING': 16, 'ADMINISTRATIV': 16,
        'AW ONE': 15, 'AW NEXT': 13, 'AW INTERNATIONAL': 10,
        'AW PREMIUM': 11, 'AW PLUS': 9, 'AW PRESTIGE': 12,
        'AW INSURANCE': 14,
    }

    @property
    def company_repo(self):
        if self._company_repo is None:
            from core.organization.repositories.company_repository import CompanyRepository
            self._company_repo = CompanyRepository()
        return self._company_repo

    def get_group_company_map(self):
        """Return group→company_id map from company_aliases table."""
        mapping = self.company_repo.get_group_company_map()
        return mapping if mapping else dict(self._FALLBACK_GROUP_MAP)

    def save_group_company_map(self, mapping):
        """Persist group→company_id map into company_aliases table."""
        for alias, company_id in mapping.items():
            if company_id:
                self.company_repo.add_alias(int(company_id), alias, 'biostar')

    def _transform_user(self, raw):
        """Transform BioStar API user to our employee dict."""
        # API returns user nested or flat depending on endpoint
        user = raw.get('User', raw)
        group = user.get('user_group_id', {})
        if isinstance(group, dict):
            group_id = str(group.get('id', ''))
            group_name = group.get('name', '')
        else:
            group_id = str(group) if group else ''
            group_name = ''

        cards = user.get('cards', [])
        card_ids = [c.get('card_id', '') for c in cards if isinstance(c, dict)]

        disabled = user.get('disabled', 'false')
        status = 'inactive' if str(disabled).lower() == 'true' else 'active'

        return {
            'biostar_user_id': str(user.get('user_id', '')),
            'name': user.get('name', ''),
            'email': user.get('email', ''),
            'phone': user.get('phone_number', ''),
            'user_group_id': group_id,
            'user_group_name': group_name,
            'company_id': self._sync_group_map.get(group_name),
            'card_ids': card_ids,
            'status': status,
        }

    def _auto_map_employees(self):
        """Match BioStar employees to JARVIS users using the shared SQL pipeline.

        Delegates to BioStarRepository helpers so the logic stays identical with
        the unified /identity/api/auto-map endpoint:
            1. CNP  (no-op — CNP is canonical in users table, matched via Sincron)
            2. email (confidence 100)
            3. name  (confidence 90)
        Cross-verification via Sincron runs as part of the unified pipeline and
        is intentionally NOT invoked here to keep the sync step self-contained.
        """
        before = self.repo.get_unmapped_employees()
        total_unmapped = len(before)

        cnp_mapped = self.repo.auto_map_by_cnp() or 0
        email_mapped = self.repo.auto_map_by_email() or 0
        name_mapped = self.repo.auto_map_by_name() or 0

        newly_mapped = (cnp_mapped or 0) + (email_mapped or 0) + (name_mapped or 0)
        return {
            'newly_mapped': newly_mapped,
            'still_unmapped': max(total_unmapped - newly_mapped, 0),
            'by_method': {
                'cnp': cnp_mapped or 0,
                'email': email_mapped or 0,
                'name': name_mapped or 0,
            },
        }

    # ── Event Sync ──

    def sync_events(self, start_date=None, end_date=None):
        """Incremental sync: fetch events since last sync or given date range."""
        # Refresh device direction cache for this sync run
        self._device_directions = None
        run = self.sync_repo.create_run('events')
        run_id = run['run_id']

        try:
            client = self._get_client()

            # Determine start date — BioStar API expects UTC with .00Z suffix
            # For scheduled (no start_date): use last successful sync's finished_at
            if not start_date:
                last_run = self.sync_repo.get_last_successful_run('events')
                if last_run and last_run.get('finished_at'):
                    # finished_at is server-local time (Romania) — convert to UTC
                    finished = last_run['finished_at']
                    if isinstance(finished, datetime):
                        local_dt = finished.replace(tzinfo=_ROMANIA_TZ)
                    else:
                        local_dt = datetime.fromisoformat(str(finished).split('.')[0]).replace(tzinfo=_ROMANIA_TZ)
                    utc_dt = local_dt.astimezone(_UTC)
                    start_date = utc_dt.strftime('%Y-%m-%dT%H:%M:%S.00Z')
                else:
                    start_date = (datetime.now(_UTC) - timedelta(days=SYNC_EVENTS_DEFAULT_DAYS)).strftime('%Y-%m-%dT00:00:00.00Z')

            if not end_date:
                end_date = datetime.now(_UTC).strftime('%Y-%m-%dT%H:%M:%S.00Z')

            logger.info(f"Event sync query: start={start_date}, end={end_date}")

            # Fetch events with pagination
            all_events = []
            offset = 0
            while True:
                result = client.search_events(start_date, end_date, offset=offset, limit=EVENTS_PAGE_SIZE)
                rows = result.get('EventCollection', {}).get('rows', [])
                all_events.extend(rows)
                logger.info(f"Event sync page offset={offset}: got {len(rows)} rows (total so far: {len(all_events)})")
                if len(rows) < EVENTS_PAGE_SIZE:
                    break
                offset += EVENTS_PAGE_SIZE

            records_fetched = len(all_events)

            # Transform and insert (filter out None — events without user)
            logs = [l for l in (self._transform_event(e) for e in all_events) if l]
            insert_result = self.repo.insert_punch_logs(logs) if logs else {'inserted': 0, 'skipped': 0}

            # Update connector
            connector_id = self._get_connector_id()
            if connector_id:
                self.connector_repo.update(
                    connector_id, status='connected',
                    last_sync=datetime.now()
                )

            # Parse UTC strings to datetimes for cursor storage
            cursor_before_dt = None
            cursor_after_dt = None
            try:
                cursor_before_dt = datetime.strptime(start_date.replace('.00Z', 'Z'), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=_UTC)
            except (ValueError, AttributeError):
                pass
            try:
                cursor_after_dt = datetime.strptime(end_date.replace('.00Z', 'Z'), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=_UTC)
            except (ValueError, AttributeError):
                pass

            self.sync_repo.complete_run(
                run_id, success=True,
                records_fetched=records_fetched,
                records_created=insert_result['inserted'],
                records_skipped=insert_result['skipped'],
                cursor_before=cursor_before_dt,
                cursor_after=cursor_after_dt,
            )

            client.close()
            return {
                'success': True,
                'data': {
                    'fetched': records_fetched,
                    'inserted': insert_result['inserted'],
                    'skipped': insert_result['skipped'],
                    'date_range': {'start': start_date, 'end': end_date},
                }
            }
        except Exception as e:
            self.sync_repo.complete_run(run_id, success=False, error_summary=str(e))
            self.sync_repo.record_error(run_id, 'SYNC', str(e))
            return {'success': False, 'error': str(e)}

    def _transform_event(self, raw):
        """Transform BioStar event to punch log dict.

        Handles API quirks:
        - user_id can be sparse (only {photo_exists:false} without user_id field)
        - door_id is a list of dicts, not a single dict
        - device_id is a dict with id/name
        - event_type_id is a dict with code/id
        """
        # User — may be missing user_id field entirely (non-auth events)
        user_id_data = raw.get('user_id', {})
        if isinstance(user_id_data, dict):
            user_id = str(user_id_data.get('user_id', ''))
        else:
            user_id = str(user_id_data) if user_id_data else ''

        # Skip events with no user — system events (door forced, etc.)
        if not user_id:
            return None

        # Skip unrecognized card swipes — user_id_name ends with "(-)"
        user_id_name = raw.get('user_id_name', '')
        if user_id_name.endswith('(-)'):
            return None

        # Device — dict with id/name
        device = raw.get('device_id', {})
        if isinstance(device, dict):
            device_id = str(device.get('id', ''))
            device_name = device.get('name', '')
        else:
            device_id = str(device) if device else ''
            device_name = ''

        # Door — LIST of dicts, take first element
        door_raw = raw.get('door_id')
        door_id = None
        door_name = ''
        if isinstance(door_raw, list) and door_raw:
            first_door = door_raw[0]
            if isinstance(first_door, dict):
                door_id = str(first_door.get('id', ''))
                door_name = first_door.get('name', '')
        elif isinstance(door_raw, dict):
            door_id = str(door_raw.get('id', ''))
            door_name = door_raw.get('name', '')

        # Event type — dict with code
        event_type_data = raw.get('event_type_id', {})
        if isinstance(event_type_data, dict):
            event_type = str(event_type_data.get('code', event_type_data.get('id', '')))
        else:
            event_type = str(event_type_data)

        return {
            'biostar_event_id': str(raw.get('id', '')),
            'biostar_user_id': user_id,
            'event_datetime': _utc_to_local(raw.get('datetime', '')),
            'event_type': event_type,
            'direction': self._infer_direction(raw),
            'device_id': device_id,
            'device_name': device_name,
            'door_id': door_id,
            'door_name': door_name,
            'auth_type': raw.get('auth_type', ''),
            'raw_data': raw,
        }

    def _load_device_directions(self):
        """Load device→direction mapping from connector config. Cached per service instance."""
        if self._device_directions is not None:
            return self._device_directions
        self._device_directions = {}
        try:
            connector = self.connector_repo.get_by_type('biostar')
            if connector:
                config = connector.get('config') or {}
                if isinstance(config, str):
                    config = json.loads(config)
                self._device_directions = config.get('device_directions', {})
        except Exception:
            pass
        return self._device_directions

    def _infer_direction(self, event):
        """Infer IN/OUT from: 1) device mapping, 2) tna_key, 3) device name patterns."""
        # 1. Check configured device→direction mapping (most reliable)
        device = event.get('device_id', {})
        device_name = ''
        if isinstance(device, dict):
            device_name = device.get('name', '') or ''

        directions = self._load_device_directions()
        if device_name and device_name in directions:
            return directions[device_name]

        # 2. Check tna_key (BioStar T&A module — often not available)
        tna_key = event.get('tna_key')
        if tna_key == 1 or tna_key == '1':
            return 'IN'
        if tna_key == 2 or tna_key == '2':
            return 'OUT'

        # 3. Fallback: check device/door name patterns
        names_to_check = [device_name.lower()]

        door_raw = event.get('door_id')
        if isinstance(door_raw, list):
            for d in door_raw:
                if isinstance(d, dict):
                    names_to_check.append((d.get('name', '') or '').lower())
        elif isinstance(door_raw, dict):
            names_to_check.append((door_raw.get('name', '') or '').lower())

        for name in names_to_check:
            if any(kw in name for kw in ('intrare', 'entry', 'reader extern')):
                return 'IN'
            if any(kw in name for kw in ('iesire', 'exit')):
                return 'OUT'

        return None

    # ── Device Directions ──

    def get_device_directions(self):
        """Get device→direction mapping from connector config."""
        connector = self.connector_repo.get_by_type('biostar')
        if not connector:
            return {}
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)
        return config.get('device_directions', {})

    def save_device_directions(self, directions):
        """Save device→direction mapping to connector config."""
        connector = self.connector_repo.get_by_type('biostar')
        if not connector:
            raise ValueError('BioStar connector not configured')
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)
        config['device_directions'] = directions
        self.connector_repo.update(connector['id'], config=config)
        # Invalidate cache
        self._device_directions = None

    def get_devices(self):
        """Get all unique devices from punch logs with punch counts."""
        return self.repo.get_devices()

    def backfill_directions(self, directions=None):
        """Update direction on existing punch logs based on device mapping.

        Returns count of updated records.
        """
        if directions is None:
            directions = self.get_device_directions()
        if not directions:
            return 0
        return self.repo.backfill_directions(directions)

    # ── Getters ──

    def get_employees(self, active_only=True):
        """Get synced employees."""
        return self.repo.get_all_employees(active_only)

    def get_employee_stats(self):
        """Get employee counts."""
        return self.repo.get_employee_stats()

    def get_punch_logs(self, biostar_user_id=None, start_date=None,
                       end_date=None, limit=100, offset=0):
        """Get punch logs with filters."""
        logs = self.repo.get_punch_logs(biostar_user_id, start_date, end_date, limit, offset)
        total = self.repo.get_punch_log_count(biostar_user_id, start_date, end_date)
        return {'logs': logs, 'total': total}

    def get_daily_summary(self, date_str, jarvis_user_ids=None):
        """Get per-employee daily punch summary."""
        return self.repo.get_daily_summary(date_str, jarvis_user_ids=jarvis_user_ids)

    def get_range_summary(self, start_date, end_date, jarvis_user_ids=None):
        """Get per-employee aggregated summary over a date range."""
        return self.repo.get_range_summary(start_date, end_date, jarvis_user_ids=jarvis_user_ids)

    def get_attendance_overview(self, date_str, jarvis_user_ids=None):
        """Get attendance overview with stable employee list for a given date."""
        return self.repo.get_attendance_overview(date_str, jarvis_user_ids=jarvis_user_ids)

    def get_attendance_week(self, end_date_str, jarvis_user_ids=None):
        """Get 7-day attendance summary with stable employee list."""
        return self.repo.get_attendance_week(end_date_str, jarvis_user_ids=jarvis_user_ids)

    def get_employee_punches(self, biostar_user_id, date_str):
        """Get all punch events for one employee on a specific date."""
        return self.repo.get_employee_punches(biostar_user_id, date_str)

    def get_employee_profile(self, biostar_user_id):
        """Get employee details with mapping info."""
        return self.repo.get_employee_with_mapping(biostar_user_id)

    def get_employee_daily_history(self, biostar_user_id, start_date, end_date):
        """Get per-day punch summaries for one employee over a date range."""
        return self.repo.get_employee_daily_history(biostar_user_id, start_date, end_date)

    def update_employee_mapping(self, biostar_user_id, jarvis_user_id):
        """Manually map a BioStar employee to a JARVIS user."""
        return self.repo.update_mapping(biostar_user_id, jarvis_user_id, 'manual', 100.0)

    def remove_employee_mapping(self, biostar_user_id):
        """Remove JARVIS user mapping."""
        return self.repo.remove_mapping(biostar_user_id)

    def update_employee_schedule(self, biostar_user_id, lunch_break_minutes, working_hours,
                                    schedule_start=None, schedule_end=None):
        """Update work schedule for an employee."""
        return self.repo.update_schedule(biostar_user_id, lunch_break_minutes, working_hours,
                                         schedule_start, schedule_end)

    def bulk_update_schedule(self, biostar_user_ids, lunch_break_minutes=None,
                             working_hours=None, schedule_start=None, schedule_end=None):
        """Bulk update schedule fields for multiple employees."""
        return self.repo.bulk_update_schedule(
            biostar_user_ids, lunch_break_minutes, working_hours,
            schedule_start, schedule_end
        )

    def bulk_deactivate(self, biostar_user_ids):
        """Deactivate (soft-delete) multiple employees."""
        return self.repo.bulk_deactivate(biostar_user_ids)

    def get_sync_history(self, sync_type=None, limit=20):
        """Get recent sync runs."""
        return self.sync_repo.get_recent_runs(sync_type, limit)

    def get_sync_errors(self, run_id):
        """Get errors for a sync run."""
        return self.sync_repo.get_run_errors(run_id)

    def get_status(self):
        """Get full connector status."""
        connector = self.connector_repo.get_by_type('biostar')
        stats = self.repo.get_employee_stats() or {}
        event_count = self.repo.get_punch_log_count()
        last_user_run = self.sync_repo.get_last_successful_run('users')
        last_event_run = self.sync_repo.get_last_successful_run('events')

        return {
            'connected': connector.get('status') == 'connected' if connector else False,
            'status': connector.get('status', 'disconnected') if connector else 'disconnected',
            'host': (json.loads(connector['config']) if isinstance(connector.get('config'), str) else connector.get('config', {})).get('host') if connector else None,
            'last_sync_users': str(last_user_run['finished_at']) if last_user_run and last_user_run.get('finished_at') else None,
            'last_sync_events': str(last_event_run['finished_at']) if last_event_run and last_event_run.get('finished_at') else None,
            'employee_count': {
                'total': stats.get('total', 0),
                'active': stats.get('active', 0),
                'mapped': stats.get('mapped', 0),
                'unmapped': stats.get('unmapped', 0),
            },
            'event_count': event_count,
        }

    # ── Schedule Adjustments ──

    def get_off_schedule_employees(self, date_str, threshold=15):
        """Get employees with punches deviating from schedule by >= threshold minutes."""
        return self.adj_repo.get_off_schedule(date_str, threshold)

    def get_adjustments(self, date_str):
        """Get all adjustments for a date."""
        return self.adj_repo.get_adjustments(date_str)

    def get_employee_adjustment_history(self, biostar_user_id, start_date=None, end_date=None):
        """Get adjustment history for one employee (audit trail)."""
        return self.adj_repo.get_employee_history(biostar_user_id, start_date, end_date)

    def adjust_employee(self, biostar_user_id, date_str, adjusted_first, adjusted_last,
                        original_first, original_last, schedule_start, schedule_end,
                        lunch_break_minutes, working_hours, original_duration,
                        deviation_in, deviation_out, adjustment_type='manual',
                        adjusted_by=None, notes=None, **kwargs):
        """Create or update a schedule adjustment for one employee/day."""
        # Calculate adjusted duration
        if adjusted_first and adjusted_last:
            delta = adjusted_last - adjusted_first
            adj_seconds = delta.total_seconds()
        else:
            adj_seconds = None

        return self.adj_repo.upsert_adjustment({
            'biostar_user_id': biostar_user_id,
            'date': date_str,
            'original_first_punch': original_first,
            'original_last_punch': original_last,
            'original_duration_seconds': original_duration,
            'adjusted_first_punch': adjusted_first,
            'adjusted_last_punch': adjusted_last,
            'adjusted_duration_seconds': adj_seconds,
            'schedule_start': schedule_start,
            'schedule_end': schedule_end,
            'lunch_break_minutes': lunch_break_minutes,
            'working_hours': working_hours,
            'deviation_minutes_in': deviation_in,
            'deviation_minutes_out': deviation_out,
            'adjustment_type': adjustment_type,
            'adjusted_by': adjusted_by,
            'notes': notes,
        })

    @staticmethod
    def _randomize_times(first_punch, schedule_start, lunch_break_minutes, working_hours):
        """Generate natural-looking adjusted check-in/out times.

        Randomizes so net worked = working_hours + 0..10 min,
        with check-in scattered ±5 min around schedule_start.
        """
        wh_min = int(working_hours * 60)
        target_worked = random.randint(wh_min, wh_min + 10)
        target_span = target_worked + int(lunch_break_minutes)

        start_offset = random.randint(-5, 5)
        if isinstance(first_punch, str):
            first_punch = datetime.fromisoformat(first_punch)
        if isinstance(schedule_start, str):
            from datetime import time as _time
            parts = schedule_start.split(':')
            schedule_start = _time(int(parts[0]), int(parts[1]))
        date_part = first_punch.date()
        adj_start = datetime.combine(date_part, schedule_start) + timedelta(minutes=start_offset)
        adj_end = adj_start + timedelta(minutes=target_span)
        return adj_start, adj_end

    def _get_sincron_leave_user_ids(self, date_str):
        """Return set of mapped_jarvis_user_ids with Sincron leave codes for the date."""
        try:
            from core.connectors.sincron.repositories.sincron_repository import SincronRepository
            sincron_repo = SincronRepository()
            LEAVE_CODES = ('CO', 'CM', 'CIC', 'CES', 'CMS', 'DLG', 'ZLS', 'CFP', 'CFS', 'INV')
            rows = sincron_repo.query_all('''
                SELECT DISTINCT se.mapped_jarvis_user_id
                FROM sincron_employees se
                JOIN sincron_timesheets st
                  ON st.sincron_employee_id = se.sincron_employee_id
                  AND st.company_name = se.company_name
                  AND st.day = %s::date
                  AND st.short_code = ANY(%s)
                WHERE se.is_active = TRUE
                  AND se.mapped_jarvis_user_id IS NOT NULL
            ''', (date_str, list(LEAVE_CODES)))
            return {r['mapped_jarvis_user_id'] for r in rows}
        except Exception as e:
            logger.warning('Failed to load Sincron leave user IDs for %s: %s', date_str, e)
            return set()

    def _get_sincron_leave_by_company(self, date_str):
        """Return {jarvis_user_id: {company_name, ...}} — which companies have leave per user."""
        try:
            from core.connectors.sincron.repositories.sincron_repository import SincronRepository
            sincron_repo = SincronRepository()
            LEAVE_CODES = ('CO', 'CM', 'CIC', 'CES', 'CMS', 'DLG', 'ZLS', 'CFP', 'CFS', 'INV')
            rows = sincron_repo.query_all('''
                SELECT se.mapped_jarvis_user_id,
                       COALESCE(co.company, se.company_name) AS company
                FROM sincron_employees se
                JOIN sincron_timesheets st
                  ON st.sincron_employee_id = se.sincron_employee_id
                  AND st.company_name = se.company_name
                  AND st.day = %s::date
                  AND st.short_code = ANY(%s)
                LEFT JOIN companies co ON co.id = se.company_id
                WHERE se.is_active = TRUE
                  AND se.mapped_jarvis_user_id IS NOT NULL
            ''', (date_str, list(LEAVE_CODES)))
            result = {}
            for r in rows:
                uid = r['mapped_jarvis_user_id']
                if uid not in result:
                    result[uid] = set()
                result[uid].add(r['company'])
            return result
        except Exception as e:
            logger.warning('Failed to load per-company Sincron leave for %s: %s', date_str, e)
            return {}

    def auto_adjust_all(self, date_str, threshold=15, user_id=None):
        """Auto-adjust off-schedule, single-punch, and absent employees.

        Skips public holidays entirely.  For multi-contract employees, generates
        per-company adjustments based on each company's Sincron schedule.
        Leave codes are checked per-company: only the company on leave is
        skipped, others are still adjusted.
        """
        # Skip public holidays
        if self._is_public_holiday(date_str):
            return {'adjusted': 0, 'total_flagged': 0, 'skipped': 'public_holiday'}

        off = self.adj_repo.get_off_schedule(date_str, threshold)
        absent = self.adj_repo.get_absent_employees(date_str)
        leave_ids = self._get_sincron_leave_user_ids(date_str)
        leave_by_company = self._get_sincron_leave_by_company(date_str)
        adjusted_count = 0

        # Batch-fetch full combined schedules (including secondary contracts)
        full_schedules = {}
        all_intervals = {}  # {jarvis_uid: [intervals]}
        try:
            from core.connectors.sincron.repositories.sincron_repository import SincronRepository
            sincron_repo = SincronRepository()
            rows = sincron_repo.get_all_full_day_schedules_for_date(date_str)
            for r in rows:
                if r.get('schedule_start') and r.get('schedule_end'):
                    full_schedules[r['mapped_jarvis_user_id']] = r
            all_intervals = sincron_repo.get_all_day_intervals(date_str)
        except Exception as e:
            logger.warning('Failed to load Sincron schedules for %s: %s', date_str, e)

        from datetime import time as _time

        def _parse_time(val):
            if isinstance(val, str):
                parts = val.split(':')
                return _time(int(parts[0]), int(parts[1]))
            return val

        def _override_schedule(row, sched_start, sched_end, lunch, wh):
            """Override schedule with full combined schedule if available."""
            jarvis_uid = row.get('mapped_jarvis_user_id')
            if jarvis_uid and jarvis_uid in full_schedules:
                fs = full_schedules[jarvis_uid]
                fs_start = _parse_time(str(fs['schedule_start'])[:5])
                fs_end = _parse_time(str(fs['schedule_end'])[:5])
                fs_lunch = fs.get('lunch_break_minutes') or lunch
                full_span_min = (datetime.combine(datetime.today(), fs_end) -
                                 datetime.combine(datetime.today(), fs_start)).total_seconds() / 60
                fs_wh = (full_span_min - fs_lunch) / 60
                return fs_start, fs_end, fs_lunch, fs_wh
            return sched_start, sched_end, lunch, wh

        # Identify multi-contract jarvis_uids — these are handled by
        # _adjust_per_group instead of getting individual global adjustments.
        multi_contract_uids = set()
        for juid, ivs in all_intervals.items():
            if len(ivs) > 1:
                multi_contract_uids.add(juid)

        # --- Off-schedule employees (have punches but deviate) ---
        for row in off:
            first = row['first_punch']
            last = row['last_punch']
            sched_start = row['schedule_start']
            sched_end = row['schedule_end']
            lunch = row.get('lunch_break_minutes') or 60
            wh = row.get('working_hours') or 8

            if not sched_start or not sched_end:
                continue

            jarvis_uid = row.get('mapped_jarvis_user_id')

            # Multi-contract: handled by _adjust_per_group below
            if jarvis_uid and jarvis_uid in multi_contract_uids:
                continue

            # Single-contract: blanket leave check
            if jarvis_uid and jarvis_uid in leave_ids:
                continue

            if not first or not last:
                continue

            # Override with full combined schedule (base + secondary contracts)
            sched_start, sched_end, lunch, wh = _override_schedule(
                row, sched_start, sched_end, lunch, wh)

            adj_first, adj_last = self._randomize_times(first, sched_start, lunch, wh)

            self.adjust_employee(
                biostar_user_id=row['biostar_user_id'],
                date_str=date_str,
                adjusted_first=adj_first,
                adjusted_last=adj_last,
                original_first=first,
                original_last=last,
                schedule_start=sched_start,
                schedule_end=sched_end,
                lunch_break_minutes=lunch,
                working_hours=wh,
                original_duration=row.get('duration_seconds'),
                deviation_in=round(row.get('deviation_in') or 0),
                deviation_out=round(row.get('deviation_out') or 0),
                adjustment_type='auto',
                adjusted_by=user_id,
            )
            adjusted_count += 1

        # --- Absent employees (no punches, past day) ---
        for row in absent:
            sched_start = row['schedule_start']
            sched_end = row['schedule_end']
            lunch = row.get('lunch_break_minutes') or 60

            if not sched_start or not sched_end:
                continue

            jarvis_uid = row.get('mapped_jarvis_user_id')

            # Multi-contract: handled by _adjust_per_group below
            if jarvis_uid and jarvis_uid in multi_contract_uids:
                continue

            # Single-contract: blanket leave check
            if jarvis_uid and jarvis_uid in leave_ids:
                continue

            sched_start = _parse_time(sched_start)
            sched_end = _parse_time(sched_end)
            wh = row.get('working_hours') or 8

            # Override with full combined schedule (base + secondary contracts)
            sched_start, sched_end, lunch, wh = _override_schedule(
                row, sched_start, sched_end, lunch, wh)

            ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_offset = random.randint(-3, 3)
            end_offset = random.randint(-3, 5)
            adj_first = datetime.combine(ref_date, sched_start) + timedelta(minutes=start_offset)
            adj_last = datetime.combine(ref_date, sched_end) + timedelta(minutes=end_offset)

            self.adjust_employee(
                biostar_user_id=row['biostar_user_id'],
                date_str=date_str,
                adjusted_first=adj_first,
                adjusted_last=adj_last,
                original_first=None,
                original_last=None,
                schedule_start=sched_start,
                schedule_end=sched_end,
                lunch_break_minutes=lunch,
                working_hours=wh,
                original_duration=0,
                deviation_in=0,
                deviation_out=0,
                adjustment_type='auto',
                adjusted_by=user_id,
            )
            adjusted_count += 1

        # --- Per-group adjustments for multi-contract employees ---
        # Each group's buid gets its own adjustment based on Sincron schedule.
        processed_uids = set()
        for row in list(off) + list(absent):
            juid = row.get('mapped_jarvis_user_id')
            if not juid or juid not in multi_contract_uids or juid in processed_uids:
                continue
            processed_uids.add(juid)

            intervals = all_intervals[juid]
            # Filter out companies on leave
            leave_companies = leave_by_company.get(juid, set())
            active_intervals = [iv for iv in intervals if iv['company'] not in leave_companies]

            if not active_intervals:
                continue

            try:
                self._adjust_per_group(juid, date_str, active_intervals, user_id)
                adjusted_count += len(active_intervals)
            except Exception as e:
                logger.warning('Per-group adjust failed for user %s on %s: %s',
                               juid, date_str, e)

        total_flagged = len(off) + len(absent)
        return {'adjusted': adjusted_count, 'total_flagged': total_flagged}

    def _is_public_holiday(self, date_str):
        """Check if a date is a public holiday."""
        try:
            from core.utils.holidays_repository import HolidayRepository
            repo = HolidayRepository()
            year = int(date_str[:4])
            holidays = repo.get_holidays_for_year(year)
            holiday_dates = set()
            for h in holidays:
                d = h['date']
                holiday_dates.add(d.isoformat() if hasattr(d, 'isoformat') else str(d))
            return date_str in holiday_dates
        except Exception:
            return False

    def _is_weekend(self, date_str):
        """Check if a date is a weekend (Saturday or Sunday)."""
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return d.weekday() >= 5  # 5=Saturday, 6=Sunday

    def auto_adjust_single(self, biostar_user_id, date_str, user_id=None,
                           group_name=None):
        """Auto-adjust a single employee for a specific date using Sincron per-day schedule.

        group_name: if provided, only adjust that specific group's interval.
                    The adjustment is stored under the buid belonging to that group.
                    If None, auto-detect: multi-contract employees get per-group
                    adjustments, single-contract get a single adjustment.
        """
        from datetime import time as _time

        # Skip public holidays
        if self._is_public_holiday(date_str):
            return {'success': False, 'error': 'Date is a public holiday'}

        employee = self.repo.get_employee_by_biostar_id(biostar_user_id)
        if not employee:
            return {'success': False, 'error': 'Employee not found'}

        jarvis_uid = employee.get('mapped_jarvis_user_id')

        # Check for Sincron leave codes and get per-company intervals
        leave_companies = set()  # companies on leave (for per-company filtering)
        if jarvis_uid:
            try:
                from core.connectors.sincron.repositories.sincron_repository import SincronRepository
                sincron_repo = SincronRepository()

                LEAVE_CODES = ('CO', 'CM', 'CIC', 'CES', 'CMS', 'DLG', 'ZLS', 'CFP', 'CFS', 'INV')
                leave_rows = sincron_repo.query_all('''
                    SELECT COALESCE(co.company, se.company_name) AS company,
                           st.short_code
                    FROM sincron_employees se
                    JOIN sincron_timesheets st
                      ON st.sincron_employee_id = se.sincron_employee_id
                      AND st.company_name = se.company_name
                      AND st.day = %s::date
                      AND st.short_code = ANY(%s)
                    LEFT JOIN companies co ON co.id = se.company_id
                    WHERE se.mapped_jarvis_user_id = %s
                      AND se.is_active = TRUE
                ''', (date_str, list(LEAVE_CODES), jarvis_uid))
                leave_companies = {r['company'] for r in leave_rows}

                # Get per-company intervals
                intervals = sincron_repo.get_day_intervals_by_jarvis_user(jarvis_uid, date_str)
            except Exception as e:
                logger.warning('Sincron schedule lookup failed for user %s on %s: %s',
                               jarvis_uid, date_str, e)
                intervals = []
        else:
            intervals = []

        # If a specific group was requested, filter to its company_id
        if group_name and intervals:
            group_map = self.get_group_company_map()  # {group: company_id}
            target_cid = group_map.get(group_name)
            if target_cid:
                intervals = [iv for iv in intervals
                             if iv.get('company_id') == target_cid]
            if not intervals:
                return {'success': False, 'error': f'No schedule found for group {group_name}'}

        # Filter out companies on leave (per-company, not blanket)
        if leave_companies and intervals:
            intervals = [iv for iv in intervals if iv['company'] not in leave_companies]

        # If ALL companies are on leave, skip entirely
        if not intervals and leave_companies:
            codes = ', '.join(r['short_code'] for r in leave_rows)
            return {'success': False, 'error': f'Employee on leave ({codes}) for this date'}

        # Multi-contract: per-group adjustments
        if len(intervals) > 1 or (len(intervals) == 1 and group_name):
            return self._adjust_per_group(
                jarvis_uid, date_str, intervals, user_id)

        # Single-contract / legacy: full-span adjustment
        sched_start = employee.get('schedule_start')
        sched_end = employee.get('schedule_end')
        lunch = employee.get('lunch_break_minutes') or 60
        wh = employee.get('working_hours') or 8

        if intervals:
            # Single Sincron interval
            iv = intervals[0]
            parts_s = iv['start'].split(':')
            parts_e = iv['end'].split(':')
            sched_start = _time(int(parts_s[0]), int(parts_s[1]))
            sched_end = _time(int(parts_e[0]), int(parts_e[1]))
            lunch = iv.get('lunch_break_minutes') or 0
        elif jarvis_uid:
            try:
                full_sched = sincron_repo.get_full_day_schedule_by_jarvis_user(
                    jarvis_uid, date_str, include_excluded=True)
                if full_sched:
                    if full_sched.get('schedule_start'):
                        parts = str(full_sched['schedule_start']).split(':')
                        sched_start = _time(int(parts[0]), int(parts[1]))
                    if full_sched.get('schedule_end'):
                        parts = str(full_sched['schedule_end']).split(':')
                        sched_end = _time(int(parts[0]), int(parts[1]))
                    if full_sched.get('lunch_break_minutes') is not None:
                        lunch = full_sched['lunch_break_minutes']
            except Exception:
                pass

        if not sched_start or not sched_end:
            return {'success': False, 'error': 'No schedule found'}

        full_span_min = (datetime.combine(datetime.today(), sched_end) -
                         datetime.combine(datetime.today(), sched_start)).total_seconds() / 60
        wh = (full_span_min - lunch) / 60

        punches = self.repo.get_punch_logs(biostar_user_id, f'{date_str} 00:00:00', f'{date_str} 23:59:59')

        if punches:
            fp = punches[-1]['event_datetime']
            lp = punches[0]['event_datetime']
            first_punch = fp if isinstance(fp, datetime) else datetime.fromisoformat(str(fp))
            last_punch = lp if isinstance(lp, datetime) else datetime.fromisoformat(str(lp))
            duration = (last_punch - first_punch).total_seconds() if len(punches) > 1 else 0
            deviation_in = round((first_punch - datetime.combine(first_punch.date(), sched_start)).total_seconds() / 60)
            deviation_out = round((last_punch - datetime.combine(last_punch.date(), sched_end)).total_seconds() / 60) if len(punches) > 1 else 0
        else:
            first_punch = None
            last_punch = None
            duration = 0
            deviation_in = 0
            deviation_out = 0

        ref_date = first_punch.date() if first_punch else datetime.strptime(date_str, '%Y-%m-%d').date()

        if not punches:
            start_offset = random.randint(-3, 3)
            end_offset = random.randint(-3, 5)
            adj_first = datetime.combine(ref_date, sched_start) + timedelta(minutes=start_offset)
            adj_last = datetime.combine(ref_date, sched_end) + timedelta(minutes=end_offset)
        else:
            synthetic_ref = datetime.combine(ref_date, sched_start)
            adj_first, adj_last = self._randomize_times(synthetic_ref, sched_start, lunch, wh)

        self.adjust_employee(
            biostar_user_id=biostar_user_id,
            date_str=date_str,
            adjusted_first=adj_first,
            adjusted_last=adj_last,
            original_first=first_punch,
            original_last=last_punch,
            schedule_start=sched_start,
            schedule_end=sched_end,
            lunch_break_minutes=lunch,
            working_hours=wh,
            original_duration=duration,
            deviation_in=deviation_in,
            deviation_out=deviation_out,
            adjustment_type='auto',
            adjusted_by=user_id,
        )
        return {'success': True, 'adjusted_first': str(adj_first), 'adjusted_last': str(adj_last)}

    def _adjust_per_group(self, jarvis_uid, date_str, intervals, user_id):
        """Generate per-group adjustments for multi-contract employees.

        Each BioStar group (= biostar_user_id) gets its own adjustment based on
        the Sincron schedule for the company mapped to that group.  Punches from
        ALL of the employee's buids are collected and split across time windows.
        """
        from datetime import time as _time

        ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Get all active buids for this JARVIS user, keyed by group name
        buids = self.repo.query_all('''
            SELECT biostar_user_id, user_group_name
            FROM biostar_employees
            WHERE mapped_jarvis_user_id = %s AND status = 'active'
        ''', (jarvis_uid,))
        all_buid_list = [b['biostar_user_id'] for b in buids]

        # Build company_id → buid map via group → company_id
        group_map = self.get_group_company_map()  # {group_name: company_id}
        cid_to_buid = {}
        for b in buids:
            cid = group_map.get(b['user_group_name'])
            if cid:
                cid_to_buid[cid] = b['biostar_user_id']

        # Split punches from ALL buids into time intervals
        split = self.repo.get_employee_punches_by_interval(
            all_buid_list, date_str, intervals)

        results = []
        for iv in split:
            # Find the buid that owns this interval's company
            target_buid = cid_to_buid.get(iv.get('company_id'))
            if not target_buid:
                continue  # no BioStar employee for this group — skip

            parts_s = iv['start'].split(':')
            parts_e = iv['end'].split(':')
            sched_start = _time(int(parts_s[0]), int(parts_s[1]))
            sched_end = _time(int(parts_e[0]), int(parts_e[1]))

            # Find lunch from the interval data (base contract has lunch, secondary usually 0)
            matching_iv = next((x for x in intervals
                                if x.get('company_id') == iv.get('company_id')), None)
            lunch = (matching_iv.get('lunch_break_minutes') or 0) if matching_iv else 0

            span_min = (datetime.combine(ref_date, sched_end) -
                        datetime.combine(ref_date, sched_start)).total_seconds() / 60
            wh = (span_min - lunch) / 60

            fp_str = iv.get('first_punch')
            lp_str = iv.get('last_punch')
            first_punch = datetime.fromisoformat(fp_str) if fp_str else None
            last_punch = datetime.fromisoformat(lp_str) if lp_str else None
            punch_count = iv.get('punch_count', 0)
            duration = iv.get('duration_seconds') or 0

            if first_punch:
                deviation_in = round((first_punch - datetime.combine(ref_date, sched_start)).total_seconds() / 60)
                deviation_out = round((last_punch - datetime.combine(ref_date, sched_end)).total_seconds() / 60) if punch_count > 1 else 0
            else:
                deviation_in = 0
                deviation_out = 0

            # Generate adjusted times for this interval
            if not first_punch:
                start_offset = random.randint(-3, 3)
                end_offset = random.randint(-3, 5)
                adj_first = datetime.combine(ref_date, sched_start) + timedelta(minutes=start_offset)
                adj_last = datetime.combine(ref_date, sched_end) + timedelta(minutes=end_offset)
            else:
                synthetic_ref = datetime.combine(ref_date, sched_start)
                adj_first, adj_last = self._randomize_times(synthetic_ref, sched_start, lunch, wh)

            self.adjust_employee(
                biostar_user_id=target_buid,
                date_str=date_str,
                adjusted_first=adj_first,
                adjusted_last=adj_last,
                original_first=first_punch,
                original_last=last_punch,
                schedule_start=sched_start,
                schedule_end=sched_end,
                lunch_break_minutes=lunch,
                working_hours=wh,
                original_duration=duration,
                deviation_in=deviation_in,
                deviation_out=deviation_out,
                adjustment_type='auto',
                adjusted_by=user_id,
            )
            results.append({
                'biostar_user_id': target_buid,
                'company': iv['company'],
                'adjusted_first': str(adj_first),
                'adjusted_last': str(adj_last),
            })

        return {'success': True, 'intervals': results}

    def backfill_adjustments(self, threshold=15, user_id=None):
        """Auto-adjust all past dates with unadjusted off-schedule employees."""
        dates = self.adj_repo.get_unadjusted_dates()
        total_adjusted = 0
        dates_processed = 0
        for row in dates:
            date_str = str(row['punch_date'])
            result = self.auto_adjust_all(date_str, threshold, user_id=user_id)
            total_adjusted += result['adjusted']
            if result['adjusted'] > 0:
                dates_processed += 1
        return {'dates_processed': dates_processed, 'total_adjusted': total_adjusted}

    def revert_adjustment(self, biostar_user_id, date_str):
        """Revert an adjustment (delete it, back to original punches)."""
        return self.adj_repo.delete_adjustment(biostar_user_id, date_str)

    def revert_adjustments_range(self, start_date, end_date):
        """Revert all auto-adjustments in a date range."""
        return self.adj_repo.delete_adjustments_range(start_date, end_date, adjustment_type='auto')
