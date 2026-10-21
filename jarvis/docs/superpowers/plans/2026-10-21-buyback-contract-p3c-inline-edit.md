# BuyBack P3c — Inline-editable contract + smart regenerate + Acțiuni polish — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** On a BuyBack record, show the generated contract in a card under the Acțiuni panel where the advisor can **edit its text inline** (saved per-record, PDF re-renders from the edits), **regenerate from current client/car data** (rebuilds from the template, discarding manual edits with a confirm), and **download** it. Plus clean up the Acțiuni button hierarchy.

**Architecture:** Store the contract's editable text on `buyback_records` (`contract_title`/`contract_body`/`contract_general_conditions`/`contract_generated_at`). Split the renderer into a `_from_parts` path that renders already-final text (used by inline edits) and keep `render_contract_pdf(template_row, context)` delegating to it (P3b behaviour unchanged). One route serves a draft (GET) and a unified write (POST) that either substitutes from the active template (`from_data`) or renders the posted edited text, then stores the PDF via the existing `store_contract_pdf`.

**Tech Stack:** Python/Flask, reportlab, psycopg2; React/TS + React Query.

**Spec/precedent:** builds on P3b (`jarvis/docs/superpowers/plans/2026-10-21-buyback-contract-p3b-renderer.md`). Branch `feat/buyback-purchase-contract` (on staging).

## Global Constraints
- Branch `feat/buyback-purchase-contract`, worktree `/Users/sebastiansabo/Documents/Git/JARVIS-bb-contract`. DB tests: `DATABASE_URL=postgresql://localhost/defaultdb`.
- **Routes contain NO raw SQL** (repo-arch hook) — all DB via repos.
- reportlab injection safety: every user string via `_ptext` (escape, no ASCII-fold); fonts stay DejaVu. The edited body is user-controlled → still escaped.
- Never-500 on sparse/odd input — only 404/403/409 as in P3b.
- P3b tests must stay green (the renderer refactor keeps `render_contract_pdf`'s signature + output).
- Idempotent `ADD COLUMN IF NOT EXISTS`.

## Review Focus
- Edited body containing reportlab markup / `<img>` → escaped, no crash/fetch (Task 2/3 test).
- `from_data` regenerate overwrites the stored edited body; a plain save preserves it (Task 3 test).
- No active template + no stored body → 409, not 500 (Task 3 test).
- GET draft on a record with no stored contract returns the fresh substituted preview with `has_contract=false` (Task 3 test).
- Diacritics still render through the `_from_parts` path (Task 2 test).

---

### Task 1: Schema + repo for the editable contract
**Files:** Modify `jarvis/migrations/domains/schema_buyback.py` (ADD COLUMN block), `jarvis/buyback/repositories/record_repository.py`, `jarvis/buyback/routes/_shared.py` (serialize if it whitelists columns). Test: `jarvis/tests/buyback/test_contract_fields.py`.
**Produces:** columns `contract_title VARCHAR(300)`, `contract_body TEXT`, `contract_general_conditions TEXT`, `contract_generated_at TIMESTAMPTZ` on `buyback_records`; `RecordRepository.update_contract(record_id, title, body, general_conditions) -> dict` (sets the three text cols + `contract_generated_at = now()`, RETURNING *); the record serializer exposes the four fields.
- [ ] Write failing test: a record created then `update_contract(...)` round-trips the fields and stamps `contract_generated_at`.
- [ ] RED, implement (idempotent columns + repo method + serialize), GREEN, commit.

### Task 2: Renderer `_from_parts` refactor
**Files:** Modify `jarvis/buyback/services/contract_pdf.py`. Test: `jarvis/tests/buyback/test_contract_pdf_from_parts.py` (+ existing P3b render tests stay green).
**Produces:** `render_contract_pdf_from_parts(title: str, body: str, general_conditions: str = '', signatory: str = '', signature: str | None = None) -> bytes` holding the current rendering logic on FINAL strings (no `render_contract_template` calls; `signatory` drives the dealer signature line). `render_contract_pdf(template_row, context, signature=None)` now substitutes title/body/general_conditions via `render_contract_template` + derives `signatory` from context, then delegates to `_from_parts` — its signature and output are unchanged.
- [ ] Write failing test: `_from_parts('Contract', 'Mașină {already} ăâșț', 'GC')` → valid `%PDF-`, diacritics present, and the literal `{already}` is NOT substituted (proves no token pass). Keep the P3b `render_contract_pdf` tests.
- [ ] RED, implement (extract body, delegate), GREEN (run the full render test file + P3b render tests), commit.

### Task 3: Draft GET + unified write POST
**Files:** Modify `jarvis/buyback/routes/contract.py`. Test: `jarvis/tests/buyback/test_contract_edit_route.py`.
**Produces:**
- `GET /records/<id>/contract` → `{has_template, has_contract, document_type, title, body, general_conditions, generated_at, download_url, warnings}`. `record.view`. If no stored `contract_body`: `has_contract=false` and title/body/general_conditions are the fresh substitution from the active template (preview to edit); if no active template: `has_template=false`, empty text.
- `POST /records/<id>/contract` `{title?, body?, general_conditions?, from_data?: bool}`. `record.edit`. Logic: resolve `document_type` as P3b. If `from_data` is true OR (`body` absent AND no stored `contract_body`): require an active template (else 409), substitute title/body/gc from template+current record; else use the posted title/body/general_conditions. Render via `render_contract_pdf_from_parts` (signatory from the company's `administrator`/name), `RecordRepository.update_contract(...)`, `PhotoRepository().store_contract_pdf(id, pdf, caption=title or 'Contract')`, return `{photo: serialize, draft, warnings}`. No raw SQL. Keep the existing `POST /records/<id>/generate-contract` working (delegate to the same handler with `from_data=True`).
- [ ] Failing tests: generate-from-data creates body+photo; POST with edited `body` stores that exact body (PDF text contains it, template NOT re-substituted); `from_data=true` after an edit overwrites the edit; no template + no body → 409; GET draft with no stored contract returns the substituted preview + `has_contract=false`; cross-company → 403.
- [ ] RED, implement, GREEN (full `jarvis/tests/buyback`), commit.

### Task 4: Frontend — API + ContractCard under Acțiuni
**Files:** Modify `jarvis/frontend/src/api/buyback.ts`, `jarvis/frontend/src/pages/BuyBack/BuyBackDetail.tsx`; Create `jarvis/frontend/src/pages/BuyBack/ContractCard.tsx`.
**Produces:** api `getContractDraft(id)`, `saveContract(id, {title, body, general_conditions})` (POST, no `from_data`), `regenerateContractFromData(id)` (POST `{from_data:true}`). `ContractCard` mounted directly under `<ActionPanel/>` in BuyBackDetail, shown when the record is contract-eligible (status in `FINAL_OFFER/BOUGHT/CONSIGNMENT_OFFER/CONSIGNAT`) and `can('buyback.record.view')`. Card: generated-at line; editable Titlu (Input) + Conținut (Textarea, monospace, ~14 rows) + collapsible Condiții generale; buttons **Salvează & regenerează** (saveContract), **Descarcă PDF** (draft.download_url, hidden until one exists), **Regenerează din date** (confirm when the body was manually edited; regenerateContractFromData). Empty/no-template state: a hint linking to Setări → BuyBack → Contracte. Invalidate `['buyback-record', id]` + the draft query on success; Romanian toasts in the interface voice.
- [ ] Implement api + component + mount; `cd jarvis/frontend && npx tsc -b` clean; commit (source files only, no build artifacts).

### Task 5: Beautify the Acțiuni panel
**Files:** Modify `jarvis/buyback/.../ActionPanel.tsx`.
**Produces:** a clear button hierarchy — the single most-important next-step action stays solid (primary); secondary actions (Propune consignație, Schimbă status, Transferă în custodie, Generează/Regenerează) become quiet `variant="outline"`/ghost; the destructive **Anulează** becomes a restrained ghost with red text (`variant="ghost"` + `text-destructive`), not a solid red block; utility actions (Schimbă status, Suspendă) group together visually separated from the progress actions. Wrap the loose buttons in a consistent `flex flex-wrap gap-2` row with a subtle divider between progress and utility groups. No logic/conditional changes — visual only. `npx tsc -b` clean; commit.

---
## Notes
- After all tasks: final review, then re-ship to staging (FF push `feat/buyback-purchase-contract:staging`, monitor DO → ACTIVE). Prod stays a separate 2×-confirm step.
- The relabel: the Generează button text becomes **Regenerează contract** when `draft.has_contract` (handled in ContractCard; the ActionPanel generate button can be removed once ContractCard owns generation, or kept — Task 4 decides, Task 5 keeps ActionPanel visual-only).
