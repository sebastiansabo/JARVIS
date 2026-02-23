"""Repository for bilant_generations, bilant_results, bilant_metrics."""

from core.base_repository import BaseRepository


class BilantGenerationRepository(BaseRepository):

    # ── Generations ──

    def get_by_id(self, generation_id):
        return self.query_one('''
            SELECT g.*, c.company as company_name,
                   t.name as template_name,
                   u.email as generated_by_email,
                   u.first_name || ' ' || u.last_name as generated_by_name
            FROM bilant_generations g
            JOIN companies c ON c.id = g.company_id
            JOIN bilant_templates t ON t.id = g.template_id
            JOIN users u ON u.id = g.generated_by
            WHERE g.id = %s
        ''', (generation_id,))

    def list_generations(self, company_id=None, limit=50, offset=0):
        where = ['1=1']
        params = []
        if company_id:
            where.append('g.company_id = %s')
            params.append(company_id)
        count_sql = f"SELECT COUNT(*) as total FROM bilant_generations g WHERE {' AND '.join(where)}"
        count_row = self.query_one(count_sql, params)
        total = count_row['total'] if count_row else 0

        params.extend([limit, offset])
        rows = self.query_all(f'''
            SELECT g.*, c.company as company_name,
                   t.name as template_name,
                   u.first_name || ' ' || u.last_name as generated_by_name
            FROM bilant_generations g
            JOIN companies c ON c.id = g.company_id
            JOIN bilant_templates t ON t.id = g.template_id
            JOIN users u ON u.id = g.generated_by
            WHERE {' AND '.join(where[:])}
            ORDER BY g.created_at DESC
            LIMIT %s OFFSET %s
        ''', params)
        return rows, total

    def create(self, template_id, company_id, generated_by, period_label=None,
               period_date=None, original_filename=None):
        row = self.execute('''
            INSERT INTO bilant_generations
                (template_id, company_id, period_label, period_date, generated_by, original_filename, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'processing') RETURNING id
        ''', (template_id, company_id, period_label, period_date, generated_by, original_filename),
            returning=True)
        return row['id']

    def update_status(self, generation_id, status, error_message=None):
        return self.execute('''
            UPDATE bilant_generations
            SET status = %s, error_message = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (status, error_message, generation_id))

    def update_notes(self, generation_id, notes):
        return self.execute(
            "UPDATE bilant_generations SET notes = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (notes, generation_id)
        )

    def delete_generation(self, generation_id):
        return self.execute("DELETE FROM bilant_generations WHERE id = %s", (generation_id,))

    def get_latest_by_company(self, company_id):
        return self.query_one('''
            SELECT g.*, t.name as template_name
            FROM bilant_generations g
            JOIN bilant_templates t ON t.id = g.template_id
            WHERE g.company_id = %s AND g.status = 'completed'
            ORDER BY g.created_at DESC LIMIT 1
        ''', (company_id,))

    # ── Results ──

    def save_results(self, generation_id, results):
        """Batch insert row results."""
        def _work(cursor):
            for r in results:
                cursor.execute('''
                    INSERT INTO bilant_results
                        (generation_id, template_row_id, nr_rd, description,
                         formula_ct, formula_rd, value, verification, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (generation_id, r.get('template_row_id'), r.get('nr_rd'),
                      r.get('description'), r.get('formula_ct'), r.get('formula_rd'),
                      r.get('value', 0), r.get('verification'), r.get('sort_order', 0)))
            return len(results)
        return self.execute_many(_work)

    def get_results(self, generation_id):
        return self.query_all('''
            SELECT r.*, tr.row_type, tr.is_bold, tr.indent_level
            FROM bilant_results r
            LEFT JOIN bilant_template_rows tr ON tr.id = r.template_row_id
            WHERE r.generation_id = %s
            ORDER BY r.sort_order
        ''', (generation_id,))

    # ── Metrics ──

    def save_metrics(self, generation_id, metrics_dict):
        """Save computed metrics (summary + ratios + structure) to DB."""
        def _work(cursor):
            count = 0
            # Summary
            for key, val in metrics_dict.get('summary', {}).items():
                cursor.execute('''
                    INSERT INTO bilant_metrics
                        (generation_id, metric_key, metric_label, metric_group, value)
                    VALUES (%s, %s, %s, 'summary', %s)
                    ON CONFLICT (generation_id, metric_key) DO UPDATE
                        SET value = EXCLUDED.value
                ''', (generation_id, key, key.replace('_', ' ').title(), val))
                count += 1

            # Ratios
            from accounting.bilant.formula_engine import STANDARD_RATIOS
            for key, val in metrics_dict.get('ratios', {}).items():
                spec = STANDARD_RATIOS.get(key, {})
                cursor.execute('''
                    INSERT INTO bilant_metrics
                        (generation_id, metric_key, metric_label, metric_group, value, interpretation)
                    VALUES (%s, %s, %s, 'ratio', %s, %s)
                    ON CONFLICT (generation_id, metric_key) DO UPDATE
                        SET value = EXCLUDED.value, interpretation = EXCLUDED.interpretation
                ''', (generation_id, key, spec.get('label', key), val, spec.get('interpretation')))
                count += 1

            # Structure
            for group_key, items in metrics_dict.get('structure', {}).items():
                mg = 'structure_assets' if group_key == 'assets' else 'structure_liabilities'
                for item in items:
                    mk = f"{mg}_{item['name'].lower().replace(' ', '_').replace('<', 'lt').replace('>', 'gt')}"
                    cursor.execute('''
                        INSERT INTO bilant_metrics
                            (generation_id, metric_key, metric_label, metric_group, value, percent)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (generation_id, metric_key) DO UPDATE
                            SET value = EXCLUDED.value, percent = EXCLUDED.percent
                    ''', (generation_id, mk, item['name'], mg, item['value'], item['percent']))
                    count += 1
            return count
        return self.execute_many(_work)

    def get_metrics(self, generation_id):
        return self.query_all('''
            SELECT * FROM bilant_metrics
            WHERE generation_id = %s
            ORDER BY metric_group, metric_key
        ''', (generation_id,))

    def get_metrics_for_comparison(self, generation_ids):
        """Get metrics for multiple generations, for period comparison."""
        if not generation_ids:
            return []
        placeholders = ','.join(['%s'] * len(generation_ids))
        return self.query_all(f'''
            SELECT m.*, g.period_label, g.period_date, g.company_id
            FROM bilant_metrics m
            JOIN bilant_generations g ON g.id = m.generation_id
            WHERE m.generation_id IN ({placeholders})
            ORDER BY g.period_date, m.metric_group, m.metric_key
        ''', generation_ids)
