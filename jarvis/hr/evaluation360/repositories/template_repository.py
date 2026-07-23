"""Form-template + competency reads (for rendering the reviewer's form)."""
from core.base_repository import BaseRepository


class EvalTemplateRepository(BaseRepository):

    def get_template(self, template_id):
        return self.query_one(
            'SELECT * FROM eval_form_templates WHERE id = %s', (template_id,))

    def list_questions(self, template_id):
        """Question blocks for a template, in display order, joined to their
        competency name."""
        return self.query_all(
            '''SELECT q.*, c.name AS competency_name, c.cluster AS competency_cluster
               FROM eval_question_blocks q
               LEFT JOIN eval_competencies c ON c.id = q.competency_id
               WHERE q.template_id = %s
               ORDER BY q.sort_order, q.id''',
            (template_id,))
