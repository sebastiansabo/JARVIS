# Field Sales — AI Visit-Note Schema Fix (Phase 2, Slice 1)

**Date:** 2026-08-05
**Branch:** `fs-ainote-schema-fix` (off `dev` 22d210dd8) → ff-merge to `dev` at finish.
**Type:** Bug fix + small hardening. First slice of Phase 2 (`add-info-during-visit`); the remaining slices (quick non-finalizing notes, edit client details, fleet add/edit) get their own spec→plan→build cycles.

## Problem

There is one canonical structured-note contract, `FSStructuredNote` (`jarvis/frontend/src/api/fieldSales.ts`), consumed by **both** the review UI (`NoteCaptureModal.tsx`) **and** the backend notifiers (`jarvis/field_sales/notifications.py`: `notify_high_value_opportunity`, `notify_risk_flags`). The AI prompt in `ai_service.structure_visit_note` (`jarvis/field_sales/services/ai_service.py`) emits a *different, drifted* schema — nearly every field name mismatches, plus one type mismatch.

| Canonical `FSStructuredNote` (UI + notifiers read) | AI prompt currently emits |
|---|---|
| `visit_summary` | `summary` |
| `contact_person` | — |
| `vehicles_discussed: [{action, current_vehicle, interested_in, budget_eur}]` | `vehicles_of_interest: [{brand, model, type, notes}]` |
| `commitments_made: string[]` | `action_items: [{task, owner, deadline}]` |
| `next_steps: [{action, owner, deadline}]` | `next_steps: "…string…"` (type mismatch) |
| `opportunity_value_eur: number\|null` | — (has `deal_probability`) |
| `decision_timeline: string\|null` | — |
| `objections: string[]` | — |
| `risk_flags: string[]` | — |
| `follow_up_date` | `follow_up_date` (only field that matches) |

**Impact (all currently dead in production):**
1. The structured review UI renders almost nothing — every field guard (`x?.length ?? 0`, `structured.visit_summary`) resolves to undefined/absent.
2. `notify_high_value_opportunity` never fires — it reads `opportunity_value_eur` (always None ⇒ the `≥ €10,000` gate never triggers).
3. `notify_risk_flags` never fires — it reads `risk_flags` (always empty).

## Canonical schema (the fix target)

The AI output — and everything downstream — standardizes on `FSStructuredNote` **plus `sentiment`** (user decision to keep it):

```
{
  "visit_summary": string,                       // 1-2 sentence summary
  "sentiment": "positive" | "neutral" | "negative" | null,
  "contact_person": string | null,
  "vehicles_discussed": [
    { "action": string, "current_vehicle": string|null, "interested_in": string|null, "budget_eur": number|null }
  ],
  "commitments_made": string[],
  "next_steps": [ { "action": string, "owner": string, "deadline": string|null } ],
  "opportunity_value_eur": number | null,
  "decision_timeline": string | null,
  "follow_up_date": string | null,               // YYYY-MM-DD or null
  "objections": string[],
  "risk_flags": string[]
}
```

`deal_probability` (old prompt) is **dropped** — nothing reads it. `fleet_updates`, `topics_discussed`, `client_needs` (old prompt) are dropped — not in the contract; fleet edits are a later Phase-2 slice.

## Design

Three coordinated changes plus tests.

### 1. Backend — rewrite the AI prompt (`ai_service.structure_visit_note`)
Replace the JSON schema block + rules in `system_prompt` so the model targets the canonical schema above (exact field names, the `vehicles_discussed`/`next_steps` object shapes, `sentiment` enum, `objections`/`risk_flags`/`opportunity_value_eur`/`contact_person`/`decision_timeline`). Keep the existing markdown-fence stripping, `json.loads`, and error-dict returns (`{'error': …}`) unchanged. Update the "field has no data" rule to say scalars → null, arrays → `[]`.

### 2. Backend — server-side normalizer (user decision)
Add a private `_normalize_structured_note(raw: dict) -> dict` in `ai_service.py`, applied to the parsed LLM output **before** it is returned (so both storage and the response envelope get the clean shape). It:
- Whitelists exactly the canonical keys; drops any stray keys the LLM invents.
- Coerces types defensively: array fields (`vehicles_discussed`, `commitments_made`, `next_steps`, `objections`, `risk_flags`) forced to lists (non-list → `[]`); scalar fields default to null when absent; `sentiment` clamped to the enum (else null); `opportunity_value_eur`/`budget_eur` coerced to number-or-null.
- Never raises — a malformed element degrades to a safe default rather than crashing. If `raw` carries an `{'error': …}` marker, it is returned untouched (the endpoint already treats `structured.get('error')` as "skip save").

This guarantees off-shape LLM output can never reach the DB/frontend, independent of prompt adherence. The frontend keeps its existing null-guards as defense-in-depth.

### 3. Frontend — add `sentiment` to the contract + render it
- Add `sentiment: 'positive' | 'neutral' | 'negative' | null` to `FSStructuredNote` (`api/fieldSales.ts`).
- Render a small sentiment badge in `NoteCaptureModal.tsx`'s review step (color per value; hidden when null), consistent with existing iOS-sized styling.

### Data flow (unchanged except the shape)
`POST /visits/:id/note` → `add_note(raw)` → `structure_visit_note(raw, client_context)` → **normalizer** → `update_note_structured(note.id, structured)` (JSONB) → response `{ note, structured_note, visit_status }`. The visit is still completed (this slice does **not** change finalize behavior — that's Slice 2).

## Tenant-awareness
No change required. The note endpoint is IDOR-gated to the visit owner (`visit['kam_id'] == current_user.id`), and `get_client_context(visit_id)` derives context from that owned visit only. No `company_id` surface here.

## Testing
- **Backend drift-guard** (`tests/`): assert the `structure_visit_note` system prompt string contains every canonical key (`visit_summary`, `sentiment`, `contact_person`, `vehicles_discussed`, `commitments_made`, `next_steps`, `opportunity_value_eur`, `decision_timeline`, `follow_up_date`, `objections`, `risk_flags`) — cheap regression guard, no LLM call. (First field_sales pytest file; if the harness can't import the module standalone, fall back to an `ast`/source-string assertion.)
- **Normalizer unit tests**: off-shape inputs (stray keys, `next_steps` as a string, arrays as null/scalar, bad `sentiment`, non-numeric `opportunity_value_eur`, `{'error':…}` passthrough) → assert clean canonical shape / safe defaults.
- **Backend parse path**: mock `ask()` to return a canonical-shaped JSON (raw + fenced) → `structure_visit_note` returns the normalized dict.
- **Frontend**: extend `NoteCaptureModal.test.tsx` to assert the sentiment badge renders for a value and is absent when null. Existing structured-render tests already pin the canonical field names and must stay green.
- **Gates:** `npx tsc --noEmit` clean; full `npx vitest run` pristine; backend `python3 -c "import ast; ast.parse(...)"` on changed `.py`; `python3 -m pytest tests/<new>` if runnable. `npm run build` then revert artifacts. Commit source only.

## Out of scope (later Phase-2 slices / tickets)
- Quick non-finalizing notes; edit client details; fleet add/edit.
- Phase-1 follow-up tickets: `clients/search` server-side auth; client-vs-company coherence on visit create.
- Reprocessing/backfilling already-stored (mis-shaped) structured notes — new notes get the correct shape; old rows stay as-is (the UI guards render them harmlessly).

## Self-review
Canonical schema is fully specified (no TBD). Prompt rewrite + normalizer + sentiment badge are internally consistent (all target the same key set). Scope is one slice, single plan. `sentiment` and `deal_probability` handling is explicit. Testing covers prompt drift, normalizer robustness, parse path, and the new UI badge.
