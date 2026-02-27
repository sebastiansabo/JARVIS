"""BioStar 2 sync service — orchestrates user and event synchronization."""

import json
from datetime import datetime, timedelta

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

            # 2. Transform to our schema
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
            'card_ids': card_ids,
            'status': status,
        }

    def _auto_map_employees(self):
        """Match BioStar employees to JARVIS users by name/email."""
        unmapped = self.repo.get_unmapped_employees()
        jarvis_users = self.repo.get_jarvis_users()

        # Build lookups
        name_lookup = {}
        email_lookup = {}
        for u in jarvis_users:
            name_key = (u.get('name') or '').strip().lower()
            if name_key:
                name_lookup[name_key] = u
            email_key = (u.get('email') or '').strip().lower()
            if email_key:
                email_lookup[email_key] = u

        newly_mapped = 0
        for emp in unmapped:
            # Try email match first (highest confidence)
            emp_email = (emp.get('email') or '').strip().lower()
            if emp_email and emp_email in email_lookup:
                jarvis_user = email_lookup[emp_email]
                self.repo.update_mapping(
                    emp['biostar_user_id'], jarvis_user['id'],
                    'auto_email', 100.0
                )
                newly_mapped += 1
                continue

            # Try exact name match
            emp_name = (emp.get('name') or '').strip().lower()
            if emp_name and emp_name in name_lookup:
                jarvis_user = name_lookup[emp_name]
                self.repo.update_mapping(
                    emp['biostar_user_id'], jarvis_user['id'],
                    'auto_name', 90.0
                )
                newly_mapped += 1
                continue

        return {
            'newly_mapped': newly_mapped,
            'still_unmapped': len(unmapped) - newly_mapped,
        }

    # ── Event Sync ──

    def sync_events(self, start_date=None, end_date=None):
        """Incremental sync: fetch events since last sync or given date range."""
        run = self.sync_repo.create_run('events')
        run_id = run['run_id']

        try:
            client = self._get_client()

            # Determine start date
            if not start_date:
                last_dt = self.repo.get_last_event_datetime()
                if last_dt:
                    start_date = last_dt.isoformat() if isinstance(last_dt, datetime) else str(last_dt)
                else:
                    start_date = (datetime.now() - timedelta(days=SYNC_EVENTS_DEFAULT_DAYS)).strftime('%Y-%m-%dT00:00:00.00Z')

            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.00Z')

            # Fetch events with pagination
            all_events = []
            offset = 0
            while True:
                result = client.search_events(start_date, end_date, offset=offset, limit=EVENTS_PAGE_SIZE)
                rows = result.get('EventCollection', {}).get('rows', [])
                all_events.extend(rows)
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

            self.sync_repo.complete_run(
                run_id, success=True,
                records_fetched=records_fetched,
                records_created=insert_result['inserted'],
                records_skipped=insert_result['skipped'],
                cursor_before=start_date if isinstance(start_date, datetime) else None,
                cursor_after=end_date if isinstance(end_date, datetime) else None,
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
            'event_datetime': raw.get('datetime', ''),
            'event_type': event_type,
            'direction': self._infer_direction(raw),
            'device_id': device_id,
            'device_name': device_name,
            'door_id': door_id,
            'door_name': door_name,
            'auth_type': raw.get('auth_type', ''),
            'raw_data': raw,
        }

    def _infer_direction(self, event):
        """Infer IN/OUT from tna_key or device/door name patterns."""
        tna_key = event.get('tna_key')
        if tna_key == 1 or tna_key == '1':
            return 'IN'
        if tna_key == 2 or tna_key == '2':
            return 'OUT'

        # Fallback: check device/door name patterns (Romanian)
        names_to_check = []
        device = event.get('device_id', {})
        if isinstance(device, dict):
            names_to_check.append((device.get('name', '') or '').lower())

        door_raw = event.get('door_id')
        if isinstance(door_raw, list):
            for d in door_raw:
                if isinstance(d, dict):
                    names_to_check.append((d.get('name', '') or '').lower())
        elif isinstance(door_raw, dict):
            names_to_check.append((door_raw.get('name', '') or '').lower())

        for name in names_to_check:
            if any(kw in name for kw in ('intrare', 'entry', 'in ')):
                return 'IN'
            if any(kw in name for kw in ('iesire', 'exit', 'out ')):
                return 'OUT'

        return None

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

    def get_daily_summary(self, date_str):
        """Get per-employee daily punch summary."""
        return self.repo.get_daily_summary(date_str)

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

    def adjust_employee(self, biostar_user_id, date_str, adjusted_first, adjusted_last,
                        original_first, original_last, schedule_start, schedule_end,
                        lunch_break_minutes, working_hours, original_duration,
                        deviation_in, deviation_out, adjustment_type='manual',
                        adjusted_by=None, notes=None):
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

    def auto_adjust_all(self, date_str, threshold=15, user_id=None):
        """Auto-adjust all off-schedule employees: snap punches to schedule times."""
        off = self.adj_repo.get_off_schedule(date_str, threshold)
        adjusted_count = 0
        for row in off:
            first = row['first_punch']
            last = row['last_punch']
            sched_start = row['schedule_start']
            sched_end = row['schedule_end']

            if not first or not last or not sched_start or not sched_end:
                continue

            # Build adjusted timestamps: use original date + schedule time
            date_part = first.date()
            adj_first = datetime.combine(date_part, sched_start)
            adj_last = datetime.combine(date_part, sched_end)

            self.adjust_employee(
                biostar_user_id=row['biostar_user_id'],
                date_str=date_str,
                adjusted_first=adj_first,
                adjusted_last=adj_last,
                original_first=first,
                original_last=last,
                schedule_start=sched_start,
                schedule_end=sched_end,
                lunch_break_minutes=row.get('lunch_break_minutes', 60),
                working_hours=row.get('working_hours', 8),
                original_duration=row.get('duration_seconds'),
                deviation_in=round(row.get('deviation_in') or 0),
                deviation_out=round(row.get('deviation_out') or 0),
                adjustment_type='auto',
                adjusted_by=user_id,
            )
            adjusted_count += 1

        return {'adjusted': adjusted_count, 'total_flagged': len(off)}

    def revert_adjustment(self, biostar_user_id, date_str):
        """Revert an adjustment (delete it, back to original punches)."""
        return self.adj_repo.delete_adjustment(biostar_user_id, date_str)
