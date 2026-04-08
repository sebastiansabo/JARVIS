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

logger = logging.getLogger('jarvis.sincron.service')


class SincronSyncService:
    """Business logic for Sincron timesheet connector."""

    def __init__(self):
        self.repo = SincronRepository()
        self.sync_repo = SincronSyncRepository()
        self.connector_repo = ConnectorRepository()

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
        """Sync timesheet data for given month across all (or one) companies."""
        if not year or not month:
            now = datetime.now()
            year = year or now.year
            month = month or now.month

        tokens = self._get_company_tokens()
        if not tokens:
            return {'success': False, 'error': 'No tokens configured'}

        if company_name:
            tokens = {company_name: tokens.get(company_name)}

        total_employees = 0
        total_records = 0
        company_results = {}

        for comp, token in tokens.items():
            if not token:
                company_results[comp] = {'success': False, 'error': 'No token'}
                continue

            run = self.sync_repo.create_run('timesheet', comp, year, month)
            run_id = run['run_id'] if run else None

            try:
                result = self._sync_company_timesheets(comp, token, year, month)
                company_results[comp] = result
                total_employees += result.get('employees', 0)
                total_records += result.get('records', 0)

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

        return {
            'success': True,
            'year': year,
            'month': month,
            'total_employees': total_employees,
            'total_records': total_records,
            'companies': company_results,
        }

    def _sync_company_timesheets(self, company_name, token, year, month):
        """Sync timesheets for a single company."""
        client = SincronClient(token)
        try:
            all_employees = client.get_all_timesheets(month, year)
        finally:
            client.close()

        employees_synced = 0
        records_created = 0
        discovered_codes = set()

        for emp in all_employees:
            sincron_id = str(emp.get('id_angajat', ''))
            if not sincron_id:
                continue

            # Handle invalid dates from API (e.g. "0000-00-00")
            contract_date = emp.get('data_incepere_contract')
            if contract_date in ('0000-00-00', '', None):
                contract_date = None

            # Upsert employee
            self.repo.upsert_employee(
                sincron_employee_id=sincron_id,
                company_name=company_name,
                nume=emp.get('nume', ''),
                prenume=emp.get('prenume', ''),
                cnp=emp.get('cnp'),
                id_contract=str(emp.get('id_contract', '')),
                nr_contract=str(emp.get('nr_contract', '')),
                data_incepere_contract=contract_date,
            )
            employees_synced += 1

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
        }

    # ── Auto-mapping ──

    def auto_map_employees(self):
        """Auto-map unmapped Sincron employees to JARVIS users.

        Strategy: CNP match first (highest confidence), then name match.
        """
        cnp_mapped = self.repo.auto_map_by_cnp()
        name_mapped = self.repo.auto_map_by_name()
        return {
            'success': True,
            'cnp_mapped': cnp_mapped,
            'name_mapped': name_mapped,
            'total_mapped': cnp_mapped + name_mapped,
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
        rows = self.repo.get_timesheet_by_jarvis_user(jarvis_user_id, year, month)
        if not rows:
            return {'days': {}, 'summary': [], 'employee': None}

        # Get employee info
        employee = self.repo.get_employee_by_jarvis_id(jarvis_user_id)

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

        # Group by user
        by_user = {}
        for row in rows:
            uid = row['mapped_jarvis_user_id']
            if uid not in by_user:
                by_user[uid] = {
                    'user_id': uid,
                    'name': row['employee_name'],
                    'company': row['company_name'],
                    'codes': {},
                    'total_hours': 0,
                }
            code = row['short_code']
            val = float(row['total_value'])
            by_user[uid]['codes'][code] = {
                'value': val,
                'unit': row['unit'],
                'days': row['day_count'],
            }
            if row['unit'] == 'hour':
                by_user[uid]['total_hours'] += val

        return list(by_user.values())

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
