"""Repository for mkt_kpi_definitions, mkt_project_kpis, mkt_kpi_snapshots."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.kpi_repo')


class KpiRepository(BaseRepository):

    # ---- KPI Definitions (admin catalog) ----

    def get_definitions(self, active_only=True):
        where = 'WHERE is_active = TRUE' if active_only else ''
        return self.query_all(
            f'SELECT * FROM mkt_kpi_definitions {where} ORDER BY sort_order'
        )

    def create_definition(self, name, slug, unit='number', direction='higher',
                          category='performance', formula=None, description=None):
        # Auto-resolve slug collisions by appending numeric suffix
        base_slug = slug
        counter = 1
        while True:
            existing = self.query_one(
                'SELECT 1 FROM mkt_kpi_definitions WHERE slug = %s', (slug,)
            )
            if not existing:
                break
            slug = f'{base_slug}_{counter}'
            counter += 1
        row = self.execute('''
            INSERT INTO mkt_kpi_definitions (name, slug, unit, direction, category, formula, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (name, slug, unit, direction, category, formula, description), returning=True)
        return row['id'] if row else None

    def update_definition(self, def_id, **kwargs):
        from psycopg2.extras import Json
        allowed = {'name', 'slug', 'unit', 'direction', 'category', 'formula', 'description', 'benchmarks', 'is_active', 'sort_order'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed and val is not None:
                updates.append(f'{key} = %s')
                params.append(Json(val) if key == 'benchmarks' and isinstance(val, dict) else val)
        if not updates:
            return False
        params.append(def_id)
        return self.execute(
            f'UPDATE mkt_kpi_definitions SET {", ".join(updates)} WHERE id = %s', params
        ) > 0

    # ---- Project KPIs ----

    def get_by_project(self, project_id):
        return self.query_all('''
            SELECT pk.*, kd.name as kpi_name, kd.slug as kpi_slug,
                   kd.unit, kd.direction, kd.category, kd.formula,
                   (SELECT ROUND(AVG(s.value)::numeric, 4) FROM mkt_kpi_snapshots s
                    WHERE s.project_kpi_id = pk.id) as average_value,
                   (SELECT ROUND(SUM(s.value)::numeric, 4) FROM mkt_kpi_snapshots s
                    WHERE s.project_kpi_id = pk.id) as cumulative_value,
                   (SELECT s.value FROM mkt_kpi_snapshots s
                    WHERE s.project_kpi_id = pk.id
                    ORDER BY s.recorded_at DESC LIMIT 1) as latest_value
            FROM mkt_project_kpis pk
            JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
            WHERE pk.project_id = %s
            ORDER BY kd.sort_order
        ''', (project_id,))

    def add_project_kpi(self, project_id, kpi_definition_id, **kwargs):
        row = self.execute('''
            INSERT INTO mkt_project_kpis
                (project_id, kpi_definition_id, channel, target_value, weight,
                 threshold_warning, threshold_critical, currency, notes, show_on_overview, aggregation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            project_id, kpi_definition_id,
            kwargs.get('channel'), kwargs.get('target_value'),
            kwargs.get('weight', 50),
            kwargs.get('threshold_warning'), kwargs.get('threshold_critical'),
            kwargs.get('currency', 'RON'),
            kwargs.get('notes'),
            kwargs.get('show_on_overview', False),
            kwargs.get('aggregation', 'latest'),
        ), returning=True)
        return row['id'] if row else None

    def update_project_kpi(self, kpi_id, **kwargs):
        allowed = {'target_value', 'current_value', 'weight', 'threshold_warning',
                    'threshold_critical', 'status', 'notes', 'channel', 'currency',
                    'show_on_overview', 'aggregation'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False
        updates.append('updated_at = NOW()')
        params.append(kpi_id)
        return self.execute(
            f'UPDATE mkt_project_kpis SET {", ".join(updates)} WHERE id = %s', params
        ) > 0

    def delete_project_kpi(self, kpi_id):
        # Get the definition id before deleting
        row = self.query_one(
            'SELECT kpi_definition_id FROM mkt_project_kpis WHERE id = %s', (kpi_id,)
        )
        deleted = self.execute(
            'DELETE FROM mkt_project_kpis WHERE id = %s', (kpi_id,)
        ) > 0
        # Clean up orphan custom definitions (no other project uses it)
        if deleted and row:
            def_id = row['kpi_definition_id']
            still_used = self.query_one(
                'SELECT 1 FROM mkt_project_kpis WHERE kpi_definition_id = %s', (def_id,)
            )
            if not still_used:
                self.execute(
                    'DELETE FROM mkt_kpi_definitions WHERE id = %s', (def_id,)
                )
        return deleted

    # ---- KPI ↔ Budget Line linking ----

    def get_kpi_budget_lines(self, project_kpi_id):
        return self.query_all('''
            SELECT kb.id, kb.project_kpi_id, kb.budget_line_id, kb.role, kb.created_at,
                   bl.channel, bl.description, bl.planned_amount,
                   bl.spent_amount, bl.currency
            FROM mkt_kpi_budget_lines kb
            JOIN mkt_budget_lines bl ON bl.id = kb.budget_line_id
            WHERE kb.project_kpi_id = %s
            ORDER BY kb.role, bl.channel
        ''', (project_kpi_id,))

    def link_budget_line(self, project_kpi_id, budget_line_id, role='input'):
        # ON CONFLICT DO UPDATE always returns a row
        row = self.execute('''
            INSERT INTO mkt_kpi_budget_lines (project_kpi_id, budget_line_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (project_kpi_id, budget_line_id) DO UPDATE SET role = EXCLUDED.role
            RETURNING id
        ''', (project_kpi_id, budget_line_id, role), returning=True)
        return row['id'] if row else None

    def unlink_budget_line(self, project_kpi_id, budget_line_id):
        return self.execute('''
            DELETE FROM mkt_kpi_budget_lines
            WHERE project_kpi_id = %s AND budget_line_id = %s
        ''', (project_kpi_id, budget_line_id)) > 0

    # ---- KPI ↔ KPI dependencies ----

    def get_kpi_dependencies(self, project_kpi_id):
        return self.query_all('''
            SELECT kd.id, kd.project_kpi_id, kd.depends_on_kpi_id, kd.role, kd.created_at,
                   pk.current_value as dep_current_value,
                   kdef.name as dep_kpi_name, kdef.slug as dep_kpi_slug,
                   kdef.unit as dep_unit
            FROM mkt_kpi_dependencies kd
            JOIN mkt_project_kpis pk ON pk.id = kd.depends_on_kpi_id
            JOIN mkt_kpi_definitions kdef ON kdef.id = pk.kpi_definition_id
            WHERE kd.project_kpi_id = %s
            ORDER BY kd.role, kdef.name
        ''', (project_kpi_id,))

    def link_kpi_dependency(self, project_kpi_id, depends_on_kpi_id, role='input'):
        # ON CONFLICT DO UPDATE always returns a row
        row = self.execute('''
            INSERT INTO mkt_kpi_dependencies (project_kpi_id, depends_on_kpi_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (project_kpi_id, depends_on_kpi_id) DO UPDATE SET role = EXCLUDED.role
            RETURNING id
        ''', (project_kpi_id, depends_on_kpi_id, role), returning=True)
        return row['id'] if row else None

    def unlink_kpi_dependency(self, project_kpi_id, depends_on_kpi_id):
        return self.execute('''
            DELETE FROM mkt_kpi_dependencies
            WHERE project_kpi_id = %s AND depends_on_kpi_id = %s
        ''', (project_kpi_id, depends_on_kpi_id)) > 0

    # ---- KPI ↔ Deal Sources ----

    def get_kpi_deal_sources(self, project_kpi_id):
        return self.query_all('''
            SELECT * FROM mkt_kpi_deal_sources
            WHERE project_kpi_id = %s
            ORDER BY role, metric
        ''', (project_kpi_id,))

    def link_deal_source(self, project_kpi_id, role='input', metric='count',
                         brand_filter=None, source_filter=None, status_filter=None,
                         date_from=None, date_to=None):
        row = self.execute('''
            INSERT INTO mkt_kpi_deal_sources
                (project_kpi_id, role, metric, brand_filter, source_filter,
                 status_filter, date_from, date_to)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (project_kpi_id, role, metric)
            DO UPDATE SET brand_filter = EXCLUDED.brand_filter,
                          source_filter = EXCLUDED.source_filter,
                          status_filter = EXCLUDED.status_filter,
                          date_from = EXCLUDED.date_from,
                          date_to = EXCLUDED.date_to
            RETURNING id
        ''', (project_kpi_id, role, metric, brand_filter, source_filter,
              status_filter, date_from, date_to), returning=True)
        return row['id'] if row else None

    def unlink_deal_source(self, project_kpi_id, deal_source_id):
        return self.execute('''
            DELETE FROM mkt_kpi_deal_sources
            WHERE id = %s AND project_kpi_id = %s
        ''', (deal_source_id, project_kpi_id)) > 0

    # ---- KPI ↔ Individual Deals ----

    def get_kpi_deals(self, project_kpi_id):
        """Get all individual deals linked to a KPI, with deal details."""
        return self.query_all('''
            SELECT kd.id, kd.project_kpi_id, kd.deal_id, kd.linked_by, kd.created_at,
                   d.source, d.brand, d.model_name, d.sale_price_net, d.gross_profit,
                   d.contract_date, d.dossier_status, d.sales_person, d.vin,
                   d.dealer_name, d.buyer_name,
                   u.name as linked_by_name
            FROM mkt_kpi_deals kd
            JOIN crm_deals d ON d.id = kd.deal_id
            LEFT JOIN users u ON u.id = kd.linked_by
            WHERE kd.project_kpi_id = %s
            ORDER BY d.contract_date DESC
        ''', (project_kpi_id,))

    def link_kpi_deal(self, project_kpi_id, deal_id, linked_by):
        """Link an individual deal to a KPI (each deal = +1 to current_value)."""
        row = self.execute('''
            INSERT INTO mkt_kpi_deals (project_kpi_id, deal_id, linked_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (project_kpi_id, deal_id) DO NOTHING
            RETURNING id
        ''', (project_kpi_id, deal_id, linked_by), returning=True)
        if row:
            self.execute('''
                UPDATE mkt_project_kpis
                SET current_value = COALESCE(current_value, 0) + 1, updated_at = NOW()
                WHERE id = %s
            ''', (project_kpi_id,))
        return row['id'] if row else None

    def unlink_kpi_deal(self, project_kpi_id, deal_link_id):
        """Unlink an individual deal from a KPI (each deal = -1 from current_value)."""
        deleted = self.execute('''
            DELETE FROM mkt_kpi_deals
            WHERE id = %s AND project_kpi_id = %s
        ''', (deal_link_id, project_kpi_id)) > 0
        if deleted:
            self.execute('''
                UPDATE mkt_project_kpis
                SET current_value = GREATEST(COALESCE(current_value, 0) - 1, 0), updated_at = NOW()
                WHERE id = %s
            ''', (project_kpi_id,))
        return deleted

    def get_available_deals(self, project_id, project_kpi_id):
        """Get deals from linked clients that aren't already linked to this KPI."""
        return self.query_all('''
            SELECT d.id, d.source, d.brand, d.model_name, d.sale_price_net,
                   d.gross_profit, d.contract_date, d.dossier_status,
                   d.sales_person, d.vin, d.buyer_name,
                   c.display_name as client_name
            FROM crm_deals d
            JOIN crm_clients c ON c.id = d.client_id
            JOIN mkt_project_clients pc ON pc.client_id = d.client_id AND pc.project_id = %s
            WHERE d.id NOT IN (
                SELECT deal_id FROM mkt_kpi_deals WHERE project_kpi_id = %s
            )
            ORDER BY d.contract_date DESC
        ''', (project_id, project_kpi_id))

    # ---- Sync / Recalculate ----

    def sync_kpi(self, project_kpi_id):
        """Recalculate current_value from linked sources using the KPI definition's formula.

        For formula KPIs (e.g. 'spent / leads'), evaluates the formula with variable values
        resolved from linked budget lines and KPI dependencies.
        For raw KPIs (no formula), sums all linked source values.
        """
        from marketing.services.formula_engine import evaluate as eval_formula

        def _work(cursor):
            # Get KPI's formula and current value from its definition
            cursor.execute('''
                SELECT pk.id, pk.current_value, kd.formula
                FROM mkt_project_kpis pk
                JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
                WHERE pk.id = %s
            ''', (project_kpi_id,))
            kpi_row = cursor.fetchone()
            if not kpi_row:
                return {'synced': False, 'reason': 'KPI not found'}
            formula = kpi_row['formula']
            old_value = float(kpi_row['current_value'] or 0)

            # Budget lines grouped by role (variable name)
            cursor.execute('''
                SELECT kb.role, COALESCE(SUM(bl.spent_amount), 0) as total
                FROM mkt_kpi_budget_lines kb
                JOIN mkt_budget_lines bl ON bl.id = kb.budget_line_id
                WHERE kb.project_kpi_id = %s
                GROUP BY kb.role
            ''', (project_kpi_id,))
            bl_by_role = {r['role']: float(r['total']) for r in cursor.fetchall()}

            # KPI dependencies grouped by role (variable name)
            cursor.execute('''
                SELECT kd.role, COALESCE(SUM(pk.current_value), 0) as total
                FROM mkt_kpi_dependencies kd
                JOIN mkt_project_kpis pk ON pk.id = kd.depends_on_kpi_id
                WHERE kd.project_kpi_id = %s
                GROUP BY kd.role
            ''', (project_kpi_id,))
            dep_by_role = {r['role']: float(r['total']) for r in cursor.fetchall()}

            # Deal sources grouped by role — aggregate CRM deals from linked clients
            deal_by_role = {}
            cursor.execute(
                'SELECT project_id FROM mkt_project_kpis WHERE id = %s',
                (project_kpi_id,)
            )
            proj_row = cursor.fetchone()
            if proj_row:
                cursor.execute(
                    'SELECT * FROM mkt_kpi_deal_sources WHERE project_kpi_id = %s',
                    (project_kpi_id,)
                )
                deal_sources = cursor.fetchall()
                if deal_sources:
                    cursor.execute(
                        'SELECT client_id FROM mkt_project_clients WHERE project_id = %s',
                        (proj_row['project_id'],)
                    )
                    client_ids = [r['client_id'] for r in cursor.fetchall()]
                    if client_ids:
                        agg_map = {
                            'count': 'COUNT(*)',
                            'sum_revenue': 'COALESCE(SUM(sale_price_net), 0)',
                            'sum_profit': 'COALESCE(SUM(gross_profit), 0)',
                            'avg_price': 'COALESCE(AVG(sale_price_net), 0)',
                        }
                        for ds in deal_sources:
                            agg_expr = agg_map.get(ds['metric'], 'COUNT(*)')
                            conditions = ['client_id IN %s']
                            params = [tuple(client_ids)]
                            if ds.get('brand_filter'):
                                conditions.append('brand ILIKE %s')
                                params.append(f'%{ds["brand_filter"]}%')
                            if ds.get('source_filter'):
                                conditions.append('source = %s')
                                params.append(ds['source_filter'])
                            if ds.get('status_filter'):
                                statuses = [s.strip() for s in ds['status_filter'].split(',')]
                                placeholders = ','.join(['%s'] * len(statuses))
                                conditions.append(f'dossier_status IN ({placeholders})')
                                params.extend(statuses)
                            if ds.get('date_from'):
                                conditions.append('contract_date >= %s')
                                params.append(ds['date_from'])
                            if ds.get('date_to'):
                                conditions.append('contract_date <= %s')
                                params.append(ds['date_to'])
                            where = ' AND '.join(conditions)
                            cursor.execute(
                                f'SELECT {agg_expr} as total FROM crm_deals WHERE {where}',
                                tuple(params)
                            )
                            val = float(cursor.fetchone()['total'] or 0)
                            role = ds['role']
                            deal_by_role[role] = deal_by_role.get(role, 0) + val

            # Individual deal links (each linked deal = 1 unit, counted into 'input')
            cursor.execute('''
                SELECT COUNT(*) as total FROM mkt_kpi_deals WHERE project_kpi_id = %s
            ''', (project_kpi_id,))
            individual_deal_count = int(cursor.fetchone()['total'])
            if individual_deal_count > 0:
                deal_by_role['input'] = deal_by_role.get('input', 0) + individual_deal_count

            has_sources = bool(bl_by_role) or bool(dep_by_role) or bool(deal_by_role)
            if not has_sources:
                return {'synced': False, 'reason': 'No linked sources'}

            # Merge variables from all sources (same variable name = summed)
            variables = {}
            for role in set(bl_by_role.keys()) | set(dep_by_role.keys()) | set(deal_by_role.keys()):
                variables[role] = (bl_by_role.get(role, 0)
                                   + dep_by_role.get(role, 0)
                                   + deal_by_role.get(role, 0))

            # Calculate
            if formula:
                try:
                    new_value = round(eval_formula(formula, variables), 4)
                except ZeroDivisionError:
                    logger.warning(f"KPI {project_kpi_id}: division by zero in '{formula}'")
                    new_value = 0
                except ValueError as e:
                    logger.warning(f"KPI {project_kpi_id}: formula error: {e}")
                    return {'synced': False, 'reason': f'Formula error: {e}'}
            else:
                # No formula = raw KPI, sum all inputs
                new_value = sum(variables.values())

            # Always update last_synced_at, but only create snapshot if value changed
            cursor.execute('''
                UPDATE mkt_project_kpis
                SET current_value = %s, last_synced_at = NOW(), updated_at = NOW()
                WHERE id = %s
            ''', (new_value, project_kpi_id))
            value_changed = round(old_value, 4) != round(new_value, 4)
            if value_changed:
                cursor.execute('''
                    INSERT INTO mkt_kpi_snapshots (project_kpi_id, value, source)
                    VALUES (%s, %s, 'auto')
                ''', (project_kpi_id, new_value))
            return {'synced': True, 'value': new_value, 'changed': value_changed}
        return self.execute_many(_work)

    def sync_all_project_kpis(self, project_id):
        """Sync all KPIs for a project that have linked sources. Returns count synced."""
        rows = self.query_all(
            'SELECT id FROM mkt_project_kpis WHERE project_id = %s', (project_id,)
        )
        kpi_ids = [r['id'] for r in rows]
        synced = 0
        for kpi_id in kpi_ids:
            try:
                result = self.sync_kpi(kpi_id)
                if result.get('synced'):
                    synced += 1
            except Exception as e:
                logger.warning(f"Failed to sync KPI {kpi_id}: {e}")
        return synced

    def get_all_syncable_kpi_ids(self):
        """Get all KPI IDs that have at least one linked source."""
        rows = self.query_all('''
            SELECT DISTINCT project_kpi_id FROM (
                SELECT project_kpi_id FROM mkt_kpi_budget_lines
                UNION
                SELECT project_kpi_id FROM mkt_kpi_dependencies
                UNION
                SELECT project_kpi_id FROM mkt_kpi_deal_sources
                UNION
                SELECT project_kpi_id FROM mkt_kpi_deals
            ) src
        ''')
        return [r['project_kpi_id'] for r in rows]

    # ---- Snapshots ----

    def get_snapshots(self, project_kpi_id, limit=50):
        return self.query_all('''
            SELECT s.*, u.name as recorded_by_name
            FROM mkt_kpi_snapshots s
            LEFT JOIN users u ON u.id = s.recorded_by
            WHERE s.project_kpi_id = %s
            ORDER BY s.recorded_at DESC
            LIMIT %s
        ''', (project_kpi_id, limit))

    def add_snapshot(self, project_kpi_id, value, recorded_by=None, source='manual', notes=None):
        def _work(cursor):
            cursor.execute('''
                INSERT INTO mkt_kpi_snapshots (project_kpi_id, value, source, recorded_by, notes)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            ''', (project_kpi_id, value, source, recorded_by, notes))
            snap_id = cursor.fetchone()['id']
            # Update current_value on project_kpi (cumulative — add to existing)
            cursor.execute('''
                UPDATE mkt_project_kpis SET current_value = COALESCE(current_value, 0) + %s, last_synced_at = NOW(), updated_at = NOW()
                WHERE id = %s
            ''', (value, project_kpi_id))
            return snap_id
        return self.execute_many(_work)
