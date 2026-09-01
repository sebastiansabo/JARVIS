# Design — Mandatory Consent-Documents Gate ("Acorduri obligatorii")

**Date:** 2026-08-26
**Author:** Sebastian Sabo (+ Claude)
**Status:** Approved — implementation in progress
**Repos:** `JARVIS` (Flask backend + React web, includes Hub) · `jarvis-mobile-2` (Capacitor + React)
**Base branch:** `staging` (feature/consent-gate)

---

## 1. Summary

On the **first login ever**, before a user can use JARVIS on **any** surface (web, Hub, mobile-2), they are stopped by a full-screen blocker and must **read + acknowledge + draw a signature** on **three mandatory legal documents**:

1. **Acord privind utilizarea datelor de contact** (data-usage / communication)
2. **Notă de informare și acord GDPR** (per RO law: Reg. (UE) 2016/679 + Legea nr. 190/2018)
3. **Acord de confidențialitate (NDA)**

Until all three carry an accepted + signed record for that user, the app content never renders — the only escape is **Logout**. The signed status is visible on the user's profile, and HR gets a compliance dashboard of who has / hasn't signed.

Rather than hard-code three agreements, we build a small **generic consent-documents module**: the three documents are seed rows in a table; a 4th later is a DB row + text, not a code change. Text is **admin-editable in Settings**.

## 2. Locked decisions

| # | Decision | Value |
|---|----------|-------|
| 1 | Acceptance mechanism | Checkbox **"Am citit și sunt de acord"** + **drawn signature** — on **all three** docs |
| 2 | Text scope | **Single global** text (same for every user / company) |
| 3 | Versioning | **Sign once, ever** — editing text does **not** force existing signers to re-sign in v1 (version+hash stored for future) |
| 4 | Text management | **Admin-editable** in Settings (stored in DB) |
| 5 | Oversight | **HR compliance dashboard** (who signed / pending) |
| 6 | Legal copy | **Placeholders** for GDPR + NDA (DPO/legal finalize); data-usage seeded from the provided Connecteam example, adapted to JARVIS |
| 7 | Documents | **3** (data_usage, gdpr, nda) — extensible |
| 8 | Block behavior | **All three must be Accepted** — no "Nu"; refusing = cannot use JARVIS |
| 9 | Signature | **All three require a drawn signature** |

## 3. Goals / Non-goals

**Goals**
- No user can reach any authenticated screen without all mandatory documents signed.
- Audit-grade record per signature: who, when, which document version, signature image, IP, user-agent, hash of the exact text signed.
- Admins edit document text; HR sees compliance; users re-read what they signed.
- One gate mechanism reused verbatim on web (covers Hub) and mobile-2.

**Non-goals (v1)**
- Re-consent when admin edits text (deferred; schema is ready for it).
- Per-company / per-role document variants (single global only).
- Mobile-side document editing or HR dashboard (admins use web).
- Legacy surfaces `jarvis-mobile`, `jarvis-mobile-3`, `jarvis-mobile-chat` (out of scope).

## 4. Data model (2 new tables — `users` table untouched)

Keying signatures by `user_id` in a **separate table** means we **do not alter the protected `users` schema at all**. Both `CREATE TABLE`s + seeds live in `jarvis/migrations/domains/schema_incremental.py`, which is **already wired** into `init_schema.create_schema_incremental()` — so **no `init_schema.py` change either**. Only one protected file is touched.

```sql
CREATE TABLE IF NOT EXISTS consent_documents (
    id                 SERIAL PRIMARY KEY,
    doc_key            TEXT    NOT NULL UNIQUE,        -- 'data_usage' | 'gdpr' | 'nda'
    title              TEXT    NOT NULL,
    body               TEXT    NOT NULL DEFAULT '',    -- admin-editable (markdown/rich text)
    sort_order         INTEGER NOT NULL DEFAULT 0,     -- wizard order
    requires_signature BOOLEAN NOT NULL DEFAULT TRUE,
    is_mandatory       BOOLEAN NOT NULL DEFAULT TRUE,  -- counts toward the gate
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    version            INTEGER NOT NULL DEFAULT 1,     -- bumped on body edit (future re-consent)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by         INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS user_consent_signatures (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id      INTEGER NOT NULL REFERENCES consent_documents(id) ON DELETE CASCADE,
    document_version INTEGER NOT NULL DEFAULT 1,       -- version signed
    response         TEXT    NOT NULL DEFAULT 'accepted'
                             CHECK (response IN ('accepted','declined')),  -- 'declined' reserved
    signature_image  TEXT,                             -- base64 PNG data URL
    document_hash    TEXT,                             -- sha256 hex of signed body (integrity)
    ip_address       TEXT,
    user_agent       TEXT,
    signed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, document_id)                      -- one signature per user per doc
);
CREATE INDEX IF NOT EXISTS idx_ucs_user     ON user_consent_signatures(user_id);
CREATE INDEX IF NOT EXISTS idx_ucs_document ON user_consent_signatures(document_id);
```

> **Storage choice considered:** reuse the existing generic `document_signatures` table (`document_type='consent'`). Rejected for v1 — it has no `response`, no link to a versioned document catalog, and is coupled to the foi-parcurs/forms signing-request flow. The dedicated table is self-contained; the audit fields (ip/hash/signed_at) it needs are trivial. `document_signatures` remains the fallback if a single signature store is later preferred.

**Gate signal** = `count(active mandatory docs)` == `count(user's accepted signatures for active mandatory docs)`. If not equal → blocked.

## 5. Backend

New blueprint `consents_bp` (registered in `jarvis/app.py:_register_blueprints`). Module `jarvis/core/consents/` (routes / services / repositories), mirroring existing module layout.

### 5.1 User-facing (`@login_required`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/consents/pending` | `{ complete: bool, pending: [{id, doc_key, title, body, version, requires_signature}] }` in `sort_order`. |
| POST | `/api/consents/sign` | Body `{document_id, signature_image}`. **`user_id` taken from `current_user` server-side (never the client — IDOR guard).** Validates doc active+mandatory, requires non-empty signature when `requires_signature`, computes `document_hash`, captures IP + user-agent, upserts `user_consent_signatures` (idempotent via UNIQUE). Returns `{ complete, pending_count }`. |
| GET | `/api/consents/documents/:docKey` | Read-only fetch of one active document (for the "re-read" viewer route). |
| GET | `/api/consents/mine` | Current user's signed docs + `signed_at` (profile section). |

### 5.2 Admin — Settings editor (`@v2_permission_required('settings','consents',...)`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/consents/documents` | All documents (incl. inactive) for the editor. |
| POST | `/api/consents/documents` | Create a new document. |
| PUT | `/api/consents/documents/:id` | Edit `title/body/sort_order/is_active`; **bumps `version` when `body` changes**. |

### 5.3 HR — compliance (`@v2_permission_required('hr','consents','view')`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/consents/compliance` | Per-user × per-document matrix: `[{user_id, name, email, company, documents: [{doc_key, signed, signed_at}]}]`; supports `?status=pending`. Backing a table + CSV export. |

### 5.4 "me" endpoints — the gate flag
Add `consents_complete: bool` and `pending_consents_count: int` to:
- `GET /api/auth/current-user` — `jarvis/core/auth/routes.py:api_current_user`
- `GET /api/mobile/current-user` — mobile mirror

So the frontend gate reads the flag with **zero extra round-trips** on login/session-restore; it calls `/pending` only when it needs the document bodies to render.

### 5.5 Mobile
Mirror endpoints under `/api/mobile/consents/*` (`pending`, `sign`) for the JWT/CORS path. **Add the new routes/methods to `app.py:_mobile_cors` allow-methods** (known CORS gotcha — new Capacitor endpoints must be listed).

## 6. Frontend — Web (covers Hub)

1. **Blocker** — in `jarvis/frontend/src/components/Layout.tsx`, right after `if (!user) → /login` (≈:75): `if (user.consents_complete === false) return <ConsentGate />;` before `<Outlet/>`. One insertion covers **Hub, Dashboard, and every `/app/*`** uniformly.
2. **`<ConsentGate />`** — full-screen (`fixed inset-0`, high z-index) **stepper**. Per pending document, in order: scrollable rendered body → **"Am citit și sunt de acord"** checkbox (enabled only after scroll-to-bottom) → `<SignatureCanvas onSave>` → **"Semnează și continuă"** → POST `/sign`, advance. Progress "Document 1 din 3". Only way out = **Logout**.
3. **Re-read route** `/app/acorduri` (list) + `/app/acord/:docKey` (single) — read-only viewer. Linked from Profile + app footer.
4. **Settings → new tab "Acorduri (documente legale)"** (admin-gated) — list documents; edit title/body, toggle `is_active`, reorder. Save bumps `version`.
5. **HR compliance dashboard** — table users × documents (signed ✓ / pending), filter pending, CSV export.
6. **Profile** — "Acorduri semnate" section: each document + `signed_at` + link to re-view.

## 7. Frontend — Mobile-2 (blocker + sign only)

- **Blocker** — in `src/App.tsx:ProtectedRoute` (≈:50): `if (isAuthenticated && user?.consents_complete === false) return <ConsentGate/>;`.
- **`<ConsentGate/>`** — full-screen, modeled on `src/pages/Sales/TestDrive/GdprNoticeModal.tsx`; reuse existing `src/components/shared/SignatureCanvas.tsx` + `src/hooks/useSignaturePad.ts`.
- **Hooks** in `src/hooks/useApi.ts`: `usePendingConsents()`, `useSignConsent()`. Surface `consents_complete` on the `User` via `authStore.extractPermissions`.
- **Ship ritual:** changelog entry, then `npm run build && npx cap sync android`, wait for APK CI, promote.

## 8. Seed data (v1)

Seeded idempotently (`INSERT ... ON CONFLICT (doc_key) DO NOTHING`). **Shipped `is_active = FALSE`** (see Rollout §11) so placeholder text never blocks real users; flipped active once legal copy is approved.

- **`data_usage`** — adapted from the provided Connecteam example to JARVIS/Autoworld.
- **`gdpr`** — structured placeholder referencing Reg. (UE) 2016/679 + Legea nr. 190/2018, marked `‹DE COMPLETAT DPO›`.
- **`nda`** — structured NDA placeholder, marked `‹DE COMPLETAT — juridic›`.

**No binding legal text is authored.** Placeholders carry structure + legal-basis references only.

## 9. Security

- **IDOR guard:** `/sign` uses `current_user.id` server-side.
- **Admin/HR gates:** editor + compliance behind `@v2_permission_required`.
- **Signature validation:** must be `data:image/png;base64,`; size cap (~500 KB); reject empty when `requires_signature`.
- **Integrity:** `document_hash` binds the signature to the exact bytes signed.
- **Rate-limit** `/sign` lightly.

## 10. Edge cases

- Fully-signed user → gate never renders.
- New mandatory document added later → gate reappears for that one document (a new obligation).
- Admin edits an existing doc's body → v1 does **not** force re-sign; gate checks existence, not version. `version` bump recorded for future.
- Deactivating a doc → drops from pending; gate recomputes.
- Empty signature submit → 400. Concurrent double-submit → UNIQUE no-op.

## 11. Rollout & deployment

- On deploy, seed docs are `is_active=FALSE` — gate dormant until an admin finalizes text and flips active. Controlled go-live with real legal copy.
- Backend + web: `feature/consent-gate` → validate → `staging` → `main` (double confirmation), per CLAUDE.md branch workflow.
- Mobile-2: changelog → `npm run build && npx cap sync android` → APK CI → promote.

## 12. Open items / needs input

1. **Legal text** — DPO finalizes GDPR; legal finalizes NDA; confirm the adapted data-usage copy.
2. **v2 permission entities** — confirm seed for `('settings','consents',...)` and `('hr','consents','view')`.
3. **Legal caveat (DPO):** making the *data-usage consent* a hard condition of using JARVIS is not "freely given consent" under GDPR — for an employer-provided internal tool this is normally a **different legal basis** (contract / legitimate interest). Worth a DPO sign-off on framing.

## 13. Testing (TDD)

- **Backend (pytest):** repository (pending computation, sign idempotency, compliance), routes (IDOR guard, admin/HR gates, `consents_complete`, empty-signature 400, inactive-doc rejection).
- **Web:** `npm run build` typecheck + Playwright/manual gate behavior.
- **Mobile-2 (vitest):** gate shows when `consents_complete=false`, sign posts, refetch clears.
