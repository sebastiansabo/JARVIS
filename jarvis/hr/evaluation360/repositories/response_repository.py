"""Response persistence — idempotent draft autosave + write-once submit.

One row per assignment (UNIQUE assignment_id). ``draft_payload`` accumulates the
in-progress answers keyed by question id (latest-per-question wins, for offline
sync). ``answers`` + ``is_submitted`` are written once on submit and never again:
the ON CONFLICT / UPDATE guards carry ``WHERE is_submitted = FALSE`` so a
submitted response is immutable at the SQL layer.
"""
import json

from core.base_repository import BaseRepository


class ResponseRepository(BaseRepository):

    def get_by_assignment(self, assignment_id):
        return self.query_one(
            'SELECT * FROM eval_responses WHERE assignment_id = %s', (assignment_id,))

    def save_draft(self, assignment_id, patch, device=None):
        """Merge ``patch`` ({question_id: value, ...}) into the draft. Idempotent
        per question — re-saving a question overwrites just that key. Returns the
        row, or None if the response is already submitted (immutable)."""
        return self.execute(
            '''INSERT INTO eval_responses (assignment_id, draft_payload, device)
               VALUES (%s, %s::jsonb, %s)
               ON CONFLICT (assignment_id) DO UPDATE
                 SET draft_payload = COALESCE(eval_responses.draft_payload, '{}'::jsonb)
                                     || excluded.draft_payload,
                     device = COALESCE(excluded.device, eval_responses.device),
                     updated_at = CURRENT_TIMESTAMP
                 WHERE eval_responses.is_submitted = FALSE
               RETURNING *''',
            (assignment_id, json.dumps(patch or {}), device), returning=True,
        )

    def submit(self, assignment_id, answers, device=None):
        """Write the final answers once. Returns the row, or None if it was
        already submitted (the conflict guard blocks a second write)."""
        return self.execute(
            '''INSERT INTO eval_responses
                 (assignment_id, answers, is_submitted, submitted_at, device)
               VALUES (%s, %s::jsonb, TRUE, CURRENT_TIMESTAMP, %s)
               ON CONFLICT (assignment_id) DO UPDATE
                 SET answers = excluded.answers,
                     is_submitted = TRUE,
                     submitted_at = CURRENT_TIMESTAMP,
                     device = COALESCE(excluded.device, eval_responses.device),
                     updated_at = CURRENT_TIMESTAMP
                 WHERE eval_responses.is_submitted = FALSE
               RETURNING *''',
            (assignment_id, json.dumps(answers or []), device), returning=True,
        )
