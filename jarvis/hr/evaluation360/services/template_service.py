"""Competency-library + form-template authoring (HR side of the module).

Fork-on-edit is the core invariant (spec §3): a `published` template is
immutable. Any edit to a published template first forks a new `draft` version
(``version+1``, ``forked_from_id`` set, question blocks copied) and applies the
change to that fork — so an in-flight cycle keeps the exact form it launched
with. Draft templates edit in place.
"""
from hr.evaluation360.repositories.template_repository import EvalTemplateRepository
from hr.evaluation360.repositories.event_repository import EvalEventRepository

DEFAULT_AUDIENCES = ('self', 'manager', 'peer', 'direct_report')


class TemplateError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class EvalTemplateService:
    def __init__(self, repo=None, event_repo=None):
        self.repo = repo or EvalTemplateRepository()
        self.events = event_repo or EvalEventRepository()

    # ── competencies ─────────────────────────────────────────────────
    def list_competencies(self, include_inactive=False):
        return self.repo.list_competencies(include_inactive=include_inactive)

    def create_competency(self, data, actor_id=None):
        name = (data.get('name') or '').strip()
        if not name:
            raise TemplateError('name is required')
        comp = self.repo.create_competency(
            name=name, definition=data.get('definition'),
            cluster=(data.get('cluster') or None), created_by=actor_id)
        self.events.emit('competency.created', actor_id=actor_id,
                         payload={'competency_id': comp['id']})
        return comp

    def update_competency(self, cid, data, actor_id=None):
        comp = self.repo.update_competency(cid, data)
        if not comp:
            raise TemplateError('competency not found', 404)
        return comp

    # ── templates ────────────────────────────────────────────────────
    def list_templates(self, include_archived=False):
        return self.repo.list_templates(include_archived=include_archived)

    def get_template(self, template_id):
        tpl = self.repo.get_template(template_id)
        if not tpl:
            raise TemplateError('template not found', 404)
        return {'template': tpl, 'questions': self.repo.list_questions(template_id)}

    def create_template(self, data, actor_id=None):
        name = (data.get('name') or '').strip()
        if not name:
            raise TemplateError('name is required')
        tpl = self.repo.create_template(
            name=name, competency_ids=data.get('competency_ids') or [],
            created_by=actor_id)
        if data.get('questions'):
            self.repo.replace_questions(tpl['id'], data['questions'])
        self.events.emit('template.created', actor_id=actor_id,
                         payload={'template_id': tpl['id']})
        return self.get_template(tpl['id'])

    def save_template(self, template_id, data, actor_id=None):
        """Persist name / competencies / questions. On a *published* template
        this forks a new draft first and edits the fork; the fork's id is
        returned so the caller can follow the new version."""
        tpl = self.repo.get_template(template_id)
        if not tpl:
            raise TemplateError('template not found', 404)
        if tpl['status'] == 'archived':
            raise TemplateError('archived templates cannot be edited', 409)

        working_id = template_id
        forked = False
        if tpl['status'] == 'published':
            fork = self._fork(tpl, actor_id)
            working_id = fork['id']
            forked = True

        name = data.get('name')
        competency_ids = data.get('competency_ids')
        if name is not None or competency_ids is not None:
            self.repo.set_template_meta(
                working_id,
                name=(name.strip() if isinstance(name, str) else None),
                competency_ids=competency_ids)
        if data.get('questions') is not None:
            self.repo.replace_questions(working_id, data['questions'])

        result = self.get_template(working_id)
        result['forked'] = forked
        return result

    def publish_template(self, template_id, actor_id=None):
        tpl = self.repo.get_template(template_id)
        if not tpl:
            raise TemplateError('template not found', 404)
        if tpl['status'] == 'published':
            return self.get_template(template_id)
        if tpl['status'] == 'archived':
            raise TemplateError('archived templates cannot be published', 409)
        if not self.repo.list_questions(template_id):
            raise TemplateError('a template needs at least one question before publishing')
        self.repo.set_template_status(template_id, 'published')
        self.events.emit('template.published', actor_id=actor_id,
                         payload={'template_id': template_id})
        return self.get_template(template_id)

    def archive_template(self, template_id, actor_id=None):
        tpl = self.repo.get_template(template_id)
        if not tpl:
            raise TemplateError('template not found', 404)
        self.repo.set_template_status(template_id, 'archived')
        self.events.emit('template.archived', actor_id=actor_id,
                         payload={'template_id': template_id})
        return self.get_template(template_id)

    def fork_template(self, template_id, actor_id=None):
        tpl = self.repo.get_template(template_id)
        if not tpl:
            raise TemplateError('template not found', 404)
        fork = self._fork(tpl, actor_id)
        return self.get_template(fork['id'])

    # ── helpers ──────────────────────────────────────────────────────
    def _fork(self, tpl, actor_id):
        version = self.repo.max_version(tpl['name']) + 1
        fork = self.repo.create_template(
            name=tpl['name'], competency_ids=tpl.get('competency_ids') or [],
            rating_scale=tpl.get('rating_scale'), created_by=actor_id,
            version=version, forked_from_id=tpl['id'], status='draft')
        self.repo.copy_questions(tpl['id'], fork['id'])
        self.events.emit('template.forked', actor_id=actor_id,
                         payload={'template_id': fork['id'], 'forked_from': tpl['id']})
        return fork

    @staticmethod
    def question_for_competency(competency_id, text, *, qtype='rating', required=True):
        """Build a question-block dict with one prompt shown to every audience —
        the common case for the builder's competency rows."""
        return {
            'competency_id': competency_id,
            'type': qtype,
            'required': required,
            'text_by_audience': {a: text for a in DEFAULT_AUDIENCES},
        }
