# JARVIS Codebase Review — Full Audit Report

**Date:** February 16, 2026
**Reviewed by:** 4-agent team + 3-agent deep-dive verification
**Scope:** Full codebase — Flask backend, React frontend, database, deployment, tests

---

## Executive Summary

JARVIS is a **well-engineered internal tool with solid fundamentals** — consistent repository pattern, proper connection pooling, 560/560 passing tests, excellent TypeScript type safety (zero `any` escapes), and comprehensive React Query adoption. The codebase shows **reactive growth** that introduces security risks and some maintainability concerns:

| Area | Score | Verdict |
|------|-------|---------|
| **Security** | 5/10 | User CRUD has no admin checks, no CSRF, weak secret key fallback, no auth rate limiting |
| **Documentation** | 5/10 | Excellent CLAUDE.md but no API docs, setup guide, or architecture diagrams |
| **Architecture** | 7.5/10 | Clean patterns; statements routes exemplary, invoice routes need work |
| **Code Simplicity** | 8/10 | Better than initial assessment — major components properly extracted, good type safety |

**Top 3 actions** that would have the highest impact:
1. Fix security fundamentals (user CRUD auth, CSRF, secret key, rate limiting)
2. Create developer onboarding docs (SETUP.md, API.md, ARCHITECTURE.md)
3. Centralize error handling and add request validation to invoice routes

---

## 1. Security Findings (Verified)

### Critical

| # | Issue | File:Line | Verified Evidence |
|---|-------|-----------|-------------------|
| S1 | **User CRUD has no admin checks** | `core/auth/routes.py:38-121` | Create, Update, Delete, Bulk Delete user endpoints only have `@login_required` — any authenticated Viewer can create admin accounts, delete users, or elevate their own role. `set-password` endpoint (line 241) correctly checks `can_access_settings`, proving the pattern exists but wasn't applied to CRUD. |
| S2 | **Weak default secret key** | `app.py:36` | `os.environ.get('FLASK_SECRET_KEY', os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production'))` — hardcoded fallback. No startup validation. DigitalOcean likely sets the env var, but no enforcement. |

### High

| # | Issue | File:Line | Verified Evidence |
|---|-------|-----------|-------------------|
| S3 | **No auth rate limiting** | `app.py:206-307` | Login, forgot-password, reset-password — zero rate limiting. `RateLimiter` class exists in `statements/routes.py` but only applied to bulk operations. |
| S4 | **Error messages leak DB internals** | 48+ instances across routes | Generic `except Exception as e: return jsonify({'error': str(e)}), 500` pattern. Leaks psycopg2 errors, constraint names, SQL fragments. Worst in `invoices/routes.py` and `bugetare/routes.py`. |
| S5 | **Session cookies partially configured** | `app.py:48-53` | `REMEMBER_COOKIE_SECURE/HTTPONLY/SAMESITE` set correctly, but `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE` are **NOT set** — Flask defaults to `False`/`None`. |

### Medium

| # | Issue | Verified Status |
|---|-------|-----------------|
| S6 | No CSRF protection | **MEDIUM** (not Critical) — `credentials: 'same-origin'` in React client + `SameSite=Lax` cookies provide partial mitigation. Not ideal but not wide open. |
| S7 | Debug mode defaults to true | **LOW** — only affects `__main__` (line 492). Gunicorn in production ignores this. Local dev risk only. |
| S8 | File upload: extension check only | `statements/routes.py:224` checks `.endswith('.pdf')` — no MIME validation. |
| S9 | Weak password policy (6 chars) | `app.py:358` — NIST recommends 8+. |
| S10 | No CSP/X-Frame-Options headers | Missing security headers. |
| S11 | Password hashing uses PBKDF2 | Werkzeug `generate_password_hash()` uses PBKDF2-SHA256 (acceptable, not bcrypt/argon2). |

### Corrected: False Positives from Initial Report

| Original Claim | Verdict |
|----------------|---------|
| "SQL Injection via f-strings" | **FALSE POSITIVE** — All 48 f-string SQL patterns use code-controlled field names (`'name = %s'`), never user input. User data always goes through `%s` parameterization. Safe. |
| "Passwords hashed with bcrypt" | **Inaccurate** — Werkzeug uses PBKDF2-SHA256, not bcrypt. Still acceptable. |

### Positive Security Findings

- All SQL queries use parameterized `%s` placeholders (verified across 5 repositories)
- Passwords hashed with Werkzeug PBKDF2-SHA256 + salt
- `REMEMBER_COOKIE_SECURE=True`, `REMEMBER_COOKIE_HTTPONLY=True`
- No `eval()`, `exec()`, `subprocess`, `os.system()` calls
- No `dangerouslySetInnerHTML` in React source
- Proper `.gitignore` excludes `.env`, credentials, tokens
- Rate limiting exists on bulk statement operations
- `api_login_required` decorator returns JSON 401 (not redirect) for API routes

---

## 2. Documentation Findings

*(Unchanged from initial report — not re-verified)*

### What Exists Today

| Document | Size | Quality |
|----------|------|---------|
| `README.md` | 3.7 KB | Good overview, tech stack, quick start |
| `docs/CLAUDE.md` | 68 KB (1,525 lines) | Excellent but monolithic |
| `docs/USER_GUIDE.md` | 340 lines | Good end-user workflows |
| `docs/CHANGELOG.md` | Present | Release notes |
| Python docstrings | ~39 repo classes | Module-level docstrings on most files |
| TypeScript types | 13 type files | Comprehensive interface exports |

### Critical Gaps

| # | Missing Doc | Impact | Effort |
|---|-------------|--------|--------|
| D1 | **`docs/SETUP.md`** | New dev can't start without asking someone | 2h |
| D2 | **`docs/API.md`** | 70+ endpoints undiscoverable | 2-3h |
| D3 | **`docs/ARCHITECTURE.md`** | No diagrams | 3-4h |
| D4 | **`CONTRIBUTING.md`** | Workflow scattered in CLAUDE.md | 1.5h |
| D5 | **Env var reference** | Required vs optional unknown | 30min |
| D6 | **Permission matrix** | Permissions scattered across code | 1h |
| D7 | **Operations runbook** | No "how to" for common ops | 2h |

---

## 3. Architecture Findings (Verified)

### Current Architecture

```
Frontend (React 19 + Vite)
  Pages → Zustand Stores → API Client Layer → Shared Components
    ↕ HTTP (JSON) / Auth (Flask-Login)
Backend (Flask)
  17 Blueprints → ~30 Repositories → Domain Services
    ↕ PostgreSQL (47 connection limit)
Database (24 MB, 99.95% cache hit ratio)
```

### Strengths (Verified)

- **Consistent repository pattern**: Every repo follows `get_db()` → query → `release_db(conn)` in finally block
- **Smart connection pooling**: ThreadedConnectionPool with timeout, stale detection, auto-retry (3x)
- **React Query adoption**: **186 useQuery instances across 36 files** — comprehensive, modern patterns throughout. No raw `useEffect+fetch` found in spot checks.
- **TypeScript type safety**: **Zero `as any`, `@ts-ignore`, or `@ts-expect-error`** in entire frontend. All API responses properly typed.
- **Component decomposition**: EditInvoiceDialog, SummaryTable, AllocationEditor all properly extracted as imports (not inline)
- **Zustand stores**: Minimal, focused, no god stores
- **Statements routes exemplary**: Explicit validation (`get_json_or_error()`, `validate_regex()`), proper HTTP semantics (401/409/422/429)

### Concerns (Verified)

| # | Issue | Verified Evidence | Severity |
|---|-------|-------------------|----------|
| A1 | ~~Duplicate e-Factura~~ | **RESOLVED** — dead code deleted | N/A |
| A2 | **Business logic in invoice routes** | `invoices/routes.py:34-47` has `_user_can_set_status()` permission logic; lines 99-120 have notification orchestration + auto-tag evaluation. Statements routes are clean by comparison. | High |
| A3 | **No centralized error handler** | No `@app.errorhandler` in `app.py`. Error formats inconsistent: `{'success': False, 'error': ...}` (109+ occurrences) vs `{'error': ...}` (many). Status codes vary: statements uses 401/422/429; invoices uses 400/403/500. | High |
| A4 | **Weak request validation in invoices** | `invoices/routes.py:75`: `data = request.json` then `data['supplier']` with no null check (KeyError risk). Statements routes use `get_json_or_error()` helper — pattern exists but not applied everywhere. | High |
| A5 | **Permission coverage gaps** | Invoice routes: 14 permission checks across 49 routes (~29%). Summary routes, search routes, comment/drive-link updates have no checks. | Medium |

### Corrected: Overstated Claims

| Original Claim | Actual Finding |
|----------------|----------------|
| "React Query used inconsistently" | **Wrong** — 186 useQuery instances across 36 files. Adoption is comprehensive. |
| "No frontend schema validation" | **Partially true** — types are cast with `as T`, but TypeScript catches most mismatches at compile time. Zero type escapes found. |
| "ai_agent_service.py needs decomposition" | **Overstated** — 16 methods, all cohesive (conversation lifecycle + AI orchestration). Well-organized. |
| "efactura_service.py: 18 methods" | **Understated** — actually 47 methods. Could split into 3-4 services but not urgent. |

---

## 4. Code Simplicity Findings (Verified)

**Overall Readability Score: 8/10** — Better than initial assessment after verification.

### Complexity Hotspots (Verified Measurements)

| # | File | Actual Lines | Actual Hooks | Actual Dialogs Inline | Notes |
|---|------|-------------|-------------|----------------------|-------|
| C1 | `UnallocatedTab.tsx` | **1,142** | 10 useState, 2 useMemo, 6 useQuery, 5 useMutation | **2** (not 5) | View Details (76 lines) + Edit Overrides (195 lines). ColumnToggle is separate component in same file. |
| C2 | `Accounting/index.tsx` | **1,082** | **25 total** (7 useState, 7 useQuery, 3 useMutation, 7 useMemo, 1 useCallback) | **2** (ConfirmDialogs) | EditInvoiceDialog, SummaryTable, AllocationEditor all **imported** (not inline). InvoiceTable + InvoiceRow are memoized sub-components. |
| C3 | `efactura_service.py` | **2,252** | N/A | N/A | **47 methods** (not 18). 9 responsibility groups. Organized but large. |
| C4 | `ai_agent_service.py` | **863** | N/A | N/A | 16 methods. **Well-cohesive** — no split needed. |
| C5 | `invoice_repository.save()` | **116 lines** | N/A | N/A | 14 params, 4 SQL statements (insert invoice, select managers, insert allocations, insert reinvoice). Complexity is inherent to domain. |

### Code Duplication (Verified)

| Pattern | Instances | Consolidation | Priority |
|---------|-----------|---------------|----------|
| **Date formatting** | **7 implementations** across 6 files (`fmtDate`, `formatDate`, `formatDateTime` — all slightly different) | Extract to `lib/date-utils.ts` — 3 functions | **High** (40 LOC saved) |
| **Column persistence** | 2 implementations (UnallocatedTab + accountingStore) with different validation logic | Shared `useColumnPersistence` hook | Medium |
| SQL WHERE clause building | 5+ repos, similar but not identical | `QueryBuilder` utility possible but low ROI | Low |

### Corrected: Overstated Claims

| Original Claim | Actual Finding |
|----------------|----------------|
| "5 inline dialogs in UnallocatedTab" | **2 inline dialogs**. Others are imported shared components (ConfirmDialog, TagPickerButton). |
| "21 hooks in Accounting/index" | Actually **25 hooks** — claim was understated. |
| "EditInvoiceDialog inline in Accounting" | **Imported** from separate file (line 56: `import { EditInvoiceDialog } from './EditInvoiceDialog'`). |
| "useState explosion (10+)" | UnallocatedTab has 10 useState, Accounting has 7. Reasonable for complex pages. |
| "Magic numbers scattered" | **Not found** in React code. Frontend is clean. Legacy Jinja2 has some but those are out of scope. |

---

## 5. Cross-Team Insights (Updated)

### Confirmed by Deep-Dive

- **User CRUD authorization bypass** — CRITICAL. Any authenticated user can manage all users. Verified at `auth/routes.py:38-121`.
- **Error handling inconsistency** — 109+ occurrences of `{'success': False, 'error': str(e)}`. No `@app.errorhandler`. Statements routes use proper HTTP semantics; invoices don't.
- **Request validation split** — Statements routes have explicit validation (`get_json_or_error()`); invoice routes trust `request.json` blindly.

### Corrected After Deep-Dive

- ~~React Query inconsistency~~ — **Actually well-adopted** (186 instances, 36 files)
- ~~TypeScript type gaps~~ — **Zero type escapes found**
- ~~Large service files problematic~~ — `ai_agent_service.py` is well-cohesive; only `efactura_service.py` could benefit from splitting (not urgent)
- ~~5 inline dialogs~~ — Actually 2 per large component, with major dialogs properly imported

---

## 6. Prioritized Action Plan

### Phase 1: Security Hardening (1-2 days)

| Task | Effort | Impact |
|------|--------|--------|
| **Add admin checks on user CRUD endpoints** (`auth/routes.py:38-121`) | 30 min | **Critical** |
| Enforce `FLASK_SECRET_KEY` — fail on startup if unset | 15 min | Critical |
| Add `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE` config | 5 min | High |
| Sanitize error responses (replace `str(e)` with generic messages) | 2h | High |
| Add rate limiting on login/forgot-password (`flask-limiter`) | 1h | High |
| Add CSRF protection via Flask-WTF | 2h | Medium |
| Set `FLASK_DEBUG` default to `false` | 5 min | Low |
| Add security headers (CSP, X-Frame-Options) | 30 min | Medium |

### Phase 2: Documentation (2-3 days)

| Task | Effort | Impact |
|------|--------|--------|
| Create `docs/SETUP.md` with step-by-step local dev setup | 2h | High |
| Create `docs/API.md` with endpoint reference table | 3h | High |
| Create `docs/ARCHITECTURE.md` with Mermaid diagrams | 3h | High |
| Create `CONTRIBUTING.md` at repo root | 1.5h | High |
| Add environment variable reference table | 30 min | Medium |
| Create permission matrix (Role x Feature) | 1h | Medium |

### Phase 3: Code Quality (1-2 sprints)

| Task | Effort | Impact |
|------|--------|--------|
| ~~Merge duplicate e-Factura~~ | **DONE** | Dead code deleted |
| Centralize error handling (`@app.errorhandler` + consistent response format) | 3-4 days | High |
| Add request validation to invoice routes (match statements pattern) | 2-3 days | High |
| Extract date formatting to `lib/date-utils.ts` | 1h | Medium |
| Create shared `useColumnPersistence` hook | 1h | Medium |
| Extract 2 inline dialogs from UnallocatedTab to separate files | 2h | Low |

### Deprioritized (Not Urgent After Verification)

| Task | Reason |
|------|--------|
| Split `ai_agent_service.py` | Well-cohesive, 16 methods, no split needed |
| Use React Query consistently | Already adopted (186 instances, 36 files) |
| Add frontend schema validation | Zero type escapes — TypeScript catches mismatches |
| Extract AllocationEditor from Accounting | Already imported from separate file |

---

## 7. Summary Scorecard

| Category | Current | After Phase 1-2 | After Phase 3 |
|----------|---------|-----------------|---------------|
| Security | 5/10 | 8/10 | 9/10 |
| Documentation | 5/10 | 8/10 | 8/10 |
| Architecture | 7.5/10 | 7.5/10 | 9/10 |
| Code Simplicity | 8/10 | 8/10 | 9/10 |
| **Overall** | **6.4/10** | **7.9/10** | **8.8/10** |

Phase 1 (security) is urgent — the user CRUD authorization bypass is the single biggest risk. Phase 2 (docs) enables team scaling. Phase 3 (error handling + validation) brings invoice routes up to the quality level that statements routes already demonstrate.
