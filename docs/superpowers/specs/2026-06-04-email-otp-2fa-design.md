# Email OTP Two-Factor Authentication — Design Spec

**Date:** 2026-06-04
**Status:** Approved
**Scope:** JARVIS web login only (mobile JWT excluded)

---

## 1. Overview

Add mandatory Email OTP as a second authentication factor for all JARVIS web users. After entering a valid email + password, the user must enter a 6-digit code sent to their email before gaining access. A "Trust this device" mechanism allows skipping OTP for 30 days on the same browser.

## 2. Requirements

- **Mandatory for all users** — no opt-in/opt-out
- **Web login only** — mobile JWT auth (`/api/auth/token`) is unchanged
- **Trusted device cookie** — 30-day validity, skips OTP on recognized devices
- **Grace period on email failure** — retry button (max 3 sends), then block login
- **OTP expiry** — 5 minutes per code
- **Max wrong attempts** — 5 per code, then code is invalidated

## 3. Login Flow

```
User submits email + password on /login
    |
    v
Server validates credentials (existing logic)
    |
    +--> Invalid credentials → flash error, stay on /login (unchanged)
    |
    +--> Valid credentials → check trusted device cookie
            |
            +--> Cookie valid → login_user(), redirect to dashboard (unchanged)
            |
            +--> No cookie / expired / invalid:
                    |
                    1. Generate 6-digit OTP, store in otp_codes table (5 min TTL)
                    2. Send OTP to user's email via send_otp_email()
                    3. Store pending state in session:
                       session['otp_pending'] = {
                           'user_id': <id>,
                           'otp_id': <otp_codes.id>,
                           'remember': True/False,
                           'next_page': <url or None>,
                           'created_at': <timestamp>
                       }
                    4. Redirect to /login/verify
```

### /login/verify (GET)

- Renders `verify_otp.html` template
- Shows 6-digit input field, "Verify" button, "Resend code" button
- Displays remaining time until code expires (JS countdown)
- If no `session['otp_pending']` → redirect to /login

### /login/verify (POST)

```
User submits 6-digit code
    |
    v
Validate session['otp_pending'] exists and is < 10 min old
    |
    +--> Missing/expired session → redirect to /login with flash
    |
    v
Look up otp_codes row by otp_id
    |
    +--> Row not found or used_at is set → redirect to /login
    |
    +--> Row expired (now > expires_at) → flash "Code expired, request a new one"
    |
    +--> Row attempts >= 5 → flash "Too many wrong attempts, request a new code"
    |
    v
Compare submitted code with stored code
    |
    +--> Mismatch → increment attempts, flash "Invalid code"
    |
    +--> Match:
            1. Mark otp_codes row as used (set used_at = now)
            2. Load user, call login_user(user, remember=remember)
            3. Update last_login
            4. Log 'login' event
            5. Set trusted device cookie (30 days)
            6. Clear session['otp_pending']
            7. Redirect to next_page or dashboard
```

### /login/resend-otp (POST)

```
Check session['otp_pending'] exists
    |
    v
Look up current otp_codes row
    |
    +--> send_count >= 3 → flash "Maximum resend attempts reached. Please try again later."
    |                       Clear session, redirect to /login
    |
    v
Generate new 6-digit code, update the same row:
    - code = new code
    - expires_at = now + 5 min
    - attempts = 0
    - send_count += 1
    - used_at = NULL
    |
    v
Send email
    +--> Success → flash "New code sent", redirect to /login/verify
    +--> Failure → flash "Failed to send code. Try again."
                   If send_count now >= 3 → block (as above)
```

## 4. Database

### New table: `otp_codes`

```sql
CREATE TABLE otp_codes (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code        VARCHAR(6) NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    send_count  INTEGER NOT NULL DEFAULT 1,
    used_at     TIMESTAMP,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_otp_codes_user_id ON otp_codes(user_id);
```

No changes to the `users` table.

### Cleanup

Old OTP rows (> 1 hour) should be periodically cleaned. This can be done lazily: delete expired rows for the user when generating a new OTP.

## 5. Trusted Device Cookie

- **Cookie name:** `jarvis_trusted_device`
- **Payload:** Signed token containing `user_id` and `device_hash`
  - `device_hash` = SHA-256 of `User-Agent + first 3 octets of IP` (e.g., `192.168.1`)
  - Using first 3 octets allows the cookie to survive minor IP changes within the same network
- **Signing:** `itsdangerous.URLSafeTimedSerializer` using Flask's `SECRET_KEY`
- **Max age:** 30 days (2,592,000 seconds)
- **Cookie flags:** HttpOnly, Secure (production), SameSite=Lax
- **Validation:** On login, unsign the cookie → check max_age → compare user_id with authenticated user → compare device_hash with current request. All must match.
- **Invalidation:** Cookie is deleted on logout.

## 6. Email Template

Subject: `Jarvis — Your login verification code`

```html
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #333;">Login Verification Code</h2>
    <p>Hi {user_name},</p>
    <p>Your verification code is:</p>
    <div style="font-size: 32px; font-weight: bold; letter-spacing: 8px;
                color: #333; background: #f5f5f5; padding: 20px;
                text-align: center; border-radius: 8px; margin: 20px 0;">
        {code}
    </div>
    <p>This code expires in <strong>5 minutes</strong>.</p>
    <p>If you did not attempt to log in, please ignore this email
       and consider changing your password.</p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    <p style="color: #666; font-size: 12px;">
        This is an automated message from Jarvis.<br>
        Do not reply to this email.
    </p>
</body>
</html>
```

Sent via existing `send_email()` with `skip_global_cc=True`.

## 7. OTP Verify Page Template

File: `templates/core/verify_otp.html`

Consistent with existing login page styling (same base template, dark/light theme toggle). Contains:

- Title: "Enter verification code"
- Subtitle: "A 6-digit code has been sent to your email"
- Six-digit input field (single text input, `maxlength=6`, `pattern="[0-9]{6}"`, `inputmode="numeric"`, autofocus)
- "Verify" submit button
- "Resend code" link/button (POST to `/login/resend-otp`)
- JS countdown timer showing time remaining until code expires
- Flash message area (for errors, success messages)

## 8. Backend File Changes

| File | Changes |
|------|---------|
| `core/auth/routes.py` | Modify `login()`: after credential check, check trusted cookie → generate OTP → redirect. Add `verify_otp()` GET/POST route. Add `resend_otp()` POST route. Modify `logout()` to delete trusted device cookie. |
| `core/auth/services/auth_service.py` | Add `generate_otp(user_id) → (otp_id, code)`. Add `verify_otp(otp_id, code) → bool`. Add `create_trusted_device_cookie(user_id, request) → cookie_value`. Add `validate_trusted_device_cookie(cookie_value, user_id, request) → bool`. Add `send_otp_email(user_email, user_name, code) → (bool, str)`. |
| `core/auth/repositories/user_repository.py` | Add OTP methods: `create_otp(user_id, code, expires_at) → otp_id`. `get_otp(otp_id) → row`. `increment_otp_attempts(otp_id)`. `mark_otp_used(otp_id)`. `update_otp_code(otp_id, new_code, new_expires_at)`. `increment_otp_send_count(otp_id)`. `cleanup_expired_otps(user_id)`. |
| `templates/core/verify_otp.html` | New template (see section 7) |
| Migration (schema file) | Add `otp_codes` table creation |

## 9. Security Considerations

- **OTP is 6 random digits** (000000–999999), generated via `secrets.randbelow(1000000)`, zero-padded
- **Rate limiting:** Existing login rate limiter (10/5min per IP) applies before OTP generation. OTP verify has its own limit (5 wrong attempts per code, 3 resends per session)
- **Timing attacks:** Use `hmac.compare_digest()` for code comparison
- **Session fixation:** `session['otp_pending']` is cleared after successful verify or after 10 minutes
- **No code reuse:** `used_at` timestamp prevents replay
- **Trusted cookie scope:** Tied to user_id + device hash, signed with SECRET_KEY

## 10. What Does NOT Change

- Mobile JWT authentication (`/api/auth/token`, `/api/auth/refresh`)
- Password reset flow (`/forgot-password`, `/reset-password/<token>`)
- Flask-Login session mechanics
- Role and permission system
- User model / `users` table schema
- Frontend React SPA (OTP happens before SPA loads)
- Admin user management routes

## 11. Migration / Rollout

1. Deploy with the `otp_codes` table migration
2. Feature is immediately active for all users after deployment
3. All existing sessions remain valid (no forced re-login)
4. Users will encounter OTP on their next fresh login (no trusted cookie yet)
