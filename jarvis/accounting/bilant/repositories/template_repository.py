"""Repository for bilant_templates, bilant_template_rows, bilant_metric_configs."""

from core.base_repository import BaseRepository


class BilantTemplateRepository(BaseRepository):

    # ── Templates ──

    def get_by_id(self, template_id):
        return self.query_one('''
            SELECT t.*, c.company as company_name,
                   u.email as created_by_email
            FROM bilant_templates t
            LEFT JOIN companies c ON c.id = t.company_id
            LEFT JOIN users u ON u.id = t.created_by
            WHERE t.id = %s AND t.deleted_at IS NULL
        ''', (template_id,))

    def list_templates(self, company_id=None, include_global=True):
        where = ['t.deleted_at IS NULL']
        params = []
        if company_id and include_global:
            where.append('(t.company_id = %s OR t.company_id IS NULL)')
            params.append(company_id)
        elif company_id:
            where.append('t.company_id = %s')
            params.append(company_id)
        return self.query_all(f'''
            SELECT t.*, c.company as company_name,
                   (SELECT COUNT(*) FROM bilant_template_rows r WHERE r.template_id = t.id) as row_count
            FROM bilant_templates t
            LEFT JOIN companies c ON c.id = t.company_id
            WHERE {' AND '.join(where)}
            ORDER BY t.is_default DESC, t.name
        ''', params)

    def create(self, name, created_by, company_id=None, description=None):
        row = self.execute('''
            INSERT INTO bilant_templates (name, description, company_id, created_by)
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (name, description, company_id, created_by), returning=True)
        return row['id']

    def update(self, template_id, **kwargs):
        sets = []
        params = []
        for key in ('name', 'description', 'company_id', 'is_default'):
            if key in kwargs:
                sets.append(f"{key} = %s")
                params.append(kwargs[key])
        if not sets:
            return 0
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(template_id)
        return self.execute(
            f"UPDATE bilant_templates SET {', '.join(sets)} WHERE id = %s AND deleted_at IS NULL",
            params
        )

    def soft_delete(self, template_id):
        return self.execute(
            "UPDATE bilant_templates SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s",
            (template_id,)
        )

    def duplicate(self, template_id, new_name, created_by):
        """Deep copy template with all rows and metric configs."""
        def _work(cursor):
            # Copy template
            cursor.execute('''
                INSERT INTO bilant_templates (name, description, company_id, is_default, created_by)
                SELECT %s, description, company_id, FALSE, %s
                FROM bilant_templates WHERE id = %s
                RETURNING id
            ''', (new_name, created_by, template_id))
            new_id = cursor.fetchone()['id']
            # Copy rows
            cursor.execute('''
                INSERT INTO bilant_template_rows
                    (template_id, description, nr_rd, formula_ct, formula_rd, row_type, is_bold, indent_level, sort_order)
                SELECT %s, description, nr_rd, formula_ct, formula_rd, row_type, is_bold, indent_level, sort_order
                FROM bilant_template_rows WHERE template_id = %s
                ORDER BY sort_order
            ''', (new_id, template_id))
            # Copy metric configs
            cursor.execute('''
                INSERT INTO bilant_metric_configs
                    (template_id, metric_key, metric_label, nr_rd, metric_group, sort_order,
                     formula_expr, display_format, interpretation, threshold_good, threshold_warning, structure_side)
                SELECT %s, metric_key, metric_label, nr_rd, metric_group, sort_order,
                       formula_expr, display_format, interpretation, threshold_good, threshold_warning, structure_side
                FROM bilant_metric_configs WHERE template_id = %s
            ''', (new_id, template_id))
            return new_id
        return self.execute_many(_work)

    # ── Template Rows ──

    def get_rows(self, template_id):
        return self.query_all('''
            SELECT * FROM bilant_template_rows
            WHERE template_id = %s ORDER BY sort_order
        ''', (template_id,))

    def add_row(self, template_id, description, nr_rd=None, formula_ct=None,
                formula_rd=None, row_type='data', is_bold=False, indent_level=0, sort_order=0):
        row = self.execute('''
            INSERT INTO bilant_template_rows
                (template_id, description, nr_rd, formula_ct, formula_rd, row_type, is_bold, indent_level, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (template_id, description, nr_rd, formula_ct, formula_rd,
              row_type, is_bold, indent_level, sort_order), returning=True)
        return row['id']

    def update_row(self, row_id, **kwargs):
        sets = []
        params = []
        for key in ('description', 'nr_rd', 'formula_ct', 'formula_rd',
                     'row_type', 'is_bold', 'indent_level', 'sort_order'):
            if key in kwargs:
                sets.append(f"{key} = %s")
                params.append(kwargs[key])
        if not sets:
            return 0
        params.append(row_id)
        return self.execute(
            f"UPDATE bilant_template_rows SET {', '.join(sets)} WHERE id = %s",
            params
        )

    def delete_row(self, row_id):
        return self.execute("DELETE FROM bilant_template_rows WHERE id = %s", (row_id,))

    def reorder_rows(self, template_id, row_ids):
        """Batch update sort_order based on position in row_ids list."""
        def _work(cursor):
            for i, rid in enumerate(row_ids):
                cursor.execute(
                    "UPDATE bilant_template_rows SET sort_order = %s WHERE id = %s AND template_id = %s",
                    (i, rid, template_id)
                )
            return len(row_ids)
        return self.execute_many(_work)

    def bulk_add_rows(self, template_id, rows):
        """Bulk insert rows from import. rows = list of dicts."""
        def _work(cursor):
            for r in rows:
                cursor.execute('''
                    INSERT INTO bilant_template_rows
                        (template_id, description, nr_rd, formula_ct, formula_rd, row_type, is_bold, indent_level, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (template_id, r['description'], r.get('nr_rd'), r.get('formula_ct'),
                      r.get('formula_rd'), r.get('row_type', 'data'), r.get('is_bold', False),
                      r.get('indent_level', 0), r.get('sort_order', 0)))
            return len(rows)
        return self.execute_many(_work)

    # ── Metric Configs ──

    def get_metric_configs(self, template_id):
        return self.query_all('''
            SELECT * FROM bilant_metric_configs
            WHERE template_id = %s ORDER BY sort_order
        ''', (template_id,))

    def set_metric_config(self, template_id, metric_key, metric_label, nr_rd=None,
                          metric_group='summary', sort_order=0, formula_expr=None,
                          display_format='currency', interpretation=None,
                          threshold_good=None, threshold_warning=None, structure_side=None):
        row = self.execute('''
            INSERT INTO bilant_metric_configs
                (template_id, metric_key, metric_label, nr_rd, metric_group, sort_order,
                 formula_expr, display_format, interpretation, threshold_good, threshold_warning, structure_side)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (template_id, metric_key) DO UPDATE
                SET metric_label = EXCLUDED.metric_label,
                    nr_rd = EXCLUDED.nr_rd,
                    metric_group = EXCLUDED.metric_group,
                    sort_order = EXCLUDED.sort_order,
                    formula_expr = EXCLUDED.formula_expr,
                    display_format = EXCLUDED.display_format,
                    interpretation = EXCLUDED.interpretation,
                    threshold_good = EXCLUDED.threshold_good,
                    threshold_warning = EXCLUDED.threshold_warning,
                    structure_side = EXCLUDED.structure_side
            RETURNING id
        ''', (template_id, metric_key, metric_label, nr_rd, metric_group, sort_order,
              formula_expr, display_format, interpretation, threshold_good, threshold_warning,
              structure_side), returning=True)
        return row['id']

    def delete_metric_config(self, config_id):
        return self.execute("DELETE FROM bilant_metric_configs WHERE id = %s", (config_id,))

    def bulk_set_metric_configs(self, template_id, configs):
        """Bulk upsert metric configs. configs = list of dicts."""
        def _work(cursor):
            for c in configs:
                cursor.execute('''
                    INSERT INTO bilant_metric_configs
                        (template_id, metric_key, metric_label, nr_rd, metric_group, sort_order,
                         formula_expr, display_format, interpretation, threshold_good, threshold_warning, structure_side)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (template_id, metric_key) DO UPDATE
                        SET metric_label = EXCLUDED.metric_label,
                            nr_rd = EXCLUDED.nr_rd,
                            metric_group = EXCLUDED.metric_group,
                            sort_order = EXCLUDED.sort_order,
                            formula_expr = EXCLUDED.formula_expr,
                            display_format = EXCLUDED.display_format,
                            interpretation = EXCLUDED.interpretation,
                            threshold_good = EXCLUDED.threshold_good,
                            threshold_warning = EXCLUDED.threshold_warning,
                            structure_side = EXCLUDED.structure_side
                ''', (template_id, c['metric_key'], c['metric_label'], c.get('nr_rd'),
                      c.get('metric_group', 'summary'), c.get('sort_order', 0),
                      c.get('formula_expr'), c.get('display_format', 'currency'),
                      c.get('interpretation'), c.get('threshold_good'), c.get('threshold_warning'),
                      c.get('structure_side')))
            return len(configs)
        return self.execute_many(_work)
