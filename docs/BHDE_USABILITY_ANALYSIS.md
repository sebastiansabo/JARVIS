# BHDE Usability Analysis — JARVIS at ~200 Concurrent Users

**Date:** April 29, 2026
**Branch:** `claude/analyze-bhde-usability-3jV5e`
**Scope:** Usability and scalability flaws across the four flagship modules — **B**ugetare, **H**R, **D**ashboard, **e**-Factura — plus the supporting Flask/React/Postgres infrastructure, evaluated against a target load of ~200 active users.

> **Note on terminology.** "BHDE" is used here as shorthand for Bugetare + HR + Dashboard + e-Factura (the four user-facing pillars described in `docs/CLAUDE.md` and `README.md`). It is not a name in the codebase.

---

## TL;DR

JARVIS is well-engineered for an internal tool of ~20–30 users (which is what the current production hardware was sized for). At **~200 users it will degrade severely**, and several UX patterns that are tolerable at small scale become dealbreakers. The single most urgent issue is request capacity: the platform is provisioned to serve **9 concurrent requests** while a 200-user audience routinely produces 20–60 in-flight requests at peak. Every other finding in this report is ranked against that backdrop.

| Severity | Theme | Count |
|----------|-------|-------|
| **Critical** | Request capacity, blocking I/O on hot paths, missing pagination on dashboard | 4 |
| **High** | RBAC visibility, optimistic concurrency, mobile/empty states, error UX | 6 |
| **Medium** | i18n consistency, AI/Drive timeouts, HR lock UX, e-Factura OAuth re-auth | 5 |
| **Low** | Tooling polish, discoverability nits | 3 |

---

## 1. Capacity & Scalability

### C1 — Total concurrency ceiling: 9 requests · **Critical**

`Procfile:1` and `Dockerfile:49` both pin Gunicorn to `--workers 3 --threads 3 --worker-class gthread`. That is **9 simultaneous requests in flight, ever.** `.do/app.yaml:7-8` further sets `instance_count: 1` and `instance_size_slug: apps-s-1vcpu-1gb` — there is no horizontal scaling and only 1 GB of RAM.

For 200 users the practical implication is:
- A single accounting page-load fires **11+ parallel `useQuery` requests** (the comment at `database.py:23` even acknowledges this). At ~18 simultaneous users the entire request queue is full and the 19th user starts seeing 30–120 s response times.
- The `--timeout 120` flag means stuck workers tie up a slot for two minutes before being recycled.

**Fix direction:** Raise to `--workers 4 --threads 8` (32 in-flight) for a minimum-viable bump, raise the DO instance to `apps-s-2vcpu-4gb`, and scale `instance_count` to 2–3 behind the existing health check. Plan a cutover to async I/O (gevent or quart) for the AI + SMTP + ANAF call paths.

### C2 — DB pool sized for the old worker count · **Critical**

`jarvis/database.py:27-28` defaults to `POOL_MIN_CONN=2, POOL_MAX_CONN=15`. The DigitalOcean managed Basic plan caps at 47 connections (`database.py:21`). With 4 workers × 8 threads = 32 needed slots per app instance, the **15-connection cap will starve threads** and trigger the "Connection pool exhausted" error from `_getconn_with_timeout` at `database.py:75-77` after 10 s waits.

**Fix direction:** Bump `DB_POOL_MAX_CONN` per worker so that `workers × max_per_worker ≤ 45`; consider PgBouncer in transaction mode and upgrade the DO database tier — 47 connections is not enough for 200 users.

### C3 — Synchronous SMTP in the request path · **Critical**

`core/services/notification_service.py:128-137` opens `smtplib.SMTP` and calls `sendmail` **inside the request thread**, with no queue and no timeout. Every "Save Distribution" click in Bugetare iterates allocations at `notification_service.py:560` and calls `send_email` once **per responsable per allocation**:

> A 5-allocation invoice with two managers per department will block the user's request for 10 sequential SMTP round-trips before returning. SMTP latency of 300–800 ms × 10 = 3–8 s of perceived UI freeze, all under the 120 s worker timeout.

At 200 users this is the most likely source of `Connection pool exhausted` cascades — one slow SMTP server can stall every worker thread it owns.

**Fix direction:** Push notification sends onto an APScheduler job (the scheduler already exists, see `tasks/cleanup.py` referenced at `app.py:42-46`) or a Redis-backed RQ queue. Return immediately to the client and surface delivery status in the activity log.

### C4 — Synchronous Claude API calls during invoice upload · **Critical**

`accounting/bugetare/invoice_parser.py` issues vision calls at lines 211, 335, 501, 1204, 1380 — all inline. Bulk uploads (`bulk_processor.py:92`, `:367`, `:609`, `:714`) chain PDF extraction → AI parse with no concurrency. With the global ceiling of 9 worker threads and Claude P95 of 2–6 s, **a single user uploading 10 invoices monopolises one of those nine slots for ~30 seconds**.

**Fix direction:** Move parsing to background jobs and deliver the result via SSE or polling — the SSE plumbing already exists in `ai_agent/`. Cap concurrent AI calls per user.

---

## 2. Frontend Usability

### F1 — Accounting dashboard fetches *all* invoices on mount · **Critical**

`pages/Accounting/index.tsx:146-153` builds `apiFilters` from filter state and calls `invoicesApi.getInvoices(apiFilters)` with no `page` or `limit` — it relies entirely on filter narrowing. The repository at `accounting/invoices/repositories/invoice_repository.py:225` does support `LIMIT %s OFFSET %s` but the Accounting page **never sends those parameters**. With ~200 users producing several thousand invoices a month, the dashboard load becomes O(table scan) and pushes a multi-megabyte JSON payload through the wire on every filter change.

For comparison, `pages/EFactura/UnallocatedTab.tsx:61-62, 787-794` does it correctly: `usePersistedState('efactura-page-size', 50)` plus a `Page X of Y (N invoices)` footer.

**Fix direction:** Apply the e-Factura pagination pattern to Accounting/Invoices. Default to 50, persist user choice in localStorage with the `efactura` schema.

### F2 — No table virtualization · **High**

There is no `react-virtual`, `react-window` or TanStack Virtual import anywhere in `frontend/src`. `Accounting/index.tsx` (1,529 lines) and `EFactura/UnallocatedTab.tsx` (1,195 lines) both render every row in the DOM. Even with pagination, mobile devices and the `MobileCardList` component (`components/shared/MobileCardList.tsx`) struggle past ~200 rows.

**Fix direction:** Adopt `@tanstack/react-virtual` for the two dashboards — it is a 30-line change that yields 5–10× scroll FPS on 500-row pages.

### F3 — No optimistic locking on invoice / allocation edits · **High**

I searched for `FOR UPDATE`, `version`, `lock_version`, `If-Match`, and `etag` across `accounting/invoices/` and `efactura/repositories/`. **None are used.** Two users editing the same invoice in parallel (a realistic scenario at 200 users where multiple managers cover the same department) will silently overwrite each other; the only audit trail is `user_events`, which is read-only.

**Fix direction:** Add `updated_at` checks to PUT endpoints (return 409 Conflict if the row has moved since the user's read) and surface a "someone else changed this — reload?" toast in the React mutation handler. The `JarvisToast` infrastructure described in `CLAUDE.md` already exists.

### F4 — Backend errors leak to the user · **High**

CODEBASE_REVIEW.md §S4 already flagged the 109+ `{success: false, error: str(e)}` instances. From a usability standpoint that means a non-technical accountant sees Postgres constraint names and SQL fragments in toast messages whenever something fails. A `ErrorBoundary` does exist (`components/ErrorBoundary.tsx`, mounted at `main.tsx:128`) but it only catches React render errors, not API errors.

**Fix direction:** Centralise via `@app.errorhandler` in `app.py` and translate exception classes to user-facing messages. Keep the raw `str(e)` in server logs only.

### F5 — Tab switches re-fetch · **Medium**

The four-tab dashboard (Invoices / By Company / By Department / By Brand) keys queries on `['invoices', filters]` (`Accounting/index.tsx:152`) but the summary tabs use separate endpoints; switching tabs blows the React Query cache for each. With slow networks (Romania, mobile) every tab change is a 1–3 s wait.

**Fix direction:** Set `staleTime: 30_000` on summary queries; pre-fetch siblings on tab hover.

---

## 3. Permissions & RBAC at 200 Users

### R1 — User CRUD authorization bypass · **Critical** *(already documented)*

CODEBASE_REVIEW.md S1 still applies: `core/auth/routes.py:38-121` has `@login_required` only. **At 200 users this becomes a reputational and compliance issue, not just a security one** — Romanian financial software touched by an unprivileged user will fail the next ISO/SOC review.

### R2 — Frontend doesn't reflect `min_role` on dropdown options · **High**

`accounting/invoices/services/invoice_service.py:440-447` enforces `min_role` server-side via `ROLE_HIERARCHY`. The frontend, however, fetches dropdown options without the role filter (`Accounting/index.tsx:206`), so a Viewer sees statuses they can't set, clicks, and gets an opaque 403. At 200 users this manifests as 50+ daily "I clicked Approve but nothing happened" tickets.

**Fix direction:** Filter dropdown options by current user's role on the backend, or grey out forbidden options with a tooltip explaining why.

### R3 — HR scope permissions: deny/own/department/all · **Medium**

CLAUDE.md describes `deny / own / department / all` scopes but `hr/events/utils.py:87-102` shows the only role check is a hard-coded `if user_role == 'Admin'`. That binary "Admin or not" is too coarse for 200 users where you typically want department leads who can edit their department but not others.

**Fix direction:** Replace the string comparison with the documented scope-based check; make the backend the source of truth and have the React UI hide rather than disable forbidden actions.

---

## 4. Per-Module Concerns

### B — Bugetare

- **Bulk upload memory** (`accounting/bugetare/bulk_processor.py`): files are read into memory and sent to Claude vision sequentially. On a 1 GB DO instance, two users uploading a 25 MB statement (`InvoiceLinkedDocs.tsx:28` MAX_FILE_SIZE) at the same time risks OOM and worker recycle. **High.**
- **VAT subtraction UX**: the "Subtract VAT" checkbox + dropdown pattern works for power users but introduces three coupled fields (`subtract_vat`, `vat_rate_id`, `net_value`) without a preview. Document validation says percentages must "sum to 100% with 1% tolerance" — the React client should show running totals live. **Medium.**

### H — HR Events

- **Lock day 5 hard-cutover** (`hr/events/utils.py:39-47`): when February 5 passes, January bonuses lock instantly with the only escape hatch being `user_role == 'Admin'`. With 200 users and a finance team of 5–10, **every late-arriving HR change on the 6th becomes an admin escalation**. Add a "request-edit" flow with approval, or a 24-hour grace flag the HR lead can flip. **High.**
- **`is_locked` UX**: the `get_lock_status` payload (`utils.py:50-84`) is well-shaped but I could not find a corresponding banner component on the frontend; users only discover the lock on Save. **Medium.**

### D — Dashboard

- **F1 above** is the headline issue.
- **Currency toggle** (`localStorage 'totalValueDisplayCurrency'`): per-browser, so a user switching laptops loses their preference. At 200 users with hot-desking that's a constant nuisance. Persist server-side under user preferences. **Low.**

### E — e-Factura

- **OAuth token expiry UX** (`core/connectors/efactura/repositories/oauth_repository.py`): if `expires_at` lapses mid-import, the only signal is a 500 error. Surface a yellow banner with a "Reconnect ANAF" button on `/efactura/`, driven by the existing `/efactura/oauth/status` endpoint. **High.**
- **Duplicate detection feedback** (`services/duplicate_service.py:174-189`): the `LIMIT 500` cap is silent — beyond 500 candidate invoices the AI fallback skips remaining matches without telling the user. Add a "scanned 500 of N — narrow your filter" hint. **Medium.**
- **Pagination cap**: `repositories/invoice_repository.py:407` correctly uses `LIMIT %(limit)s OFFSET %(offset)s`; the frontend correctly drives it. This is the gold-standard pattern for the rest of the app to copy.

---

## 5. Onboarding, Discoverability & i18n

| # | Issue | File / Evidence | Severity |
|---|-------|------------------|----------|
| O1 | Mixed Romanian / English UI — `Bugetare`, `Nebugetata`, `responsable` labels live next to English buttons. New hires need a glossary on day one. | seed strings throughout `templates/`, `notification_service.py:158-170` | Medium |
| O2 | No empty-state coaching on the four dashboard tabs — first-day users see a blank table. | `Accounting/index.tsx`, `EFactura/UnallocatedTab.tsx` | Medium |
| O3 | All 20 blueprints reachable from the sidebar; good. But 25 hooks on `Accounting/index` (per CODEBASE_REVIEW C2) means the page is a power-user maze with no progressive disclosure. | `pages/Accounting/index.tsx` | Low |
| O4 | No in-app tour. With 200 users this is the difference between a 30-min onboarding and a 2-hour shadowing session. | n/a | Low |
| O5 | Status messages localised inconsistently. Lock message at `utils.py:70` is English; allocation labels are Romanian. | `hr/events/utils.py` | Low |

---

## 6. Recommended Roadmap (sequenced for 200-user readiness)

| Phase | Timeframe | Items |
|-------|-----------|-------|
| **0 — Stop the bleed** | This week | C3 (move SMTP to scheduler), C2 (raise DB pool), C1 (raise Gunicorn workers + scale to 2 instances), R1 (admin checks on user CRUD) |
| **1 — Front-of-house** | 1 sprint | F1 (paginate Accounting), F4 (centralise error mapping), R2 (role-aware dropdowns), E (OAuth banner) |
| **2 — Robustness** | 2 sprints | C4 (background AI parsing), F3 (optimistic locking + 409 toast), F2 (virtualised tables), H (HR grace-period flow) |
| **3 — Polish** | Ongoing | i18n consolidation, server-side preferences, in-app tour, virtualization on long lists |

Hitting Phase 0 + Phase 1 is the minimum bar to hand this platform to ~200 users without a reliability crisis. Phase 2–3 is where it stops being a tool the team tolerates and becomes one they enjoy.

---

## Appendix — Confidence & Method

Findings cite file:line evidence I read directly during this audit:

- `Procfile:1`, `Dockerfile:49`, `.do/app.yaml:7-8` — capacity
- `jarvis/database.py:21-77` — pool sizing & timeout behaviour
- `core/services/notification_service.py:128-137, 547-561` — sync SMTP loop
- `accounting/bugetare/invoice_parser.py:211–1380`, `bulk_processor.py:92,367,609,714` — sync AI calls
- `pages/Accounting/index.tsx:146-160`, `pages/EFactura/UnallocatedTab.tsx:61-62, 787-794` — pagination delta
- `hr/events/utils.py:39-102` — lock logic & admin bypass
- `core/connectors/efactura/repositories/invoice_repository.py:407, 644` — pagination good pattern
- `components/ErrorBoundary.tsx`, `main.tsx:128` — React error boundary scope
- `core/connectors/efactura/services/duplicate_service.py:174-189` — silent 500-row cap
- CODEBASE_REVIEW.md S1, S4, A2-A5 — pre-existing architecture findings cross-referenced

Items I deliberately did **not** verify and that should be re-checked before acting:
- Actual production query latencies and cache hit rates (the 99.95% in CODEBASE_REVIEW.md is current, not at 200-user load).
- Real SMTP latency with the configured provider.
- Whether DO managed Postgres has been upgraded since the 47-connection note was written.
