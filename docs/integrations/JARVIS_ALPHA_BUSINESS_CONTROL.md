# JARVIS alpha | BUSINESS CONTROL — Integration Guide

How the separate **JARVIS alpha** application (Next.js, isolated `jarvis_alpha`
database) authenticates users through **JARVIS** and authorizes access through
JARVIS's existing role / permission model.

> **Architecture invariants**
> - JARVIS is the single source of truth for **identity** and **authorization**.
> - JARVIS alpha keeps its financial data only in its own `jarvis_alpha` database.
> - Alpha **never** queries or modifies JARVIS's user database directly.
> - **No** password synchronization, **no** password-hash copying, **no**
>   hard-coded email allowlist.
> - Access is granted by the JARVIS permission **`business_control.access`**, not
>   by a role name. Alpha checks the permission result JARVIS returns.

---

## 1. Overview of the flow

```
                          (server-to-server, HTTPS)
  Browser ──login form──▶ JARVIS alpha (Next.js server) ──POST /api/auth/token──▶ JARVIS
     ▲                          │                                                    │
     │                          │◀──────────── { access_token, refresh_token } ──────┘
     │                          │
     │                          ├──GET /api/integrations/business-control/authorize──▶ JARVIS
     │                          │   Authorization: Bearer <access_token>              │
     │                          │◀──────────── { authorized, user, scope, ... } ──────┘
     │                          │
     └──Set-Cookie: alpha_session (Secure, HttpOnly, SameSite=Lax)──┘
```

1. The user submits email + password to **alpha's own server** (a Next.js Route
   Handler / Server Action — never from the browser directly to JARVIS).
2. Alpha's server calls JARVIS **`POST /api/auth/token`** with the credentials.
   This reuses JARVIS's existing password verification
   (`werkzeug.check_password_hash` via `UserRepository.authenticate_identifier`).
   Credentials are sent **only** to JARVIS's authentication service.
3. JARVIS returns a **short-lived JWT** (`access_token`, `refresh_token`), or an
   OTP challenge (see §2.1).
4. Alpha's server calls **`GET /api/integrations/business-control/authorize`**
   with `Authorization: Bearer <access_token>`.
5. On `authorized: true`, alpha mints **its own** session cookie (Secure,
   HttpOnly, SameSite) and discards the JARVIS tokens (or keeps the refresh token
   server-side only if it wants silent renewal). Passwords and password hashes
   are never stored in alpha.

Alpha's existing shared-password gate (`proxy.ts` Basic Auth) is replaced by this
per-user flow; keep `/api/health` open for platform probes.

---

## 2. JARVIS login request (identity)

### `POST /api/auth/token`

Request (JSON):

```json
{ "identifier": "user@example.com", "password": "••••••••", "device_id": "alpha-server" }
```

- `identifier` accepts an email (phone login is Viewer-only and not relevant here).
- `device_id` is an opaque, stable string identifying the alpha backend.

Immediate-success response (Viewer accounts, or a recognized trusted device):

```json
{ "access_token": "<JWT>", "refresh_token": "<JWT>", "expires_in": 3600 }
```

### 2.1 OTP / two-factor (non-Viewer accounts)

For normal business accounts (Manager, Admin, …) JARVIS enforces its existing
2FA. Instead of tokens you receive:

```json
{ "otp_required": true, "challenge_id": "<id>", "channel": "email" }
```

Complete it with **`POST /api/auth/verify-otp`**:

```json
{ "challenge_id": "<id>", "code": "123456", "device_id": "alpha-server" }
```

→ `{ "access_token", "refresh_token", "trusted_device_token" }`

Store the returned **`trusted_device_token`** server-side (per user) and send it
back as `trusted_device_token` on subsequent `/api/auth/token` calls to skip OTP
until it expires. This mirrors how the JARVIS mobile app avoids OTP on every
login. Rate limits: `/api/auth/token` and `/api/auth/verify-otp` are throttled to
10 requests / 5 min per IP (HTTP 429 on exceed).

> **Operator note:** decide how alpha surfaces the OTP step to end users (an OTP
> input screen, like the mobile app) or whether alpha logins run under a
> trusted-device token minted once per user. This is an integration decision on
> the alpha side — JARVIS's OTP behavior is unchanged.

---

## 3. Token & session handling

| Token | Lifetime | Purpose |
|-------|----------|---------|
| `access_token` (JWT, HS256) | 1 hour | Sent as `Authorization: Bearer` to the authorize endpoint |
| `refresh_token` (JWT, HS256) | 30 days | Exchange for a new access token, server-side only |

- Renew: **`POST /api/auth/refresh`** with `{ "refresh_token": "<JWT>" }` →
  `{ "access_token": "<JWT>" }`.
- The access token is a bearer credential: keep it **server-side** in alpha
  (Route Handler / Server Action memory or an encrypted server cookie). Never
  expose it to the browser and never put it in `localStorage`.
- Alpha's **own** session is independent of the JARVIS token lifetime — see §6.

---

## 4. Authorization request

### `GET /api/integrations/business-control/authorize`

Authenticates via the JARVIS **session cookie** *or* an
`Authorization: Bearer <access_token>` (the recommended server-to-server path).
JARVIS decides authorization through its `permissions_v2` model using the
**`business_control.access`** permission.

**200 — authorized:**

```json
{
  "authorized": true,
  "user": { "id": 123, "email": "user@example.com", "full_name": "Ada Lovelace" },
  "scope": { "tenant_id": null, "company_id": 2, "company": "DWA" },
  "permission": "business_control.access"
}
```

The response echoes **only** id / email / full_name and the scope. It never
returns password hashes, session secrets, tokens, or unrelated personal data.

**403 — insufficient permission** (authenticated but no grant, or a disabled
account), standard JARVIS envelope:

```json
{ "success": false, "error": "Permission denied" }
```

**401 — missing / invalid / expired authentication**, standard JARVIS envelope:

```json
{ "success": false, "error": "Authentication required" }
```

Alpha MUST treat only `HTTP 200` with `"authorized": true` as access. On `401`,
re-authenticate (refresh the token or send the user back to login). On `403`,
show "no access to Business Control" and do **not** create an alpha session.

### 4.1 Scope / isolation

JARVIS has **no separate tenant tier** — the **company** is the isolation
boundary. `tenant_id` is therefore always `null`; **isolate alpha's data by
`company_id`**. `company` is the human-readable company name for display. A caller
only ever receives their own company; there is no cross-company data in the
response.

---

## 5. How `business_control.access` is granted (JARVIS admin workflow)

The permission is seeded by JARVIS's migrations (module `business_control`, entity
`module`, action `access`; label **"JARVIS alpha | BUSINESS CONTROL"**). It is
assignable through the normal admin workflow — no code change needed:

- **Settings → Roles** in the JARVIS UI (the permission matrix), or
- API: `PUT /api/roles/<role_id>/permissions/v2`, or
  `PUT /api/permissions/v2/<permission_id>/role/<role_id>` with `{scope, granted}`.

**Default grants at seed time:** **Admin** and **Manager** (`granted`, scope
`all`); **User** and **Viewer** are denied. Operators can grant or revoke it for
any role afterward.

**Superadmin / admin behavior (explicit):** JARVIS has no separate superuser
account type; an "administrator" is a role with `can_access_settings`. JARVIS's
permission model treats such admins as all-access for every permission, and this
endpoint **honors that documented behavior** — an admin is authorized for
Business Control even without an explicit grant. To restrict Business Control to
specific people, use a dedicated non-admin role that holds `business_control.access`
and assign users to it.

---

## 6. Alpha's own session cookie

After a `200 { authorized: true }`, alpha creates its **own** session,
independent of JARVIS:

- `Set-Cookie` attributes: **`Secure; HttpOnly; SameSite=Lax; Path=/`** (use
  `SameSite=Strict` if alpha has no cross-site redirect needs).
- Store the session server-side (or as a signed, encrypted cookie). Persist at
  most: JARVIS `user.id`, `email`, `full_name`, `company_id` — never the password,
  never the JARVIS tokens in a browser-readable form.
- Session lifetime is alpha's decision. Re-verify with JARVIS (repeat §4) on a
  cadence appropriate to the sensitivity of the data (e.g. on login, then
  periodically or on privileged actions) so revoked JARVIS access propagates.

### Logout & expiration

- **Alpha logout:** clear the alpha session cookie. Optionally call JARVIS
  **`POST /api/auth/logout`** with the `refresh_token` to revoke it server-side.
- **Expiration:** when the JARVIS access token expires (1 h), refresh it (§3) or
  re-run the authorize check. If the JARVIS account is disabled or the grant is
  revoked, the next authorize call returns `403`/`401` — end the alpha session.

---

## 7. Environment variables

### JARVIS (identity provider) — already required in production

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET_KEY` (or `FLASK_SECRET_KEY`) | Signs/verifies the access & refresh JWTs. **Must be set in production** (JARVIS already hard-fails at boot otherwise). Never commit it. |
| `FLASK_SECRET_KEY` | Signs the Flask session cookie (web path). |

No **new** JARVIS environment variable is introduced by this integration.

### JARVIS alpha (consumer)

| Variable | Purpose |
|----------|---------|
| `JARVIS_BASE_URL` | Base URL of JARVIS, e.g. `https://jarvis.autoworld.ro` (production). |
| `JARVIS_DEVICE_ID` | Stable `device_id` string alpha sends to `/api/auth/token`. |
| `ALPHA_SESSION_SECRET` | Secret used to sign/encrypt alpha's own session cookie. |
| `DATABASE_URL` | Alpha's isolated `jarvis_alpha` database (unchanged). |

Provide all secrets as encrypted runtime variables (App Platform) or environment
files that are **never** committed. Do not place credentials in source, logs, or
PR text.

---

## 8. Production URL configuration

- Production JARVIS: **`https://jarvis.autoworld.ro`** → authorize endpoint:
  `https://jarvis.autoworld.ro/api/integrations/business-control/authorize`.
- Staging JARVIS: the staging App Platform URL (set `JARVIS_BASE_URL` accordingly
  in alpha's staging environment).
- Always use **HTTPS**. The token and authorize calls are server-to-server (from
  alpha's Next.js server), so no browser CORS is involved and JARVIS's CORS/CSRF
  posture is unchanged.

---

## 9. Reference: alpha server-side flow (illustrative)

```ts
// alpha: app/api/login/route.ts (Next.js Route Handler — runs on the server)
export async function POST(req: Request) {
  const { email, password } = await req.json();
  const base = process.env.JARVIS_BASE_URL!;

  // 1) Exchange credentials for a JARVIS token (server-to-server).
  const tokenRes = await fetch(`${base}/api/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier: email, password, device_id: process.env.JARVIS_DEVICE_ID }),
  });
  const tok = await tokenRes.json();
  if (tok.otp_required) return Response.json({ otp_required: true, challenge_id: tok.challenge_id }, { status: 200 });
  if (!tok.access_token) return Response.json({ error: 'Invalid credentials' }, { status: 401 });

  // 2) Authorize through JARVIS's permission model.
  const authRes = await fetch(`${base}/api/integrations/business-control/authorize`, {
    headers: { Authorization: `Bearer ${tok.access_token}` },
  });
  if (authRes.status === 401) return Response.json({ error: 'Auth expired' }, { status: 401 });
  if (authRes.status === 403) return Response.json({ error: 'No Business Control access' }, { status: 403 });
  const authz = await authRes.json(); // { authorized, user, scope, permission }

  // 3) Mint alpha's OWN session cookie; isolate data by scope.company_id.
  const cookie = await createAlphaSession({
    userId: authz.user.id, email: authz.user.email,
    fullName: authz.user.full_name, companyId: authz.scope.company_id,
  });
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { 'Set-Cookie': `alpha_session=${cookie}; Secure; HttpOnly; SameSite=Lax; Path=/` },
  });
}
```

*(Illustrative — no secrets. Do not log tokens or credentials.)*

---

## 10. Security checklist

- [x] Credentials flow only to JARVIS's existing auth service; no second password
      implementation.
- [x] Alpha receives only a short-lived token + an authorization result.
- [x] No password hashes / session secrets / DB credentials / tokens in the
      authorize response.
- [x] Alpha creates its own Secure / HttpOnly / SameSite session cookie.
- [x] No direct alpha access to JARVIS's `defaultdb`; no grants on user/role/
      session/password tables.
- [x] Authorization enforced by the `business_control.access` permission, not by a
      hard-coded role or email list.
- [x] JARVIS's existing web/mobile clients and auth behavior are unchanged.
