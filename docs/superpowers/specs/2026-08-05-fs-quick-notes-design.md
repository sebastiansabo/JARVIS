# Field Sales — Quick Non-Finalizing Notes (Phase 2, Slice 2)

**Date:** 2026-08-05
**Branch:** `fs-quick-notes` (off `dev` 46b300801) → ff-merge to `dev` at finish.
**Type:** Small feature. Second slice of Phase 2 (`add-info-during-visit`). Builds on Slice 1 (AI-note schema fix, shipped `dev` 46b300801).

## Problem
A KAM can only add a note to a visit via `POST /api/field-sales/visits/<id>/note`, which **finalizes** the visit: it AI-structures the note, calls `complete()`, recomputes the renewal score, and fires the high-value/risk notifications. There is no way to jot information *during* an in-progress visit without ending it. This slice adds lightweight, raw, non-finalizing notes.

## Decisions (user)
- **Raw only** — a quick note is saved as-is; no AI structuring, no LLM wait.
- **In-progress only** — a quick note can be added solely when the visit `status == 'in_progress'` (i.e. after check-in, before finalize). Any other status is rejected.

## Data model
No schema change. `kam_visit_notes` already stores multiple notes per visit: `id, visit_id, raw_note, structured_note (JSONB, nullable), structured_at, created_at`. A quick note is a row with `raw_note` set and `structured_note` NULL. `VisitRepository.add_note(visit_id, raw_note)` (existing) inserts exactly this. The visit-detail endpoint already returns `visit.notes`, and `VisitDetailDialog` already renders them read-only; `note_count` is already surfaced on list rows.

## Design

### Backend — new endpoint (single responsibility)
`POST /api/field-sales/visits/<int:visit_id>/quick-note` in `jarvis/field_sales/routes/visits.py`, decorated `@jwt_or_login_required` + `@field_sales_required` (mirroring `api_visit_note`). Steps:
1. Load the visit; 404 if missing.
2. **IDOR:** `visit['kam_id'] == _get_current_user().id` else 403 "Poți adăuga note doar la vizitele tale".
3. **Status guard:** `visit['status'] == 'in_progress'` else **409** with error "Poți adăuga note doar în timpul vizitei (vizita trebuie să fie în desfășurare)".
4. Validate `raw_note`: required (400 "raw_note is required") and ≤10000 chars (400, mirroring `/note`).
5. `note = _visit_repo.add_note(visit_id, raw_note)` — raw only, no `structured_note`.
6. Return `{'success': True, 'note': note}` (201).

It does **not** structure, complete, recompute renewal, or notify. A separate endpoint (not a `finalize=false` flag on `/note`) keeps `/note`'s finalize contract untouched and this path trivially auditable.

If mobile (Capacitor) will call it later, `POST` must be in `app.py` `_mobile_cors` allow-methods (POST is already used by `/note`, so already allowed — no change expected; confirm during implementation).

### Frontend
- `jarvis/frontend/src/api/fieldSales.ts`: `addQuickNote(visitId: number, rawNote: string)` → `api.post('/api/field-sales/visits/${visitId}/quick-note', { raw_note: rawNote })` returning `{ success: boolean; note: FSVisitNote }`.
- `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx`: a quick-note composer (shadcn `Textarea` + a "Adaugă notă" `Button`) rendered **only when `visit.status === 'in_progress'`**, adjacent to the existing notes list. A `useMutation(addQuickNote)`:
  - `onSuccess`: clear the textarea, `invalidateQueries(['fs-visit-detail', visitId])` (the new note appears on refetch), and invalidate the Hub lists `['field-sales-visits']`, `['field-sales-mine']`, `['field-sales-cal']` (note_count changes).
  - Button disabled while the trimmed text is empty or the mutation is pending; inline error text on failure (reads `err.data.error`).
- No change to the read-only notes render (quick notes have `structured_note` NULL and show their `raw_note` like any note).

### Data flow
compose → `addQuickNote` → `add_note` INSERT → detail refetch → note renders in the existing `visit.notes` list. Visit stays `in_progress`; the finalize flow (`/note` via NoteCaptureModal) is unchanged and still the way to end the visit.

## Tenant-awareness
Inherited. The endpoint is IDOR-gated to the visit owner; the visit's `company_id` is already set. No new company surface — consistent with `/note` and Slice 1.

## Error handling
- 404 missing visit; 403 not-owner; 409 wrong status; 400 empty/oversized note. Frontend surfaces the server `error` inline and keeps the composer open with the text intact on failure.

## Testing
- **Frontend (vitest, primary):** `VisitDetailDialog` — (a) composer renders when `status: 'in_progress'`; (b) composer absent when `status: 'planned'` and when `'completed'`; (c) submitting calls `addQuickNote(visitId, text)`, then the textarea clears and the detail + hub-list queries are invalidated; (d) the button is disabled for empty/whitespace input. Mock `fieldSalesApi.addQuickNote`/`getVisit` as the existing FieldSales tests do.
- **Backend:** `python3 -c "import ast; ast.parse(...)"` on `visits.py`. If a Flask test-client harness exists (e.g. the pattern in `tests/test_api_endpoints.py`), add a focused route test asserting: 409 when the visit is not `in_progress`, 403 for a non-owner, and a 201 + persisted raw note when `in_progress`. If no reusable harness exists, the guard is small and deterministic — rely on `ast.parse` + the frontend contract test + a manual localhost check, and record that decision in the plan.
- **Gates:** `npx tsc --noEmit` clean; full `npx vitest run` pristine; backend `ast.parse`; `npm run build` then revert artifacts. Commit source only (never `static/react/*` or `tsconfig.tsbuildinfo`). Ignore the post-commit hook's pre-existing repo-wide failures.

## Out of scope (later slices / follow-ups)
- Editing or deleting notes.
- AI-structuring quick notes (user chose raw); a quick note never gets a `structured_note`.
- A quick-note entry point directly on the Hub in-progress card (the detail dialog is the home for now).
- Prettifying the existing `JSON.stringify` structured-note render in `VisitDetailDialog` (cosmetic, pre-existing).
- Slices 3 (edit client details) and 4 (fleet add/edit).

## Self-review
Decisions (raw-only, in_progress-only) are encoded in the endpoint's structure guard and the composer's render gate. No schema change; reuses `add_note`. Single-responsibility endpoint leaves `/note` untouched. Invalidation covers detail + the three Hub keys so `note_count` and the notes list stay fresh. Tenant scoping is inherited and explicitly noted. Testing centers on the frontend contract with a backend guard test where the harness allows. Scope is one slice / one plan.
