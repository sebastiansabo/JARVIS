# KAM / Field Sales Blueprint — Verification Record

**Date:** 2026-08-03 · **Branch:** `feature/kam-module`
**Source doc:** `KAM_Module_Strategy.md` (audit & target-state blueprint)
**Method:** 360° code verification of ~40 discrete claims across `field_sales`, `crm`,
`ai_agent`, the Hub/Profile/FieldSales frontend, scheduled jobs, and scoring.

## Verdict

The blueprint is **highly accurate**. Of ~40 claims: **~32 confirmed, ~6 partial, 2 refuted**.
Where it is imprecise it mostly **understates** the problem. Every P0 item is real.

### Confirmed (high-confidence, file:line verified)
- **§0.3 Visit→deal unjoined** — `crm_deals` has no `visit_id`/`opportunity_id`; "opportunity"
  in `field_sales/` is only notification/AI-output naming. Revenue attribution is impossible today.
- **§0.6 Deal-theft on GET** — `deal_repository.relink_to_client` used unanchored `ILIKE '%name%'`
  and reassigned deals owned by other clients, triggered from a GET (`clients.py`). **FIXED (P0-1).**
- **§0.7 JWT `'dev-jwt-secret'` fallback** — `core/mobile/routes/_shared.py:78`.
- **§0.7 Hardcoded personal Cloudflare Worker** — `business_data_service.py:258`
  (`rrf-proxy.sebastian-sabo.workers.dev`); promised OpenAPI.ro/FirmeAPI fallbacks are docstring-only.
- **§0.7 AI tools bypass permissions** — `user_permissions` never passed; `registry.py:72` filter is a no-op.
- **§0.5 AI context bug** — `ai_service.py:42-45` reads flat keys vs nested `{profile:{...}}` → all `'N/A'`.
- **§0.4 Dead AI output + triggers 2/3 never fire** — extracted keys unread; notif triggers gate on
  `opportunity_value_eur`/`risk_flags` the AI never emits.
- **§1.2 Overdue job re-alerts forever** — no `missed` status, no UPDATE; scheduler has no timezone.
- **§1.3 `business_value` never persisted; FX 4.97 hardcoded; service revenue never scored.**
- **§3.3 `by_kam` computed backend, never rendered.**
- **§4.6 No prompt caching; `?refresh=1` unmetered LLM; three "high" magic numbers (75/€10k/60).**
- **Frontend:** cache-key typo `approvals` vs `approvals-queue`; FieldSales desktop-only + `<pre>` JSON
  dump + zero tests; no Field Sales Hub tile; raw `fetch` bypasses; `toISOString().slice(0,10)` day-shift
  bug while `lib/naiveDate.ts` exists; `BottomNav.tsx` dead.

### Partial / corrections to fold into the blueprint
- **Permission scope is NOT "never enforced"** — unenforced in CRM/field-sales (true), but **is** enforced
  in `forms/`, `hr/`, `marketing/`. The pattern to copy already exists → **P0-2 is cheaper than stated.**
- **KPMG credit-assessment misattributed** — it lives in `ai_research_company` → `enrichment_data`,
  not `_ai_company_lookup` → `anaf_data`. Both need quarantining, but they are different functions.
  (The related real bug: `_ai_company_lookup`'s guess **is** stored as `anaf_data` fiscal truth.)
- **Model id hardcoded far more than "3×"** — 22 refs across 14 files. Hostname `jarvis.autoworld.ro`
  hardcoded 9× (not 2). → §4.6 config work is bigger than stated.
- **Uncalled endpoints understated** — ~14 of 26 field-sales routes have no frontend caller (not "9 of 20").
- **Hub/Profile duplication overstated** — invoices + check-in are truly duplicated; vouchers is shared,
  driving is Hub-only. Not everything is triplicated.

### Refuted
- **`generate_structured` is NOT single-caller** — ~6 callers; proven in prod. → §6.1 review card is
  de-risked (route note-structuring through it instead of the hand-rolled fence-stripper).
- **`avg_return_months` is NOT discarded** — returned in `breakdown['retention']`; it's just score-inert.

## Strategic read
- Diagnosis and P0 ordering are correct. §0.3 (no visit→deal join) is the true indictment.
- The **review card (§6.1)** is the highest-leverage single screen and is now de-risked.
- **Recommendation: decouple P0 from the 90-day vision.** Four P0 items are live production risks today
  (deal-theft, JWT fallback, unenforced scope, hallucinated `anaf_data`) and should ship as a 1–2 week
  security/integrity hotfix regardless of the KAM roadmap go/no-go. Phases 2–5 (7 tables, state machine,
  geocoding, offline sync, Hub consolidation, Alembic) are a real multi-month build, not low-risk cleanup.

## Progress
- [x] **P0-1** deal-relink corruption — exact normalized match + orphans-only; no theft, no substring.
      Verified via SQLite predicate test (old stole 2, new steals 0). `deal_repository.py`, `clients.py`.
- [ ] P0-2 enforce `g.permission_scope` (copy the forms/hr pattern)
- [ ] P0-3 remove `'dev-jwt-secret'` fallback (fail hard if unset)
- [ ] P0-7 quarantine `_ai_company_lookup` output out of `anaf_data`; label AI research unverified
- [ ] P0-4/5/6/8/9/10 per blueprint
