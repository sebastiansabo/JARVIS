# Email OTP Two-Factor Authentication — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add mandatory Email OTP 2FA to all JARVIS web logins, with a 30-day trusted device cookie to reduce friction.

**Architecture:** Session-based OTP flow. After password validation, store pending state in Flask session, redirect to `/login/verify`. OTP codes stored in `otp_codes` DB table (5-min TTL, max 5 attempts, max 3 sends). Trusted device uses a signed cookie (itsdangerous) with 30-day expiry. Mobile JWT auth is untouched.

**Tech Stack:** Flask, Flask-Login, itsdangerous, psycopg2, Jinja2, existing SMTP via `notification_service.send_email()`

**Spec:** `docs/superpowers/specs/2026-06-04-email-otp-2fa-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `jarvis/migrations/domains/schema_misc.py` | Modify | Add `otp_codes` table creation |
| `jarvis/core/auth/repositories/user_repository.py` | Modify | Add OTP CRUD methods (create, get, increment, mark used, update, cleanup) |
| `jarvis/core/auth/services/auth_service.py` | Modify | Add OTP generation, verification, email sending, trusted cookie logic |
| `jarvis/core/auth/routes.py` | Modify | Modify `login()`, add `verify_otp()`, `resend_otp()` routes, modify `logout()` |
| `jarvis/templates/core/verify_otp.html` | Create | OTP verification page template |
| `tests/test_otp.py` | Create | Unit tests for OTP service and repository methods |

---

### Task 1: Database Migration — `otp_codes` Table

**Files:**
- Modify: `jarvis/migrations/domains/schema_misc.py` (end of `create_schema_misc` function)

- [ ] **Step 1: Add `otp_codes` table to migration**

In `jarvis/migrations/domains/schema_misc.py`, add this block at the end of the `create_schema_misc(conn, cursor)` function, before the final `conn.commit()` if any, or as the last `cursor.execute(...)` block:

```python
    # OTP codes for two-factor authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS otp_codes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code VARCHAR(6) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            send_count INTEGER NOT NULL DEFAULT 1,
            used_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_otp_codes_user_id ON otp_codes(user_id)
    ''')
```

- [ ] **Step 2: Verify migration runs locally**

Run the JARVIS app locally or invoke the migration runner to verify the table is created without errors. Check with:

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis
python -c "
from jarvis.migrations.domains.schema_misc import create_schema_misc
print('Migration function loads OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/migrations/domains/schema_misc.py
git commit -m "feat(auth): add otp_codes table migration for email OTP 2FA"
```

---

### Task 2: OTP Repository Methods

**Files:**
- Modify: `jarvis/core/auth/repositories/user_repository.py` (add methods after the password reset token methods, around line 155)
- Create: `tests/test_otp.py`

- [ ] **Step 1: Write failing tests for OTP repository methods**

Create `tests/test_otp.py`:

```python
"""Tests for OTP repository and service methods."""
import secrets
import hmac
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock


class TestOTPGeneration:
    """Test OTP code generation."""

    def test_generate_otp_returns_6_digit_string(self):
        """OTP must be exactly 6 digits, zero-padded."""
        from core.auth.services.auth_service import AuthService
        svc = AuthService.__new__(AuthService)
        code = svc._generate_otp_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_otp_is_zero_padded(self):
        """Codes like 000042 must preserve leading zeros."""
        from core.auth.services.auth_service import AuthService
        svc = AuthService.__new__(AuthService)
        with patch('secrets.randbelow', return_value=42):
            code = svc._generate_otp_code()
            assert code == '000042'

    def test_generate_otp_max_value(self):
        """Maximum code is 999999."""
        from core.auth.services.auth_service import AuthService
        svc = AuthService.__new__(AuthService)
        with patch('secrets.randbelow', return_value=999999):
            code = svc._generate_otp_code()
            assert code == '999999'


class TestOTPVerification:
    """Test OTP code comparison uses timing-safe comparison."""

    def test_verify_uses_hmac_compare_digest(self):
        """Code comparison must use hmac.compare_digest to prevent timing attacks."""
        from core.auth.services.auth_service import AuthService
        svc = AuthService.__new__(AuthService)
        with patch('hmac.compare_digest', return_value=True) as mock_cmp:
            result = svc._compare_otp('123456', '123456')
            mock_cmp.assert_called_once_with('123456', '123456')
            assert result is True

    def test_verify_wrong_code_returns_false(self):
        """Wrong code returns False."""
        from core.auth.services.auth_service import AuthService
        svc = AuthService.__new__(AuthService)
        result = svc._compare_otp('123456', '654321')
        assert result is False


class TestTrustedDeviceHash:
    """Test device hash generation."""

    def test_device_hash_uses_user_agent_and_ip_prefix(self):
        """Device hash should combine User-Agent and first 3 octets of IP."""
        from core.auth.services.auth_service import AuthService
        svc = AuthService.__new__(AuthService)
        hash1 = svc._compute_device_hash('Mozilla/5.0 Linux', '192.168.1.100')
        hash2 = svc._compute_device_hash('Mozilla/5.0 Linux', '192.168.1.200')
        # Same /24 network → same hash
        assert hash1 == hash2

    def test_device_hash_differs_for_different_network(self):
        """Different /24 networks should produce different hashes."""
        from core.auth.services.auth_service import AuthService
        svc = AuthService.__new__(AuthService)
        hash1 = svc._compute_device_hash('Mozilla/5.0 Linux', '192.168.1.100')
        hash2 = svc._compute_device_hash('Mozilla/5.0 Linux', '10.0.0.100')
        assert hash1 != hash2

    def test_device_hash_differs_for_different_user_agent(self):
        """Different user agents should produce different hashes."""
        from core.auth.services.auth_service import AuthService
        svc = AuthService.__new__(AuthService)
        hash1 = svc._compute_device_hash('Mozilla/5.0 Linux', '192.168.1.100')
        hash2 = svc._compute_device_hash('Chrome/120.0', '192.168.1.100')
        assert hash1 != hash2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis
python -m pytest tests/test_otp.py -v
```

Expected: FAIL — `_generate_otp_code`, `_compare_otp`, `_compute_device_hash` do not exist yet.

- [ ] **Step 3: Add OTP CRUD methods to UserRepository**

In `jarvis/core/auth/repositories/user_repository.py`, add these methods after `delete_expired_tokens()` (around line 155), before the `# --- User CRUD Methods ---` comment:

```python
    # --- OTP Methods ---

    def create_otp(self, user_id: int, code: str, expires_at: datetime) -> Optional[int]:
        """Create an OTP code for a user. Cleans up old OTPs first."""
        def _work(cursor):
            # Cleanup expired/used OTPs for this user
            cursor.execute('''
                DELETE FROM otp_codes
                WHERE user_id = %s AND (used_at IS NOT NULL OR expires_at < CURRENT_TIMESTAMP)
            ''', (user_id,))
            # Also invalidate any active unused OTPs
            cursor.execute('''
                UPDATE otp_codes SET used_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND used_at IS NULL
            ''', (user_id,))
            # Insert new OTP
            cursor.execute('''
                INSERT INTO otp_codes (user_id, code, expires_at)
                VALUES (%s, %s, %s)
                RETURNING id
            ''', (user_id, code, expires_at))
            row = cursor.fetchone()
            return row['id'] if row else None

        return self.execute_many(_work)

    def get_otp(self, otp_id: int) -> Optional[Dict[str, Any]]:
        """Get an OTP by ID."""
        return self.query_one('''
            SELECT id, user_id, code, expires_at, attempts, send_count, used_at, created_at
            FROM otp_codes
            WHERE id = %s
        ''', (otp_id,))

    def increment_otp_attempts(self, otp_id: int) -> int:
        """Increment wrong-attempt counter. Returns new attempt count."""
        row = self.query_one('''
            UPDATE otp_codes SET attempts = attempts + 1
            WHERE id = %s
            RETURNING attempts
        ''', (otp_id,))
        return row['attempts'] if row else 0

    def mark_otp_used(self, otp_id: int) -> bool:
        """Mark OTP as used."""
        return self.execute('''
            UPDATE otp_codes SET used_at = CURRENT_TIMESTAMP
            WHERE id = %s AND used_at IS NULL
        ''', (otp_id,)) > 0

    def update_otp_for_resend(self, otp_id: int, new_code: str, new_expires_at: datetime) -> bool:
        """Update OTP code and expiry for a resend, increment send_count, reset attempts."""
        return self.execute('''
            UPDATE otp_codes
            SET code = %s, expires_at = %s, attempts = 0, send_count = send_count + 1, used_at = NULL
            WHERE id = %s AND used_at IS NULL
        ''', (new_code, new_expires_at, otp_id)) > 0
```

- [ ] **Step 4: Commit**

```bash
git add jarvis/core/auth/repositories/user_repository.py tests/test_otp.py
git commit -m "feat(auth): add OTP repository methods and initial test scaffolding"
```

---

### Task 3: Auth Service — OTP Generation, Verification, and Trusted Device

**Files:**
- Modify: `jarvis/core/auth/services/auth_service.py` (add methods to `AuthService` class)

- [ ] **Step 1: Add imports to auth_service.py**

At the top of `jarvis/core/auth/services/auth_service.py`, add these imports alongside existing ones:

```python
import hmac
import hashlib
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
```

- [ ] **Step 2: Add OTP helper methods to AuthService class**

Add these methods to the `AuthService` class, after the password reset section (after `_send_reset_email`):

```python
    # --- OTP Two-Factor Authentication Methods ---

    OTP_EXPIRY_MINUTES = 5
    OTP_MAX_ATTEMPTS = 5
    OTP_MAX_SENDS = 3
    TRUSTED_DEVICE_MAX_AGE = 30 * 24 * 3600  # 30 days in seconds
    TRUSTED_COOKIE_NAME = 'jarvis_trusted_device'

    def _generate_otp_code(self) -> str:
        """Generate a cryptographically random 6-digit OTP code."""
        return f'{secrets.randbelow(1000000):06d}'

    def _compare_otp(self, submitted: str, stored: str) -> bool:
        """Compare OTP codes using timing-safe comparison."""
        return hmac.compare_digest(submitted, stored)

    def _compute_device_hash(self, user_agent: str, ip_address: str) -> str:
        """Compute a device fingerprint hash from User-Agent and IP /24 prefix."""
        # Use first 3 octets of IP so minor IP changes within same network are OK
        ip_parts = ip_address.split('.')
        ip_prefix = '.'.join(ip_parts[:3]) if len(ip_parts) == 4 else ip_address
        raw = f'{user_agent}|{ip_prefix}'
        return hashlib.sha256(raw.encode()).hexdigest()

    def generate_and_send_otp(self, user_id: int, user_email: str, user_name: str) -> tuple:
        """Generate OTP, store in DB, send via email.

        Returns:
            (otp_id, success, error_message)
            otp_id: ID of the otp_codes row (or None on DB failure)
            success: True if email was sent
            error_message: Error string if email failed
        """
        code = self._generate_otp_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.OTP_EXPIRY_MINUTES)

        otp_id = self.user_repo.create_otp(user_id, code, expires_at)
        if not otp_id:
            logger.error(f"Failed to create OTP for user {user_id}")
            return None, False, "Failed to generate verification code"

        success, error = self._send_otp_email(user_name, user_email, code)
        return otp_id, success, error

    def resend_otp(self, otp_id: int, user_email: str, user_name: str) -> tuple:
        """Regenerate code for existing OTP row and resend email.

        Returns:
            (success, error_message, blocked)
            blocked: True if max sends reached
        """
        otp = self.user_repo.get_otp(otp_id)
        if not otp or otp['used_at']:
            return False, "Invalid verification session", True

        if otp['send_count'] >= self.OTP_MAX_SENDS:
            return False, "Maximum resend attempts reached. Please log in again.", True

        new_code = self._generate_otp_code()
        new_expires = datetime.now(timezone.utc) + timedelta(minutes=self.OTP_EXPIRY_MINUTES)

        if not self.user_repo.update_otp_for_resend(otp_id, new_code, new_expires):
            return False, "Failed to regenerate code", False

        success, error = self._send_otp_email(user_name, user_email, new_code)
        if not success:
            # Check if this was the last allowed send
            updated_otp = self.user_repo.get_otp(otp_id)
            if updated_otp and updated_otp['send_count'] >= self.OTP_MAX_SENDS:
                return False, "Unable to send verification code. Please try again later.", True
        return success, error, False

    def verify_otp(self, otp_id: int, submitted_code: str) -> tuple:
        """Verify a submitted OTP code.

        Returns:
            (success, error_message)
        """
        otp = self.user_repo.get_otp(otp_id)
        if not otp or otp['used_at']:
            return False, "Invalid verification session. Please log in again."

        now = datetime.now(timezone.utc)
        expires_at = otp['expires_at']
        # Make expires_at timezone-aware if it isn't
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now > expires_at:
            return False, "Code expired. Please request a new one."

        if otp['attempts'] >= self.OTP_MAX_ATTEMPTS:
            return False, "Too many wrong attempts. Please request a new code."

        if not self._compare_otp(submitted_code.strip(), otp['code']):
            self.user_repo.increment_otp_attempts(otp_id)
            remaining = self.OTP_MAX_ATTEMPTS - otp['attempts'] - 1
            if remaining <= 0:
                return False, "Too many wrong attempts. Please request a new code."
            return False, f"Invalid code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."

        self.user_repo.mark_otp_used(otp_id)
        return True, ""

    def create_trusted_device_cookie(self, user_id: int, user_agent: str, ip_address: str, secret_key: str) -> str:
        """Create a signed trusted device cookie value."""
        s = URLSafeTimedSerializer(secret_key)
        device_hash = self._compute_device_hash(user_agent, ip_address)
        return s.dumps({'uid': user_id, 'dh': device_hash})

    def validate_trusted_device_cookie(self, cookie_value: str, user_id: int, user_agent: str, ip_address: str, secret_key: str) -> bool:
        """Validate a trusted device cookie."""
        if not cookie_value:
            return False
        s = URLSafeTimedSerializer(secret_key)
        try:
            data = s.loads(cookie_value, max_age=self.TRUSTED_DEVICE_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False

        if data.get('uid') != user_id:
            return False

        expected_hash = self._compute_device_hash(user_agent, ip_address)
        return hmac.compare_digest(data.get('dh', ''), expected_hash)

    def _send_otp_email(self, name: str, email: str, code: str) -> tuple:
        """Send OTP verification email. Returns (success, error_message)."""
        from core.services.notification_service import send_email, is_smtp_configured

        if not is_smtp_configured():
            logger.warning("SMTP not configured - cannot send OTP email")
            return False, "Email service not configured"

        subject = "J.A.R.V.I.S. — Your login verification code"

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #333; font-size: 24px; margin: 0;">J.A.R.V.I.S.</h1>
                <p style="color: #666; margin: 5px 0 0;">Login Verification</p>
            </div>
            <div style="background: #f8f9fa; border-radius: 8px; padding: 24px; margin-bottom: 20px;">
                <p style="margin: 0 0 15px; color: #333;">Hi {name},</p>
                <p style="margin: 0 0 20px; color: #333;">Your verification code is:</p>
                <div style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #333; background: #fff; padding: 20px; text-align: center; border-radius: 8px; border: 2px solid #e9ecef; margin: 0 0 20px;">
                    {code}
                </div>
                <p style="margin: 0 0 10px; color: #666; font-size: 14px;">This code expires in <strong>5 minutes</strong>.</p>
                <p style="margin: 0; color: #666; font-size: 14px;">If you did not attempt to log in, please ignore this email and consider changing your password.</p>
            </div>
            <div style="text-align: center; color: #999; font-size: 12px;">
                <p style="margin: 0;">This is an automated message from J.A.R.V.I.S.</p>
            </div>
        </div>
        """

        text_body = f"""J.A.R.V.I.S. — Login Verification

Hi {name},

Your verification code is: {code}

This code expires in 5 minutes.

If you did not attempt to log in, please ignore this email and consider changing your password.
"""

        success, error = send_email(email, subject, html_body, text_body, skip_global_cc=True)
        if not success:
            logger.error(f"Failed to send OTP email to {email}: {error}")
        else:
            logger.info(f"OTP email sent to {email}")
        return success, error
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis
python -m pytest tests/test_otp.py -v
```

Expected: All tests in `TestOTPGeneration`, `TestOTPVerification`, and `TestTrustedDeviceHash` PASS.

- [ ] **Step 4: Commit**

```bash
git add jarvis/core/auth/services/auth_service.py
git commit -m "feat(auth): add OTP generation, verification, trusted device, and email sending to AuthService"
```

---

### Task 4: Verify OTP Template

**Files:**
- Create: `jarvis/templates/core/verify_otp.html`

- [ ] **Step 1: Create the verify OTP template**

Create `jarvis/templates/core/verify_otp.html`. This template reuses the exact same CSS variables and styling from `login.html` for visual consistency:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS - Verify Login</title>
    <link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='img/jarvis-icon.svg') }}">
    <style>
        :root {
            --background: oklch(1 0 0);
            --foreground: oklch(0.145 0 0);
            --card: oklch(1 0 0);
            --card-foreground: oklch(0.145 0 0);
            --primary: oklch(0.205 0 0);
            --primary-foreground: oklch(0.985 0 0);
            --muted: oklch(0.97 0 0);
            --muted-foreground: oklch(0.556 0 0);
            --border: oklch(0.922 0 0);
            --input: oklch(0.922 0 0);
            --ring: oklch(0.708 0 0);
            --destructive: oklch(0.577 0.245 27.325);
            --radius: 0.625rem;
        }
        .dark {
            --background: oklch(0.145 0 0);
            --foreground: oklch(0.985 0 0);
            --card: oklch(0.205 0 0);
            --card-foreground: oklch(0.985 0 0);
            --primary: oklch(0.922 0 0);
            --primary-foreground: oklch(0.205 0 0);
            --muted: oklch(0.269 0 0);
            --muted-foreground: oklch(0.708 0 0);
            --border: oklch(1 0 0 / 10%);
            --input: oklch(1 0 0 / 15%);
            --ring: oklch(0.556 0 0);
            --destructive: oklch(0.704 0.191 22.216);
        }

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: var(--background);
            color: var(--foreground);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 1rem;
            -webkit-font-smoothing: antialiased;
        }

        .verify-container { width: 100%; max-width: 400px; }

        .verify-card {
            background: var(--card);
            color: var(--card-foreground);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 2rem;
            box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
        }

        .verify-header { text-align: center; margin-bottom: 1.5rem; }
        .verify-header .logo {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        .verify-header .logo svg { width: 1.25rem; height: 1.25rem; }
        .verify-header p { font-size: 0.875rem; color: var(--muted-foreground); }

        .alert {
            display: flex;
            align-items: flex-start;
            gap: 0.5rem;
            padding: 0.75rem 1rem;
            border-radius: var(--radius);
            font-size: 0.875rem;
            margin-bottom: 1rem;
            border: 1px solid;
        }
        .alert-error {
            background: oklch(0.577 0.245 27.325 / 10%);
            border-color: oklch(0.577 0.245 27.325 / 30%);
            color: var(--destructive);
        }
        .alert-info {
            background: oklch(0.6 0.118 184.704 / 10%);
            border-color: oklch(0.6 0.118 184.704 / 30%);
            color: oklch(0.5 0.1 160);
        }
        .dark .alert-info { color: oklch(0.7 0.15 160); }
        .alert-close {
            margin-left: auto;
            background: none;
            border: none;
            cursor: pointer;
            color: inherit;
            opacity: 0.5;
            font-size: 1.25rem;
            line-height: 1;
            padding: 0;
        }
        .alert-close:hover { opacity: 1; }

        .form-group { margin-bottom: 1rem; }
        .form-label {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            margin-bottom: 0.375rem;
        }

        .otp-input {
            width: 100%;
            height: 3.5rem;
            padding: 0 1rem;
            font-size: 1.5rem;
            font-weight: 600;
            letter-spacing: 0.5rem;
            text-align: center;
            background: transparent;
            color: var(--card-foreground);
            border: 1px solid var(--input);
            border-radius: calc(var(--radius) - 2px);
            outline: none;
            transition: border-color 0.15s, box-shadow 0.15s;
        }
        .otp-input::placeholder { color: var(--muted-foreground); letter-spacing: 0.3rem; font-weight: 400; }
        .otp-input:focus { border-color: var(--ring); box-shadow: 0 0 0 2px var(--ring); }

        .btn-verify {
            width: 100%;
            height: 2.5rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.875rem;
            font-weight: 500;
            background: var(--primary);
            color: var(--primary-foreground);
            border: none;
            border-radius: calc(var(--radius) - 2px);
            cursor: pointer;
            transition: opacity 0.15s;
            margin-top: 0.5rem;
        }
        .btn-verify:hover { opacity: 0.9; }
        .btn-verify:active { opacity: 0.8; }
        .btn-verify:disabled { opacity: 0.5; cursor: not-allowed; }

        .verify-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: 1.25rem;
            font-size: 0.875rem;
        }

        .resend-btn {
            background: none;
            border: none;
            color: var(--muted-foreground);
            cursor: pointer;
            font-size: 0.875rem;
            text-decoration: none;
            padding: 0;
        }
        .resend-btn:hover { color: var(--foreground); text-decoration: underline; }
        .resend-btn:disabled { opacity: 0.5; cursor: not-allowed; text-decoration: none; }

        .back-link {
            font-size: 0.875rem;
            color: var(--muted-foreground);
            text-decoration: none;
        }
        .back-link:hover { color: var(--foreground); text-decoration: underline; }

        .countdown {
            text-align: center;
            font-size: 0.8rem;
            color: var(--muted-foreground);
            margin-top: 0.75rem;
        }

        /* Theme toggle */
        .theme-toggle {
            position: fixed;
            top: 1rem;
            right: 1rem;
            background: var(--muted);
            border: 1px solid var(--border);
            border-radius: calc(var(--radius) - 2px);
            width: 2.25rem;
            height: 2.25rem;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: var(--muted-foreground);
            transition: background 0.15s, color 0.15s;
        }
        .theme-toggle:hover { background: var(--border); color: var(--foreground); }
        .theme-toggle svg { width: 1rem; height: 1rem; }
        .theme-toggle .icon-sun { display: none; }
        .theme-toggle .icon-moon { display: block; }
        .dark .theme-toggle .icon-sun { display: block; }
        .dark .theme-toggle .icon-moon { display: none; }
    </style>
    <script>
        (function() {
            var theme = localStorage.getItem('jarvis-theme');
            if (theme === 'dark' || (!theme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                document.documentElement.classList.add('dark');
            }
        })();
    </script>
</head>
<body>
    <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle theme">
        <svg class="icon-sun" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
        <svg class="icon-moon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
    </button>

    <div class="verify-container">
        <div class="verify-card">
            <div class="verify-header">
                <div class="logo">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    J.A.R.V.I.S.
                </div>
                <p>Enter verification code</p>
            </div>

            {% with messages = get_flashed_messages(with_categories=true) %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}" role="alert">
                        <span>{{ message }}</span>
                        <button class="alert-close" onclick="this.parentElement.remove()">&times;</button>
                    </div>
                {% endfor %}
            {% endwith %}

            <p style="font-size: 0.875rem; color: var(--muted-foreground); margin-bottom: 1.25rem;">
                A 6-digit code has been sent to your email address.
            </p>

            <form method="POST" action="{{ url_for('auth.verify_otp') }}" id="otpForm">
                <div class="form-group">
                    <label class="form-label" for="otp_code">Verification code</label>
                    <input type="text" id="otp_code" name="otp_code" class="otp-input"
                           maxlength="6" pattern="[0-9]{6}" inputmode="numeric" autocomplete="one-time-code"
                           placeholder="000000" autofocus required>
                </div>

                <button type="submit" class="btn-verify" id="verifyBtn">Verify</button>
            </form>

            <div class="countdown" id="countdown"></div>

            <div class="verify-footer">
                <a href="{{ url_for('auth.login') }}" class="back-link">Back to login</a>
                <form method="POST" action="{{ url_for('auth.resend_otp') }}" style="display:inline;">
                    <button type="submit" class="resend-btn" id="resendBtn">Resend code</button>
                </form>
            </div>
        </div>
    </div>

    <script>
        function toggleTheme() {
            var html = document.documentElement;
            var isDark = html.classList.toggle('dark');
            localStorage.setItem('jarvis-theme', isDark ? 'dark' : 'light');
        }

        // Auto-submit when 6 digits entered
        var otpInput = document.getElementById('otp_code');
        otpInput.addEventListener('input', function() {
            this.value = this.value.replace(/[^0-9]/g, '');
            if (this.value.length === 6) {
                document.getElementById('otpForm').submit();
            }
        });

        // Countdown timer (5 minutes from page load)
        var secondsLeft = {{ seconds_remaining | default(300) }};
        var countdownEl = document.getElementById('countdown');
        var verifyBtn = document.getElementById('verifyBtn');

        function updateCountdown() {
            if (secondsLeft <= 0) {
                countdownEl.textContent = 'Code expired. Please resend.';
                verifyBtn.disabled = true;
                return;
            }
            var m = Math.floor(secondsLeft / 60);
            var s = secondsLeft % 60;
            countdownEl.textContent = 'Code expires in ' + m + ':' + (s < 10 ? '0' : '') + s;
            secondsLeft--;
            setTimeout(updateCountdown, 1000);
        }
        updateCountdown();
    </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add jarvis/templates/core/verify_otp.html
git commit -m "feat(auth): add OTP verification page template"
```

---

### Task 5: Login Route — Wire Up OTP Flow

**Files:**
- Modify: `jarvis/core/auth/routes.py` (modify `login()`, add `verify_otp()`, `resend_otp()`, modify `logout()`)

- [ ] **Step 1: Add imports at the top of routes.py**

Add `time` to existing imports and import `make_response` from Flask (if not already imported):

```python
import time
from flask import make_response
```

- [ ] **Step 2: Modify the `login()` route**

Replace the current `login()` function body (lines 62-98 of `routes.py`) with:

```python
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and form handler."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        allowed, retry_after = _auth_limiter.is_allowed(
            f'login:{request.remote_addr}', max_requests=10, window_seconds=300)
        if not allowed:
            flash(f'Too many login attempts. Try again in {retry_after} seconds.', 'error')
            return render_template('core/login.html')

        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('core/login.html')

        user_data = _user_repo.authenticate(email, password)
        if user_data:
            user = User(user_data)
            remember = request.form.get('remember') == 'on'
            next_page = request.args.get('next')
            if next_page and (not next_page.startswith('/') or next_page.startswith('//')):
                next_page = None

            # Check trusted device cookie
            auth_svc = _get_auth_service()
            cookie = request.cookies.get(auth_svc.TRUSTED_COOKIE_NAME)
            if auth_svc.validate_trusted_device_cookie(
                cookie, user.id,
                request.headers.get('User-Agent', ''),
                request.remote_addr,
                current_app.secret_key
            ):
                # Trusted device — skip OTP
                login_user(user, remember=remember)
                _user_repo.update_last_login(user.id)
                _log_event('login', f'User {email} logged in (trusted device)')
                return redirect(next_page or url_for('index'))

            # Not trusted — generate and send OTP
            otp_id, email_sent, error = auth_svc.generate_and_send_otp(
                user.id, user.email, user.name)

            if not otp_id:
                flash('An error occurred. Please try again.', 'error')
                return render_template('core/login.html')

            # Store pending OTP state in session
            session['otp_pending'] = {
                'user_id': user.id,
                'otp_id': otp_id,
                'remember': remember,
                'next_page': next_page,
                'created_at': time.time(),
            }

            if not email_sent:
                flash('Failed to send verification code. You can retry on the next page.', 'error')

            return redirect(url_for('auth.verify_otp'))
        else:
            _log_event('login_failed', f'Failed login attempt for {email}')
            flash('Invalid email or password.', 'error')

    return render_template('core/login.html')
```

- [ ] **Step 3: Add `verify_otp` route**

Add this after the `login()` function:

```python
@auth_bp.route('/login/verify', methods=['GET', 'POST'])
def verify_otp():
    """OTP verification page and handler."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    pending = session.get('otp_pending')
    if not pending:
        flash('Please log in first.', 'error')
        return redirect(url_for('auth.login'))

    # Session timeout (10 minutes)
    if time.time() - pending.get('created_at', 0) > 600:
        session.pop('otp_pending', None)
        flash('Verification session expired. Please log in again.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        submitted_code = request.form.get('otp_code', '').strip()
        if not submitted_code:
            flash('Please enter the verification code.', 'error')
            return _render_verify_page(pending)

        auth_svc = _get_auth_service()
        success, error = auth_svc.verify_otp(pending['otp_id'], submitted_code)

        if success:
            # OTP verified — complete login
            user_data = _user_repo.get_by_id(pending['user_id'])
            if not user_data:
                session.pop('otp_pending', None)
                flash('User not found. Please log in again.', 'error')
                return redirect(url_for('auth.login'))

            user = User(user_data)
            login_user(user, remember=pending.get('remember', False))
            _user_repo.update_last_login(user.id)
            _log_event('login', f'User {user.email} logged in (OTP verified)')

            next_page = pending.get('next_page')
            session.pop('otp_pending', None)

            # Set trusted device cookie
            resp = make_response(redirect(next_page or url_for('index')))
            cookie_value = auth_svc.create_trusted_device_cookie(
                user.id,
                request.headers.get('User-Agent', ''),
                request.remote_addr,
                current_app.secret_key
            )
            resp.set_cookie(
                auth_svc.TRUSTED_COOKIE_NAME,
                cookie_value,
                max_age=auth_svc.TRUSTED_DEVICE_MAX_AGE,
                httponly=True,
                secure=not current_app.debug,
                samesite='Lax',
            )
            return resp
        else:
            flash(error, 'error')

    return _render_verify_page(pending)


def _render_verify_page(pending: dict):
    """Render the OTP verify page with countdown seconds."""
    auth_svc = _get_auth_service()
    otp = _user_repo.get_otp(pending['otp_id'])
    seconds_remaining = 0
    if otp and not otp.get('used_at'):
        from datetime import datetime, timezone
        expires = otp['expires_at']
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        diff = (expires - datetime.now(timezone.utc)).total_seconds()
        seconds_remaining = max(0, int(diff))
    return render_template('core/verify_otp.html', seconds_remaining=seconds_remaining)
```

- [ ] **Step 4: Add `resend_otp` route**

Add this after `verify_otp()`:

```python
@auth_bp.route('/login/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP code."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    pending = session.get('otp_pending')
    if not pending:
        flash('Please log in first.', 'error')
        return redirect(url_for('auth.login'))

    user_data = _user_repo.get_by_id(pending['user_id'])
    if not user_data:
        session.pop('otp_pending', None)
        flash('Session invalid. Please log in again.', 'error')
        return redirect(url_for('auth.login'))

    auth_svc = _get_auth_service()
    success, error, blocked = auth_svc.resend_otp(
        pending['otp_id'], user_data['email'], user_data['name'])

    if blocked:
        session.pop('otp_pending', None)
        flash(error, 'error')
        return redirect(url_for('auth.login'))

    if success:
        flash('New verification code sent to your email.', 'info')
    else:
        flash(error or 'Failed to send code. Please try again.', 'error')

    return redirect(url_for('auth.verify_otp'))
```

- [ ] **Step 5: Modify `logout()` to delete trusted device cookie**

Replace the current `logout()` function with:

```python
@auth_bp.route('/logout')
@login_required
def logout():
    """Logout current user."""
    _log_event('logout', f'User {current_user.email} logged out')
    logout_user()
    flash('You have been logged out.', 'info')
    resp = make_response(redirect(url_for('auth.login')))
    resp.delete_cookie('jarvis_trusted_device')
    return resp
```

- [ ] **Step 6: Add `get_otp` method to UserRepository if not accessible from routes**

The `_render_verify_page` helper calls `_user_repo.get_otp()`. This method was added in Task 2 Step 3 on `UserRepository`, so it's already available via the `_user_repo` instance at the top of `routes.py`.

Verify this import exists at the top of `routes.py`:

```python
from flask import current_app, make_response
```

If `make_response` is not already imported from Flask, add it to the existing import line.

- [ ] **Step 7: Verify the app starts without errors**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis
python -c "from jarvis.core.auth.routes import auth_bp; print('Routes loaded OK')"
```

- [ ] **Step 8: Run all OTP tests**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis
python -m pytest tests/test_otp.py -v
```

Expected: All tests PASS.

- [ ] **Step 9: Commit**

```bash
git add jarvis/core/auth/routes.py
git commit -m "feat(auth): wire OTP flow into login, add verify/resend routes, clear cookie on logout"
```

---

### Task 6: Manual End-to-End Verification

**Files:** None (testing only)

- [ ] **Step 1: Run the migration on local/staging DB**

Connect to the staging database and create the `otp_codes` table:

```sql
CREATE TABLE IF NOT EXISTS otp_codes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code VARCHAR(6) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    send_count INTEGER NOT NULL DEFAULT 1,
    used_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_otp_codes_user_id ON otp_codes(user_id);
```

- [ ] **Step 2: Test happy path**

1. Open JARVIS in an incognito window (no cookies)
2. Enter valid email + password → should redirect to `/login/verify`
3. Check email for 6-digit code
4. Enter code → should log in and redirect to dashboard
5. Log out → log in again → should skip OTP (trusted device cookie set)

- [ ] **Step 3: Test error paths**

1. Enter wrong OTP 5 times → should see "Too many wrong attempts"
2. Wait 5 minutes → should see "Code expired"
3. Click "Resend code" 3 times → should see "Maximum resend attempts" and redirect to login
4. Navigate directly to `/login/verify` without password step → should redirect to `/login`

- [ ] **Step 4: Test trusted device expiry**

1. Log in successfully (cookie set)
2. Delete the `jarvis_trusted_device` cookie from browser
3. Log in again → should require OTP

- [ ] **Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix(auth): address issues found during OTP manual testing"
```

---

## Dependency Graph

```
Task 1 (DB migration)
    └── Task 2 (OTP repository methods)
            └── Task 3 (Auth service methods)
                    ├── Task 4 (Template) — independent of Task 3
                    └── Task 5 (Routes — wires everything together)
                            └── Task 6 (Manual E2E testing)
```

Tasks 3 and 4 can be done in parallel. All others are sequential.
