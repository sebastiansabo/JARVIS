# BuyBack P4 — Auto-generate the purchase contract on accept + seller signature — Plan

> REQUIRED SUB-SKILL: executing inline (TDD), like P3c. Steps use `- [ ]`.

**Goal:** When the seller accepts the **final offer** (→ BOUGHT) or a **consignment** offer (→ CONSIGNAT), the advisor captures the seller's **drawn signature** on their device; the contract is **auto-generated with the signature embedded**, stored on the record, and **emailed to the advisor** — all **best-effort** so a generation/email failure never blocks the accept.

**Architecture:** Factor the P3c contract-write core into a reusable `buyback/services/contract_generation.py::generate_contract(record, *, signature=None, from_data=False)` (uses the advisor's stored `contract_body` if present, else substitutes the active template; renders via `render_contract_pdf_from_parts(signature=…)`; stores + stamps). The accept route (`routes/offers.py::record_decision`) accepts an optional `signature` and, after a successful accept landing in BOUGHT/CONSIGNAT, calls `generate_contract` + `send_contract_email` inside a swallowing try/except. Frontend: the "Client a acceptat" action opens a signature dialog (reusing `SignatureCanvas`) and passes the data-URL to `recordDecision`.

**Spec:** `jarvis/docs/superpowers/specs/2026-10-20-buyback-purchase-contract-design.md` §6, §10 "P4". Builds on P3b+P3c (both in prod). Branch `feat/buyback-purchase-contract`.

## Global Constraints
- Branch `feat/buyback-purchase-contract`; DB tests `DATABASE_URL=postgresql://localhost/defaultdb`; email/SMTP auto-muted in the buyback harness (do not un-mute); **no live PII/signatures in tests**.
- **Best-effort is non-negotiable:** the accept→BOUGHT/CONSIGNAT transition must succeed and be returned even if contract generation or email raises. Mirrors `send_offer_email`/`notify_owner` swallowing.
- Routes contain NO raw SQL. reportlab injection safety unchanged (every string via `_ptext`). Signature is an optional `data:image/...;base64` data-URL → embedded, else "Lipsă semnătură" placeholder (signature is OPTIONAL — accept can proceed without it).
- P3b/P3c behaviour + tests stay green (the refactor keeps `render_contract_pdf*` and the manual contract route identical).

## Review Focus
- Accept succeeds when `generate_contract` raises (no template, render error) — transition returned, failure logged, not surfaced as a 500. (T3 test.)
- Accept succeeds when `send_contract_email` raises. (T2/T3.)
- Signature data-URL actually reaches the stored PDF (embedded, not dropped). (T3.)
- A stored (advisor-edited) `contract_body` is signed-and-re-rendered, NOT silently overwritten by a fresh template substitution, on accept. (T1/T3.)
- Consignment accept (→CONSIGNAT) also generates (document_type='consignment'). (T3.)

---

### Task 1: Extract `generate_contract` service + refactor the manual route
**Files:** Create `jarvis/buyback/services/contract_generation.py`; modify `jarvis/buyback/routes/contract.py`. Test: `jarvis/tests/buyback/test_contract_generation.py` (+ existing P3b/P3c route tests stay green).
**Produces:** `generate_contract(record, *, signature=None, from_data=False) -> dict` returning `{photo, draft_parts: {title, body, general_conditions}, warnings}`; raises `NoTemplateError` (new, caught by the route → 409) when a template is required but absent. Logic = today's `_write_contract` core (resolve document_type, template-or-stored-body selection via `from_data or not record['contract_body']`, substitute, `render_contract_pdf_from_parts(..., signature=signature)`, `update_contract`, `store_contract_pdf`), now signature-aware. `routes/contract.py` imports and calls it (manual POST passes `from_data`/posted body as today; 409 on `NoTemplateError`).
- [ ] Failing tests: `generate_contract(record, from_data=True)` creates a contract photo + stores body; with a stored `contract_body` and `from_data=False`, it re-renders THAT body (PDF text contains it, template not re-substituted); with `signature=<data-url>` the PDF embeds it (bytes differ vs no-signature / grows); no template + `from_data=True` raises `NoTemplateError`.
- [ ] RED → implement (extract, make route delegate) → GREEN (run `test_contract_generation.py` + `test_contract_edit_route.py` + `test_generate_contract_route.py`) → commit.

### Task 2: `send_contract_email` (best-effort advisor delivery)
**Files:** Modify `jarvis/buyback/services/email.py`. Test: `jarvis/tests/buyback/test_contract_email.py`.
**Produces:** `send_contract_email(record, pdf_bytes, filename=None) -> None` — resolves the advisor contact (`_resolve_advisor_contact`), sends via `send_email` with the contract PDF attached, subject/body naming the record; **swallows every failure** (bad SMTP, raising send_email, no advisor) with a logged warning — mirrors `send_offer_email`.
- [ ] Failing tests: calls `send_email` with the PDF attachment + advisor recipient (assert via a patched/mock `send_email`); a raising `send_email` is swallowed (no exception out); no-advisor path swallows.
- [ ] RED → implement → GREEN → commit.

### Task 3: Accept hook — signature in, best-effort generate + email
**Files:** Modify `jarvis/buyback/routes/offers.py`. Test: `jarvis/tests/buyback/test_accept_generates_contract.py`.
**Produces:** `record_decision` reads `signature` from the JSON body; after `service.record_decision(...)` returns with `updated['status'] in (BOUGHT, CONSIGNAT)`, best-effort (one try/except, logged, never re-raised): re-fetch the record, `pdf = generate_contract(fresh_record, signature=signature)`, then `send_contract_email(fresh_record, pdf['photo']...)` — actually capture the rendered bytes from `generate_contract` for the email (have it also return `pdf_bytes`). The response stays `{success, record}` + a non-blocking `contract` sub-object (`{generated: bool, warnings}`) when it ran.
- [ ] Failing tests: accept a FINAL_OFFER with `signature=<data-url>` → 200, record BOUGHT, a `'contract'` document now exists on the record AND its stored PDF embeds the signature; accept when `generate_contract` raises (monkeypatch it to raise) → still 200 + BOUGHT (transition preserved); accept when `send_contract_email` raises → still 200 + BOUGHT; consignment accept → CONSIGNAT + a consignment contract generated; accept with NO signature → still 200 + contract generated with placeholder.
- [ ] RED → implement → GREEN (full `jarvis/tests/buyback`) → commit.

### Task 4: Frontend — signature dialog on accept
**Files:** Modify `jarvis/frontend/src/api/buyback.ts`, `jarvis/frontend/src/pages/BuyBack/ActionPanel.tsx`.
**Produces:** `recordDecision` data type gains `signature?: string`. The "Client a acceptat" / "Acceptă consignația" button opens a dialog containing `SignatureCanvas` (`onSave`/`onClear`, 500×200) + a note; a **Confirmă** button calls `decisionMutation.mutate({ decision: 'accepted', signature })`, and a **Continuă fără semnătură** path calls it with no signature. Decline path unchanged. On success the existing invalidate refreshes the record + (via P3c) the contract card shows the signed PDF.
- [ ] Implement api + dialog; `cd jarvis/frontend && npx tsc -b` clean; commit (source only).

---
## Notes
- After all tasks: final review, ship staging → prod (cherry-pick buyback-only onto main, 2× confirm, check in-flight DO builds).
- Deferred: dealer-side signature; certified e-signature (spec §11 out-of-scope).
