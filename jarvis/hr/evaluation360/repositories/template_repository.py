"""Competency-library + form-template persistence.

Two roles:
  * reads that render a reviewer's form (`list_questions`), and
  * the HR authoring surface — competency CRUD, versioned templates with
    fork-on-edit, and the question blocks that make a template renderable.

Templates are immutable once `published` (spec §3): the service forks a new
draft version rather than mutating one in place, so cycles that reference an
older version keep a stable form.
"""
import json

from core.base_repository import BaseRepository


class EvalTemplateRepository(BaseRepository):

    # ── form rendering ───────────────────────────────────────────────
    def get_template(self, template_id):
        return self.query_one(
            'SELECT * FROM eval_form_templates WHERE id = %s', (template_id,))

    def list_questions(self, template_id):
        """Question blocks for a template, in display order, joined to their
        competency name."""
        return self.query_all(
            '''SELECT q.*, c.name AS competency_name, c.cluster AS competency_cluster,
                      c.definition AS competency_definition,
                      c.level_descriptors AS competency_level_descriptors
               FROM eval_question_blocks q
               LEFT JOIN eval_competencies c ON c.id = q.competency_id
               WHERE q.template_id = %s
               ORDER BY q.sort_order, q.id''',
            (template_id,))

    # ── competency library ───────────────────────────────────────────
    def list_competencies(self, include_inactive=False):
        where = 'deleted_at IS NULL' if include_inactive else 'deleted_at IS NULL AND is_active = TRUE'
        return self.query_all(
            f'''SELECT c.*,
                       (SELECT COUNT(*) FROM eval_question_blocks q WHERE q.competency_id = c.id) AS usage_count
                FROM eval_competencies c
                WHERE {where}
                ORDER BY c.cluster NULLS LAST, c.name''')

    def get_competency(self, cid):
        return self.query_one('SELECT * FROM eval_competencies WHERE id = %s', (cid,))

    def create_competency(self, *, name, definition=None, cluster=None,
                          level_descriptors=None, created_by=None):
        return self.execute(
            '''INSERT INTO eval_competencies (name, definition, cluster, level_descriptors, created_by)
               VALUES (%s,%s,%s,%s::jsonb,%s) RETURNING *''',
            (name, definition, cluster, json.dumps(level_descriptors or {}), created_by),
            returning=True)

    def update_competency(self, cid, fields):
        cur = self.get_competency(cid)
        if not cur:
            return None
        level = fields.get('level_descriptors', cur.get('level_descriptors'))
        return self.execute(
            '''UPDATE eval_competencies
               SET name = %s, definition = %s, cluster = %s, is_active = %s,
                   level_descriptors = %s::jsonb, updated_at = CURRENT_TIMESTAMP
               WHERE id = %s RETURNING *''',
            (fields.get('name', cur['name']),
             fields.get('definition', cur['definition']),
             fields.get('cluster', cur['cluster']),
             fields.get('is_active', cur['is_active']),
             json.dumps(level if level is not None else {}),
             cid), returning=True)

    # ── templates ────────────────────────────────────────────────────
    def list_templates(self, include_archived=False):
        where = "t.deleted_at IS NULL" if include_archived else "t.deleted_at IS NULL AND t.status <> 'archived'"
        return self.query_all(
            f'''SELECT t.*,
                       (SELECT COUNT(*) FROM eval_question_blocks q WHERE q.template_id = t.id) AS question_count,
                       (SELECT COUNT(*) FROM eval_cycles c WHERE c.template_id = t.id) AS cycle_count
                FROM eval_form_templates t
                WHERE {where}
                ORDER BY t.name, t.version DESC''')

    def max_version(self, name):
        row = self.query_one(
            'SELECT MAX(version) AS v FROM eval_form_templates WHERE name = %s', (name,))
        return (row or {}).get('v') or 0

    def create_template(self, *, name, competency_ids=None, rating_scale=None,
                        created_by=None, version=1, forked_from_id=None, status='draft'):
        cols = ['name', 'version', 'forked_from_id', 'competency_ids', 'status', 'created_by']
        vals = [name, version, forked_from_id, competency_ids or [], status, created_by]
        if rating_scale is not None:
            cols.append('rating_scale')
            vals.append(json.dumps(rating_scale))
        placeholders = ','.join(['%s'] * len(vals))
        return self.execute(
            f'INSERT INTO eval_form_templates ({",".join(cols)}) VALUES ({placeholders}) RETURNING *',
            tuple(vals), returning=True)

    def set_template_meta(self, template_id, *, name=None, competency_ids=None):
        cur = self.get_template(template_id)
        if not cur:
            return None
        return self.execute(
            'UPDATE eval_form_templates SET name = %s, competency_ids = %s WHERE id = %s RETURNING *',
            (name if name is not None else cur['name'],
             competency_ids if competency_ids is not None else cur['competency_ids'],
             template_id), returning=True)

    def set_template_status(self, template_id, status):
        return self.execute(
            'UPDATE eval_form_templates SET status = %s WHERE id = %s RETURNING *',
            (status, template_id), returning=True)

    def soft_delete_template(self, template_id):
        return self.execute(
            'UPDATE eval_form_templates SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s',
            (template_id,))

    # ── question blocks (atomic replace-all for a draft) ─────────────
    def replace_questions(self, template_id, questions):
        """Swap the whole question set of a (draft) template in one transaction,
        so a half-written form is never observable. Returns the new blocks."""
        rows = [
            (template_id, q.get('competency_id'), q.get('type', 'rating'),
             json.dumps(q.get('text_by_audience') or {}),
             bool(q.get('required', True)), i)
            for i, q in enumerate(questions)
        ]

        def _work(cursor):
            cursor.execute('DELETE FROM eval_question_blocks WHERE template_id = %s', (template_id,))
            for r in rows:
                cursor.execute(
                    '''INSERT INTO eval_question_blocks
                         (template_id, competency_id, type, text_by_audience, required, sort_order)
                       VALUES (%s,%s,%s,%s,%s,%s)''',
                    r)
            return cursor.rowcount

        self.execute_many(_work)
        return self.list_questions(template_id)

    def copy_questions(self, from_template_id, to_template_id):
        """Duplicate every question block from one template onto another (used by
        fork). Single transaction."""
        def _work(cursor):
            cursor.execute(
                '''INSERT INTO eval_question_blocks
                     (template_id, competency_id, type, text_by_audience, required, sort_order)
                   SELECT %s, competency_id, type, text_by_audience, required, sort_order
                   FROM eval_question_blocks WHERE template_id = %s''',
                (to_template_id, from_template_id))
            return cursor.rowcount

        return self.execute_many(_work)
