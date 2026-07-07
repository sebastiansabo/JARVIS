"""Sincron sync service — orchestrates multi-company timesheet sync.

Fetches monthly timesheet data from Sincron API for all configured
Autoworld companies, transforms and stores in local DB, and manages
employee ↔ JARVIS user mapping.
"""

import json
import logging
from datetime import datetime

from ..client.sincron_client import SincronClient
from ..client.exceptions import SincronError
from ..repositories.sincron_repository import SincronRepository
from ..repositories.sync_repo import SincronSyncRepository
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.auth.repositories.user_repository import UserRepository

logger = logging.getLogger('jarvis.sincron.service')


class SincronSyncService:
    """Business logic for Sincron timesheet connector."""

    def __init__(self):
        self.repo = SincronRepository()
        self.sync_repo = SincronSyncRepository()
        self.connector_repo = ConnectorRepository()
        self.user_repo = UserRepository()

    # ── Connection config ──

    def get_connection_config(self):
        """Get stored Sincron connector configuration."""
        connector = self.connector_repo.get_by_type('sincron')
        if not connector:
            return None
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)
        # Only expose configured status per company, never token values
        tokens = config.get('company_tokens', {})
        masked = {k: True for k in tokens}
        return {
            'id': connector['id'],
            'status': connector.get('status', 'disconnected'),
            'last_sync': str(connector['last_sync']) if connector.get('last_sync') else None,
            'companies_configured': masked,
            'companies_count': len(tokens),
        }

    def save_connection(self, company_tokens):
        """Save or update Sincron connector config.

        company_tokens: dict of {company_name: bearer_token}
        """
        if not company_tokens:
            raise ValueError('company_tokens dict is required')

        config = {'company_tokens': company_tokens}

        connector = self.connector_repo.get_by_type('sincron')
        if connector:
            self.connector_repo.update(
                connector['id'],
                config=config,  # ConnectorRepository handles json.dumps
                status='connected',
            )
            return connector['id']
        else:
            return self.connector_repo.save(
                connector_type='sincron',
                name='Sincron HR',
                status='connected',
                config=config,  # ConnectorRepository handles json.dumps
                credentials={},
            )

    def _get_company_tokens(self):
        """Get company→token mapping from connector config."""
        connector = self.connector_repo.get_by_type('sincron')
        if not connector:
            return {}
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)
        return config.get('company_tokens', {})

    def _get_client(self, company_name):
        """Get a SincronClient for a specific company."""
        tokens = self._get_company_tokens()
        token = tokens.get(company_name)
        if not token:
            raise SincronError(f'No token configured for company: {company_name}')
        return SincronClient(token)

    # ── Test connection ──

    def test_connection(self, company_name=None):
        """Test connectivity for one or all companies."""
        tokens = self._get_company_tokens()
        if not tokens:
            return {'success': False, 'error': 'No tokens configured. Save config first.',
                    'companies': {}}
        if company_name:
            tokens = {company_name: tokens.get(company_name)}

        results = {}
        for comp, token in tokens.items():
            if not token:
                results[comp] = {'success': False, 'error': 'No token'}
                continue
            try:
                client = SincronClient(token)
                result = client.test_connection()
                results[comp] = result
                client.close()
            except SincronError as e:
                results[comp] = {'success': False, 'error': str(e)}
            except Exception as e:
                logger.exception(f'Test connection failed for {comp}')
                results[comp] = {'success': False, 'error': 'Connection test failed'}

        all_ok = all(r.get('success') for r in results.values())
        return {'success': all_ok, 'companies': results}

    # ── Sync timesheets ──

    def sync_timesheets(self, year=None, month=None, company_name=None):
        """Sync timesheet data for given month across all (or one) companies.

        For current-month syncs, employees missing from the API response
        are marked inactive (contract closed) in both sincron_employees
        and the linked JARVIS user.
        """
        now = datetime.now()
        if not year or not month:
            year = year or now.year
            month = month or now.month

        # Only deactivate missing employees on current-month syncs
        is_current_month = (year == now.year and month == now.month)

        tokens = self._get_company_tokens()
        if not tokens:
            return {'success': False, 'error': 'No tokens configured'}

        if company_name:
            tokens = {company_name: tokens.get(company_name)}

        # Build company_name → company_id lookup from JARVIS companies table
        company_id_map = self._get_company_id_map()

        total_employees = 0
        total_records = 0
        total_deactivated = 0
        company_results = {}

        for comp, token in tokens.items():
            if not token:
                company_results[comp] = {'success': False, 'error': 'No token'}
                continue

            run = self.sync_repo.create_run('timesheet', comp, year, month)
            run_id = run['run_id'] if run else None

            try:
                result = self._sync_company_timesheets(comp, token, year, month,
                                                       company_id=company_id_map.get(comp.upper()))
                company_results[comp] = result
                total_employees += result.get('employees', 0)
                total_records += result.get('records', 0)

                # Deactivate employees missing from current-month API response.
                # Skip first 5 days of the month — Sincron data may be
                # incomplete until the accountant enters all timesheets.
                if is_current_month and now.day > 5 and result.get('success'):
                    deactivated = self._deactivate_missing_employees(
                        comp, result.pop('_synced_ids', set()))
                    result['deactivated'] = deactivated
                    total_deactivated += deactivated

                if run_id:
                    self.sync_repo.complete_run(
                        run_id, success=True,
                        employees_synced=result.get('employees', 0),
                        records_created=result.get('records', 0),
                    )
            except Exception as e:
                logger.exception(f'Sync failed for {comp}')
                company_results[comp] = {'success': False, 'error': 'Sync failed'}
                if run_id:
                    self.sync_repo.complete_run(
                        run_id, success=False, error_message=str(e))

        # Update connector last_sync
        connector = self.connector_repo.get_by_type('sincron')
        if connector:
            self.connector_repo.update(connector['id'], last_sync=datetime.now())

        # Re-activate JARVIS users whose Sincron records came back
        total_reactivated = self._reactivate_returned_employees()

        # Recalculate base contracts (primary norm per CNP)
        base_marked = 0
        try:
            base_marked = self.repo.recalculate_base_contracts()
            logger.info(f'Base contracts recalculated: {base_marked} employees marked')
        except Exception as e:
            logger.error(f'Base contract recalculation failed: {e}')

        # Backfill BioStar employee schedules from Sincron combined norms
        biostar_updated = 0
        try:
            biostar_updated = self._sync_biostar_schedules()
        except Exception as e:
            logger.error(f'BioStar schedule backfill failed: {e}')
            # Log failure to connector config
            try:
                connector = self.connector_repo.get_by_type('sincron')
                if connector:
                    config = connector.get('config') or {}
                    if isinstance(config, str):
                        config = json.loads(config)
                    cron_jobs = config.get('cron_jobs', {})
                    cron_jobs['biostar_schedule_backfill'] = {
                        'last_run': datetime.now().isoformat(),
                        'last_success': False,
                        'last_message': str(e),
                    }
                    config['cron_jobs'] = cron_jobs
                    self.connector_repo.update(connector['id'], config=config)
            except Exception:
                pass

        return {
            'success': True,
            'year': year,
            'month': month,
            'total_employees': total_employees,
            'total_records': total_records,
            'total_deactivated': total_deactivated,
            'total_reactivated': total_reactivated,
            'base_contracts_marked': base_marked,
            'biostar_schedules_updated': biostar_updated,
            'companies': company_results,
        }

    def _sync_biostar_schedules(self):
        """Backfill BioStar employee schedules from Sincron combined norms.

        For multi-company employees: SUM hours, MIN start, MAX end, SUM breaks.
        Uses existing biostar_repository.update_schedule() per employee.
        Returns the number of BioStar employees updated.
        """
        from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
        biostar_repo = BioStarRepository()

        combined = self.repo.get_combined_schedules_for_biostar()
        if not combined:
            return 0

        # Get BioStar employees mapped to JARVIS users for lookup
        biostar_employees = biostar_repo.query_all('''
            SELECT biostar_user_id, mapped_jarvis_user_id
            FROM biostar_employees
            WHERE mapped_jarvis_user_id IS NOT NULL AND status = 'active'
        ''')
        jarvis_to_biostar = {
            row['mapped_jarvis_user_id']: row['biostar_user_id']
            for row in biostar_employees
        }

        updated = 0
        for row in combined:
            jarvis_id = row['mapped_jarvis_user_id']
            biostar_id = jarvis_to_biostar.get(jarvis_id)
            if not biostar_id:
                continue

            start_str = str(row['combined_start'])[:5] if row.get('combined_start') else None
            end_str = str(row['combined_end'])[:5] if row.get('combined_end') else None

            biostar_repo.update_schedule(
                biostar_user_id=biostar_id,
                lunch_break_minutes=int(row['total_lunch'] or 0),
                working_hours=float(row['total_working_hours'] or 8),
                schedule_start=start_str,
                schedule_end=end_str,
            )
            updated += 1

        logger.info(f'BioStar schedule backfill: {updated} employees updated from Sincron norms')

        # Persist result to connector config for UI visibility
        try:
            connector = self.connector_repo.get_by_type('sincron')
            if connector:
                config = connector.get('config') or {}
                if isinstance(config, str):
                    config = json.loads(config)
                cron_jobs = config.get('cron_jobs', {})
                cron_jobs['biostar_schedule_backfill'] = {
                    'last_run': datetime.now().isoformat(),
                    'last_success': True,
                    'last_message': f'{updated} BioStar employees updated',
                }
                config['cron_jobs'] = cron_jobs
                self.connector_repo.update(connector['id'], config=config)
        except Exception as e:
            logger.error(f'Failed to save biostar backfill log: {e}')

        return updated

    def _deactivate_missing_employees(self, company_name, synced_ids):
        """Deactivate employees missing from the Sincron API response.

        1. Marks missing sincron_employees records as inactive/closed.
        2. For mapped JARVIS users, only closes the user contract if they
           have NO remaining active sincron_employees across ALL companies.
        """
        db_active_ids = self.repo.get_active_employee_ids(company_name)
        missing_ids = db_active_ids - synced_ids

        if not missing_ids:
            return 0

        logger.info(f'{company_name}: {len(missing_ids)} employees missing from '
                     f'Sincron API — deactivating: {missing_ids}')

        # Close sincron_employees records, get affected JARVIS user IDs
        jarvis_user_ids = self.repo.deactivate_employees(company_name, missing_ids)

        # Only close JARVIS user if they have NO active sincron records left
        closed_users = 0
        for user_id in jarvis_user_ids:
            if not self.repo.has_active_contracts(user_id):
                self.repo.execute('''
                    UPDATE users SET contract_status = 'closed', updated_at = NOW()
                    WHERE id = %s AND COALESCE(contract_status, 'active') != 'closed'
                ''', (user_id,))
                logger.info(f'Closed JARVIS user {user_id} — no active Sincron contracts remain')
                closed_users += 1

        return len(missing_ids)

    def _reactivate_returned_employees(self):
        """Re-activate JARVIS users whose Sincron records came back.

        When upsert_employee re-activates a sincron_employees record
        (is_active=TRUE), the mapped JARVIS user may still be stuck
        as contract_status='closed'. This method fixes that mismatch.
        """
        rows = self.repo.query_all('''
            UPDATE users SET contract_status = 'active', updated_at = NOW()
            WHERE contract_status = 'closed'
              AND id IN (
                  SELECT DISTINCT mapped_jarvis_user_id
                  FROM sincron_employees
                  WHERE is_active = TRUE AND mapped_jarvis_user_id IS NOT NULL
              )
            RETURNING id, name
        ''')
        for r in rows:
            logger.info(f'Re-activated JARVIS user {r["id"]} ({r["name"]}) '
                        f'— active Sincron contract found')
        return len(rows)

    def _get_company_id_map(self):
        """Build UPPER(company_name) → company_id lookup from companies table."""
        rows = self.repo.query_all(
            "SELECT id, UPPER(company) AS uname FROM companies"
        )
        return {r['uname']: r['id'] for r in rows}

    def _sync_company_timesheets(self, company_name, token, year, month, company_id=None):
        """Sync timesheets for a single company."""
        client = SincronClient(token)
        try:
            all_employees = client.get_all_timesheets(month, year)
        finally:
            client.close()

        employees_synced = 0
        records_created = 0
        discovered_codes = set()
        synced_ids = set()

        for emp in all_employees:
            sincron_id = str(emp.get('id_angajat', ''))
            if not sincron_id:
                continue
            synced_ids.add(sincron_id)

            # Handle invalid dates from API (e.g. "0000-00-00")
            contract_date = emp.get('data_incepere_contract')
            if contract_date in ('0000-00-00', '', None):
                contract_date = None

            # Extract employee-level schedule from first OZ activity
            norma_lucru = emp.get('norma_lucru')
            norma_lucru_time = emp.get('norma_lucru_time')
            emp_schedule_in = None
            emp_schedule_out = None
            emp_break = None
            for _day_acts in emp.get('days', {}).values():
                for _a in _day_acts:
                    if _a.get('short_code') == 'OZ' and _a.get('program', {}).get('in'):
                        emp_schedule_in = _a['program']['in']
                        emp_schedule_out = _a['program'].get('out')
                        emp_break = _a['program'].get('pauza_masa')
                        break
                if emp_schedule_in:
                    break

            # Parse norma_lucru to numeric
            try:
                norma_val = float(norma_lucru) if norma_lucru else None
            except (ValueError, TypeError):
                norma_val = None

            # Parse break to int
            try:
                break_val = int(emp_break) if emp_break else None
            except (ValueError, TypeError):
                break_val = None

            # Upsert employee (with schedule fields)
            # Clean whitespace from Sincron names (trailing spaces, double spaces)
            raw_nume = ' '.join(emp.get('nume', '').split())
            raw_prenume = ' '.join(emp.get('prenume', '').split())
            self.repo.upsert_employee(
                sincron_employee_id=sincron_id,
                company_name=company_name,
                nume=raw_nume,
                prenume=raw_prenume,
                cnp=emp.get('cnp'),
                id_contract=str(emp.get('id_contract', '')),
                nr_contract=str(emp.get('nr_contract', '')),
                data_incepere_contract=contract_date,
                norma_lucru=norma_val,
                norma_lucru_time=norma_lucru_time,
                schedule_start=emp_schedule_in,
                schedule_end=emp_schedule_out,
                lunch_break_minutes=break_val,
                company_id=company_id,
            )
            employees_synced += 1

            # Snapshot schedule for this month (historical record)
            self.repo.upsert_schedule_snapshot(
                sincron_employee_id=sincron_id,
                company_name=company_name,
                year=year,
                month=month,
                norma_lucru=norma_val,
                norma_lucru_time=norma_lucru_time,
                schedule_start=emp_schedule_in,
                schedule_end=emp_schedule_out,
                lunch_break_minutes=break_val,
            )

            # Delete existing month data and re-insert (clean sync)
            self.repo.delete_month_timesheets(sincron_id, company_name, year, month)

            # Process days
            days = emp.get('days', {})
            for day_str, activities in days.items():
                if not activities:
                    continue
                for activity in activities:
                    short_code = activity.get('short_code', '')
                    if not short_code:
                        continue

                    short_code_en = activity.get('short_code_en', '')
                    unit = activity.get('unit', 'hour')
                    try:
                        value = float(activity.get('value', 0))
                    except (ValueError, TypeError):
                        value = 0

                    # Extract per-activity program schedule
                    prog = activity.get('program', {})
                    prog_in = prog.get('in') if prog else None
                    prog_out = prog.get('out') if prog else None
                    try:
                        prog_break = int(prog.get('pauza_masa')) if prog and prog.get('pauza_masa') else None
                    except (ValueError, TypeError):
                        prog_break = None

                    self.repo.upsert_timesheet_day(
                        sincron_employee_id=sincron_id,
                        company_name=company_name,
                        year=year,
                        month=month,
                        day=day_str,
                        short_code=short_code,
                        short_code_en=short_code_en,
                        unit=unit,
                        value=value,
                        program_in=prog_in,
                        program_out=prog_out,
                        program_break=prog_break,
                    )
                    records_created += 1
                    discovered_codes.add((short_code, short_code_en))

        # Auto-discover activity codes
        for code, code_en in discovered_codes:
            self.repo.upsert_activity_code(code, code_en)

        return {
            'success': True,
            'employees': employees_synced,
            'records': records_created,
            'activity_codes': len(discovered_codes),
            '_synced_ids': synced_ids,  # internal use only, stripped before jsonify
        }

    # ── Auto-mapping ──

    def auto_map_employees(self):
        """Auto-map unmapped Sincron employees to JARVIS users.

        Strategy: CNP match first (highest confidence), then name match.
        After mapping, propagate CNP to users table (canonical source).
        """
        cnp_mapped = self.repo.auto_map_by_cnp()
        name_mapped = self.repo.auto_map_by_name()
        # Propagate CNP from Sincron → users (canonical source of truth)
        cnp_propagated = 0
        try:
            cnp_propagated = self.repo.propagate_cnp_to_users() or 0
        except Exception:
            logger.exception('CNP propagation failed after Sincron auto-map')
        return {
            'success': True,
            'cnp_mapped': cnp_mapped,
            'name_mapped': name_mapped,
            'total_mapped': cnp_mapped + name_mapped,
            'cnp_propagated': cnp_propagated,
        }

    # ── Query methods ──

    def get_employees(self, company_name=None, active_only=True):
        """Get all synced employees."""
        return self.repo.get_all_employees(company_name, active_only)

    def get_employee_stats(self):
        """Get employee counts."""
        return self.repo.get_employee_stats()

    def get_employee_timesheet(self, jarvis_user_id, year, month):
        """Get monthly timesheet for a JARVIS user."""
        # Get employee info first — even if no timesheet data for this month
        employee = self.repo.get_employee_by_jarvis_id(jarvis_user_id)

        rows = self.repo.get_timesheet_by_jarvis_user(jarvis_user_id, year, month)

        # Group by day
        days = {}
        for row in rows:
            day_str = str(row['day'])
            if day_str not in days:
                days[day_str] = []
            days[day_str].append({
                'short_code': row['short_code'],
                'short_code_en': row.get('short_code_en', ''),
                'unit': row['unit'],
                'value': float(row['value']),
            })

        # Summary by code
        summary_rows = self.repo.get_timesheet_summary_by_jarvis_user(
            jarvis_user_id, year, month)
        summary = [
            {
                'short_code': r['short_code'],
                'short_code_en': r.get('short_code_en', ''),
                'unit': r['unit'],
                'total_value': float(r['total_value']),
                'day_count': r['day_count'],
            }
            for r in summary_rows
        ]

        emp_info = None
        if employee:
            emp_info = {
                'sincron_employee_id': employee['sincron_employee_id'],
                'company_name': employee['company_name'],
                'nume': employee['nume'],
                'prenume': employee['prenume'],
                'nr_contract': employee.get('nr_contract'),
                'data_incepere_contract': str(employee['data_incepere_contract']) if employee.get('data_incepere_contract') else None,
            }

        return {
            'days': days,
            'summary': summary,
            'employee': emp_info,
        }

    def get_team_timesheet_summary(self, jarvis_user_ids, year, month):
        """Get team timesheet summary for multiple users."""
        rows = self.repo.get_team_timesheet_summary(jarvis_user_ids, year, month)

        # Group by user + company (sincron_employee_id is per-company, not global)
        by_user_company = {}
        for row in rows:
            uid = row['mapped_jarvis_user_id']
            company = row['company_name']
            key = (uid, company)
            if key not in by_user_company:
                by_user_company[key] = {
                    'user_id': uid,
                    'name': row['employee_name'],
                    'company': company,
                    'codes': {},
                    'total_hours': 0,
                }
            code = row['short_code']
            val = float(row['total_value'])
            by_user_company[key]['codes'][code] = {
                'value': val,
                'unit': row['unit'],
                'days': row['day_count'],
            }
            if row['unit'] == 'hour':
                by_user_company[key]['total_hours'] += val

        return list(by_user_company.values())

    def get_status(self):
        """Get connector status summary."""
        connector = self.connector_repo.get_by_type('sincron')
        if not connector:
            return {
                'connected': False,
                'status': 'disconnected',
                'employee_count': {'total': 0, 'mapped': 0, 'unmapped': 0, 'companies': 0},
            }

        stats = self.repo.get_employee_stats()
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)

        return {
            'connected': connector.get('status') == 'connected',
            'status': connector.get('status', 'disconnected'),
            'last_sync': str(connector['last_sync']) if connector.get('last_sync') else None,
            'companies_configured': len(config.get('company_tokens', {})),
            'employee_count': stats,
        }

    def get_sync_history(self, sync_type=None, limit=20):
        """Get recent sync runs."""
        return self.sync_repo.get_recent_runs(sync_type, limit)

    def get_activity_codes(self):
        """Get all discovered activity codes."""
        return self.repo.get_activity_codes()

    # ── Employee mapping management ──

    def update_employee_mapping(self, sincron_employee_id, company_name, jarvis_user_id):
        """Manually map a Sincron employee to a JARVIS user."""
        self.repo.update_mapping(sincron_employee_id, company_name, jarvis_user_id, 'manual')

    def remove_employee_mapping(self, sincron_employee_id, company_name):
        """Remove JARVIS user mapping."""
        self.repo.remove_mapping(sincron_employee_id, company_name)
