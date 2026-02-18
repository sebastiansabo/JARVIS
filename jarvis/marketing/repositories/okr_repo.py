"""Repository for mkt_objectives and mkt_key_results tables."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.okr_repo')


class OkrRepository(BaseRepository):

    def get_by_project(self, project_id):
        """Get all objectives with nested key_results and computed progress."""
        def _work(cursor):
            cursor.execute('''
                SELECT * FROM mkt_objectives
                WHERE project_id = %s
                ORDER BY sort_order, id
            ''', (project_id,))
            objectives = [dict(r) for r in cursor.fetchall()]
            if not objectives:
                return []

            obj_ids = [o['id'] for o in objectives]
            cursor.execute('''
                SELECT kr.*,
                       kd.name as linked_kpi_name
                FROM mkt_key_results kr
                LEFT JOIN mkt_project_kpis pk ON kr.linked_kpi_id = pk.id
                LEFT JOIN mkt_kpi_definitions kd ON pk.kpi_definition_id = kd.id
                WHERE kr.objective_id = ANY(%s)
                ORDER BY kr.sort_order, kr.id
            ''', (obj_ids,))
            krs = [dict(r) for r in cursor.fetchall()]

            kr_by_obj = {}
            for kr in krs:
                target = float(kr['target_value'] or 0)
                current = float(kr['current_value'] or 0)
                kr['progress'] = round(min(current / target * 100, 100), 1) if target > 0 else 0
                kr_by_obj.setdefault(kr['objective_id'], []).append(kr)

            for obj in objectives:
                obj['key_results'] = kr_by_obj.get(obj['id'], [])
                if obj['key_results']:
                    obj['progress'] = round(
                        sum(kr['progress'] for kr in obj['key_results']) / len(obj['key_results']), 1
                    )
                else:
                    obj['progress'] = 0

            return objectives
        return self.execute_many(_work)

    def create_objective(self, project_id, title, created_by, description=None, sort_order=0):
        row = self.execute('''
            INSERT INTO mkt_objectives (project_id, title, description, sort_order, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (project_id, title, description, sort_order, created_by), returning=True)
        return row['id'] if row else None

    def update_objective(self, objective_id, **kwargs):
        allowed = {'title', 'description', 'sort_order'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed and val is not None:
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False
        updates.append('updated_at = NOW()')
        params.append(objective_id)
        return self.execute(
            f'UPDATE mkt_objectives SET {", ".join(updates)} WHERE id = %s', params
        ) > 0

    def delete_objective(self, objective_id):
        return self.execute(
            'DELETE FROM mkt_objectives WHERE id = %s', (objective_id,)
        ) > 0

    def create_key_result(self, objective_id, title, target_value=100, unit='number',
                          linked_kpi_id=None, sort_order=0):
        def _work(cursor):
            current_value = 0
            if linked_kpi_id:
                cursor.execute(
                    'SELECT current_value FROM mkt_project_kpis WHERE id = %s',
                    (linked_kpi_id,)
                )
                row = cursor.fetchone()
                if row:
                    current_value = float(row['current_value'] or 0)
            cursor.execute('''
                INSERT INTO mkt_key_results
                    (objective_id, title, target_value, current_value, unit, linked_kpi_id, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (objective_id, title, target_value, current_value, unit, linked_kpi_id, sort_order))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def update_key_result(self, kr_id, **kwargs):
        allowed = {'title', 'target_value', 'current_value', 'unit', 'linked_kpi_id', 'sort_order'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False

        def _work(cursor):
            # If linking to a KPI, sync its current value
            if 'linked_kpi_id' in kwargs and kwargs['linked_kpi_id']:
                cursor.execute(
                    'SELECT current_value FROM mkt_project_kpis WHERE id = %s',
                    (kwargs['linked_kpi_id'],)
                )
                row = cursor.fetchone()
                if row:
                    updates.append('current_value = %s')
                    params.append(float(row['current_value'] or 0))
            updates.append('updated_at = NOW()')
            params.append(kr_id)
            cursor.execute(
                f'UPDATE mkt_key_results SET {", ".join(updates)} WHERE id = %s',
                params
            )
            return cursor.rowcount > 0
        return self.execute_many(_work)

    def delete_key_result(self, kr_id):
        return self.execute(
            'DELETE FROM mkt_key_results WHERE id = %s', (kr_id,)
        ) > 0

    def sync_linked_kpis(self, project_id):
        """Copy current_value from linked KPIs to key results for a project."""
        return self.execute('''
            UPDATE mkt_key_results kr
            SET current_value = pk.current_value, updated_at = NOW()
            FROM mkt_project_kpis pk, mkt_objectives o
            WHERE kr.linked_kpi_id = pk.id
              AND kr.objective_id = o.id
              AND o.project_id = %s
              AND kr.linked_kpi_id IS NOT NULL
        ''', (project_id,))
