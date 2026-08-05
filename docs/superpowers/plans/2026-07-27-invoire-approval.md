# Bilet de Invoire Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route a leave request to an optional second approver (either may approve), and make the approver's email + push notification open the JARVIS mobile app when installed.

**Architecture:** Reuse the existing approval engine (flow #7, `context_approver` step, `min_approvals=1`), FCM push (`notify_with_push`), and status lifecycle. New code: a second-approver form field wired into `stakeholder_approver_ids`; a public `/go/approval/<id>` landing route that chooses app-vs-web; and a mobile `appUrlOpen` + push-tap handler that routes to the existing `/approvals` screen.

**Tech Stack:** Python/Flask (JARVIS backend), React/TS + Vitest (JARVIS frontend), React/TS + Capacitor (jarvis-mobile-2), PostgreSQL.

## Global Constraints

- Never touch production DB. Localhost (`postgresql://localhost/defaultdb`) only during dev; staging/prod DB changes are explicit, user-gated deploy steps.
- Do NOT commit `jarvis/app.py` (local `DEV_INSECURE_COOKIES`) or build artifacts (`tsconfig.tsbuildinfo`, `static/react/**`).
- The Bilet form is DB data: the seed skips existing forms, so each env needs an idempotent patch script (run once per env DB).
- Engine semantics: a `context_approver` step completes when `approved_count >= min_approvals`; `min_approvals` defaults to 1 (either-approves). No engine changes.
- Backend python interpreter for scripts: `/Users/sebastiansabo/Documents/Git/Jarvis-3.0/.venv-phase1/bin/python3`.
- Mobile: after any change run `npm run build && npx cap sync android`. Device push additionally requires `VITE_PUSH_ENABLED=true` + FCM `google-services.json` (deploy prerequisite, outside this plan).
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

- `jarvis/forms/services/form_service.py` — build `stakeholder_approver_ids` from primary + optional second (Task 2).
- `jarvis/scripts/seed_leave_permission_form.py` + `jarvis/scripts/patch_leave_permission_second_approver.py` — add the `f_bi_second_approver` field (Task 1).
- `jarvis/core/connectors/connecteam/services/connecteam_service.py` — real approver name from decisions (Task 3).
- `jarvis/core/deeplink/routes.py` (new blueprint) + registration in `jarvis/app.py` — `/go/approval/<id>` landing (Task 4).
- `jarvis/core/approvals/handlers/_shared.py` + `event_handlers.py` — app-aware link + push data payload (Task 5).
- `jarvis-mobile-2/src/services/pushNotifications.ts`, `src/services/deepLinks.ts` (new), `src/App.tsx`, iOS `Info.plist` — appUrlOpen + push-tap routing (Task 6).

---

## Task 1: Second-approver form field

**Files:**
- Modify: `jarvis/scripts/seed_leave_permission_form.py`
- Create: `jarvis/scripts/patch_leave_permission_second_approver.py`

**Interfaces:**
- Produces: a Bilet form field `{id: 'f_bi_second_approver', type: 'user_select'}` whose submitted value is a user-id string (empty when unset). Consumed by Task 2 via `answers['f_bi_second_approver']`.

- [ ] **Step 1: Add the field to the seed schema.** In `FORM_SCHEMA`, after the `f_bi_reason` dropdown, insert:

```python
    {
        'id': 'f_bi_second_approver',
        'type': 'user_select',
        'label': 'Al doilea aprobator (opțional)',
        'required': False,
        'order': 8,
        'config': {'hint': 'Oricare dintre aprobatori poate aproba. Lasă gol pentru aprobare doar de managerul direct.'},
    },
```

Then bump the existing `f_bi_notes` field `'order'` from 8 to 9.

- [ ] **Step 2: Write the idempotent patch** `jarvis/scripts/patch_leave_permission_second_approver.py`:

```python
"""Patch — add the optional second-approver field to the Bilet de Invoire form.

The form already exists in every environment (seed skips it), so add the field
in place, in both `schema` and `published_schema`. Idempotent.

Usage: cd jarvis && python scripts/patch_leave_permission_second_approver.py
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db, get_cursor, release_db

FORM_SLUG = 'bilet-de-invoire'
FIELD_ID = 'f_bi_second_approver'
NEW_FIELD = {
    'id': FIELD_ID,
    'type': 'user_select',
    'label': 'Al doilea aprobator (opțional)',
    'required': False,
    'order': 8,
    'config': {'hint': 'Oricare dintre aprobatori poate aproba. Lasă gol pentru aprobare doar de managerul direct.'},
}


def _as_list(raw):
    return None if raw is None else (json.loads(raw) if isinstance(raw, str) else raw)


def _patch(schema):
    if any(f.get('id') == FIELD_ID for f in schema):
        return schema, False
    # Insert before the notes field if present, else append.
    idx = next((i for i, f in enumerate(schema) if f.get('id') == 'f_bi_notes'), len(schema))
    schema.insert(idx, dict(NEW_FIELD))
    return schema, True


def patch():
    conn = get_db(); cursor = get_cursor(conn)
    try:
        cursor.execute("SELECT id, schema, published_schema FROM forms WHERE slug=%s AND deleted_at IS NULL", (FORM_SLUG,))
        row = cursor.fetchone()
        if not row:
            print(f'Form "{FORM_SLUG}" not found — nothing to patch.'); return
        def col(r, i, n): return r[i] if isinstance(r, (list, tuple)) else r[n]
        form_id = col(row, 0, 'id')
        schema, ca = _patch(_as_list(col(row, 1, 'schema')) or [])
        published, cb = _patch(_as_list(col(row, 2, 'published_schema')) or [])
        if not (ca or cb):
            print(f'Form id={form_id} already has {FIELD_ID}. Nothing to do.'); return
        cursor.execute("UPDATE forms SET schema=%s, published_schema=%s WHERE id=%s",
                       (json.dumps(schema), json.dumps(published), form_id))
        conn.commit()
        print(f'Added {FIELD_ID} to form id={form_id} (schema={ca}, published_schema={cb}).')
    except Exception as e:
        conn.rollback(); print(f'Error: {e}'); raise
    finally:
        release_db(conn)


if __name__ == '__main__':
    patch()
```

- [ ] **Step 3: Run the patch against localhost.**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb /Users/sebastiansabo/Documents/Git/Jarvis-3.0/.venv-phase1/bin/python3 scripts/patch_leave_permission_second_approver.py`
Expected: `Added f_bi_second_approver to form id=2 (schema=True, published_schema=True).`

- [ ] **Step 4: Verify idempotency (run again).**

Run: same command.
Expected: `Form id=2 already has f_bi_second_approver. Nothing to do.`

- [ ] **Step 5: Verify the field is stored.**

Run: `psql postgresql://localhost/defaultdb -At -c "SELECT elem->>'type' FROM forms f, jsonb_array_elements(f.published_schema::jsonb) elem WHERE f.slug='bilet-de-invoire' AND elem->>'id'='f_bi_second_approver';"`
Expected: `user_select`

- [ ] **Step 6: Commit.**

```bash
git add jarvis/scripts/seed_leave_permission_form.py jarvis/scripts/patch_leave_permission_second_approver.py
git commit -m "forms: add optional second-approver field to Bilet de Invoire"
```

---

## Task 2: Route to primary + optional second approver

**Files:**
- Modify: `jarvis/forms/services/form_service.py` (add `_build_stakeholder_ids`; call it in `_trigger_approval`)
- Test: `jarvis/tests/test_form_approval_stakeholders.py`

**Interfaces:**
- Consumes: `answers['f_bi_second_approver']` (user-id string) from Task 1.
- Produces: `context['stakeholder_approver_ids']` (deduped `list[int]`) consumed by the engine's `_get_current_step_approvers`.

- [ ] **Step 1: Write the failing test** `jarvis/tests/test_form_approval_stakeholders.py`:

```python
from forms.services.form_service import FormService

def test_no_second_approver_returns_primary_only():
    assert FormService._build_stakeholder_ids(10, {}) == [10]

def test_distinct_second_appended():
    assert FormService._build_stakeholder_ids(10, {'f_bi_second_approver': '22'}) == [10, 22]

def test_second_equal_primary_deduped():
    assert FormService._build_stakeholder_ids(10, {'f_bi_second_approver': '10'}) == [10]

def test_non_numeric_second_ignored():
    assert FormService._build_stakeholder_ids(10, {'f_bi_second_approver': 'abc'}) == [10]

def test_no_primary_still_returns_second():
    assert FormService._build_stakeholder_ids(None, {'f_bi_second_approver': '22'}) == [22]
```

- [ ] **Step 2: Run test to verify it fails.**

Run: `cd jarvis && python -m pytest tests/test_form_approval_stakeholders.py -v`
Expected: FAIL (`_build_stakeholder_ids` not defined).

- [ ] **Step 3: Add the static helper** to `FormService`:

```python
    @staticmethod
    def _build_stakeholder_ids(primary_id, answers):
        """Deduped [primary, second?] approver ids for either-approves routing."""
        def _as_int(v):
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
        candidates = [primary_id, _as_int((answers or {}).get('f_bi_second_approver'))]
        out, seen = [], set()
        for a in candidates:
            if a and a not in seen:
                seen.add(a); out.append(a)
        return out
```

- [ ] **Step 4: Wire it into `_trigger_approval`.** After `answers = (sub.get('answers') or {}) if sub else {}` and before building `context`, add:

```python
            stakeholder_ids = self._build_stakeholder_ids(approver_user_id, answers)
```

Then in the `context` dict, add the key:

```python
                'stakeholder_approver_ids': stakeholder_ids,
```

- [ ] **Step 5: Run test to verify it passes.**

Run: `cd jarvis && python -m pytest tests/test_form_approval_stakeholders.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit.**

```bash
git add jarvis/forms/services/form_service.py jarvis/tests/test_form_approval_stakeholders.py
git commit -m "forms: route leave approval to primary + optional second approver (either approves)"
```

---

## Task 3: Show the real approver from the decision record

**Files:**
- Modify: `jarvis/core/connectors/connecteam/services/connecteam_service.py` (add `_decider_name`; use it + select `approval_request_id`)
- Test: `jarvis/tests/test_connecteam_decider.py`

**Interfaces:**
- Consumes: `DecisionRepository().get_decisions_for_request(request_id)` → list of dicts with `decision`, `decided_by` (user id), and a joinable decider name.
- Produces: `submission['approved_by']` = deciding approver's name (or None).

- [ ] **Step 1: Confirm the decision row shape.**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS && grep -n "SELECT\|decided_by\|JOIN users\|name" jarvis/core/approvals/repositories/decision_repo.py | head`
Expected: `get_decisions_for_request` returns rows including `decided_by` and (verify) a user name column. If it does NOT join the user name, add `u.name AS decided_by_name` to that query's SELECT (LEFT JOIN users u ON u.id = d.decided_by) as part of this task.

- [ ] **Step 2: Write the failing test** `jarvis/tests/test_connecteam_decider.py`:

```python
from core.connectors.connecteam.services.connecteam_service import _decider_name

def test_none_when_no_decisions():
    assert _decider_name([]) is None

def test_picks_approved_decider():
    rows = [{'decision': 'approved', 'decided_by_name': 'Ion Popescu'}]
    assert _decider_name(rows) == 'Ion Popescu'

def test_picks_rejected_decider():
    rows = [{'decision': 'rejected', 'decided_by_name': 'Ana Ionescu'}]
    assert _decider_name(rows) == 'Ana Ionescu'

def test_ignores_non_terminal_decisions():
    rows = [{'decision': 'returned', 'decided_by_name': 'X'}]
    assert _decider_name(rows) is None
```

- [ ] **Step 3: Run test to verify it fails.**

Run: `cd jarvis && python -m pytest tests/test_connecteam_decider.py -v`
Expected: FAIL (`_decider_name` not defined).

- [ ] **Step 4: Add the module-level helper** to `connecteam_service.py` (near `_leave_hours`):

```python
def _decider_name(decisions):
    """Name of the approver whose decision closed the request (approved/rejected)."""
    for d in decisions or []:
        if d.get('decision') in ('approved', 'rejected'):
            return d.get('decided_by_name') or None
    return None
```

- [ ] **Step 5: Wire it into `get_user_submissions`.** In the JARVIS-submission SELECT, add `fs.approval_request_id` to the selected columns. Then in the result mapping replace `'approved_by': answers.get('f_bi_approved_by')` with:

```python
                    'approved_by': _decider_name(
                        DecisionRepository().get_decisions_for_request(r['approval_request_id'])
                    ) if r.get('approval_request_id') else answers.get('f_bi_approved_by'),
```

Add the import at the top of the file: `from core.approvals.repositories import DecisionRepository`.

- [ ] **Step 6: Run test to verify it passes.**

Run: `cd jarvis && python -m pytest tests/test_connecteam_decider.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit.**

```bash
git add jarvis/core/connectors/connecteam/services/connecteam_service.py jarvis/tests/test_connecteam_decider.py
git commit -m "hub: show the real leave approver from the approval decision record"
```

---

## Task 4: `/go/approval/<id>` app-or-web landing

**Files:**
- Create: `jarvis/core/deeplink/__init__.py`, `jarvis/core/deeplink/routes.py`
- Modify: `jarvis/app.py` (register blueprint)
- Test: `jarvis/tests/test_deeplink_resolve.py`

**Interfaces:**
- Produces: `resolve_deeplink(user_agent: str, request_id: int) -> tuple[str, str]` returning `('redirect', web_url)` for desktop or `('interstitial', app_url)` for mobile, where `app_url = f'com.jarvis.mobile2://approvals?request={request_id}'` and `web_url = f'/app/approvals?request={request_id}'`. Consumed by the Flask route and by Task 5's link builder (`/go/approval/<id>`).

- [ ] **Step 1: Write the failing test** `jarvis/tests/test_deeplink_resolve.py`:

```python
from core.deeplink.routes import resolve_deeplink

IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit'
DESKTOP = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit'

def test_desktop_redirects_to_web():
    assert resolve_deeplink(DESKTOP, 5) == ('redirect', '/app/approvals?request=5')

def test_mobile_gets_interstitial_app_url():
    kind, url = resolve_deeplink(IPHONE, 5)
    assert kind == 'interstitial'
    assert url == 'com.jarvis.mobile2://approvals?request=5'

def test_missing_user_agent_defaults_to_web():
    assert resolve_deeplink('', 9) == ('redirect', '/app/approvals?request=9')
```

- [ ] **Step 2: Run test to verify it fails.**

Run: `cd jarvis && python -m pytest tests/test_deeplink_resolve.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Create the blueprint** `jarvis/core/deeplink/routes.py`:

```python
"""Deep-link landing: send approval notification links to the app or the web."""
from flask import Blueprint, request, redirect, render_template_string

deeplink_bp = Blueprint('deeplink', __name__)

_MOBILE_UA = ('iphone', 'ipad', 'ipod', 'android')


def resolve_deeplink(user_agent, request_id):
    """('redirect', web_url) on desktop, ('interstitial', app_url) on mobile."""
    web_url = f'/app/approvals?request={request_id}'
    ua = (user_agent or '').lower()
    if any(tok in ua for tok in _MOBILE_UA):
        return 'interstitial', f'com.jarvis.mobile2://approvals?request={request_id}'
    return 'redirect', web_url


_INTERSTITIAL = """<!doctype html><html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JARVIS — Aprobare</title>
<style>body{font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#f5f5f5;margin:0;
display:flex;min-height:100vh;align-items:center;justify-content:center}
.card{background:#fff;border-radius:12px;padding:28px;max-width:340px;width:88%;text-align:center;
box-shadow:0 6px 24px rgba(0,0,0,.08)}h1{font-size:18px;margin:0 0 8px}p{color:#666;font-size:14px;margin:0 0 20px}
a{display:block;padding:12px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;margin-top:10px}
.app{background:#4f46e5;color:#fff}.web{background:#eee;color:#333}</style></head>
<body><div class="card"><h1>Cerere de aprobare</h1>
<p>Deschide în aplicația JARVIS?</p>
<a class="app" href="{{ app_url }}">Deschide în aplicație</a>
<a class="web" href="{{ web_url }}">Continuă în browser</a></div></body></html>"""


@deeplink_bp.route('/go/approval/<int:request_id>')
def approval_landing(request_id):
    kind, target = resolve_deeplink(request.headers.get('User-Agent', ''), request_id)
    if kind == 'redirect':
        return redirect(target)
    return render_template_string(_INTERSTITIAL, app_url=target,
                                  web_url=f'/app/approvals?request={request_id}')
```

Add `jarvis/core/deeplink/__init__.py` (empty file).

- [ ] **Step 4: Register the blueprint in `jarvis/app.py`.** Next to the other blueprint registrations add:

```python
    from core.deeplink.routes import deeplink_bp
    flask_app.register_blueprint(deeplink_bp)
```

(Match the exact registration style used by neighbouring blueprints in `app.py` — verify whether they pass a `url_prefix`; `/go/...` must remain at the root, so register with no prefix.)

- [ ] **Step 5: Run test to verify it passes.**

Run: `cd jarvis && python -m pytest tests/test_deeplink_resolve.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Smoke-test the route.**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb /Users/sebastiansabo/Documents/Git/Jarvis-3.0/.venv-phase1/bin/python3 -c "import app as a; c=a.create_app().test_client(); r=c.get('/go/approval/5', headers={'User-Agent':'iPhone'}); print(r.status_code, 'com.jarvis.mobile2' in r.get_data(as_text=True)); r2=c.get('/go/approval/5'); print(r2.status_code, r2.headers.get('Location'))"`
Expected: `200 True` then `302 /app/approvals?request=5` (adjust `create_app` to the actual app factory name in `app.py`).

- [ ] **Step 7: Commit.**

```bash
git add jarvis/core/deeplink/ jarvis/tests/test_deeplink_resolve.py
git commit -m "approvals: /go/approval/<id> app-or-web landing for notification links"
```

(Register-blueprint edit to `app.py` is committed here too — stage `jarvis/app.py` only if the diff is solely the blueprint registration; otherwise stage that hunk explicitly to avoid committing the local cookie change.)

---

## Task 5: Point approver notifications at the landing + carry the deep-link in push

**Files:**
- Modify: `jarvis/core/approvals/handlers/_shared.py` (add `_approval_deeplink`)
- Modify: `jarvis/core/approvals/handlers/event_handlers.py` (`_on_submitted`: use landing link + `notify_with_push`)
- Test: `jarvis/tests/test_approval_deeplink.py`

**Interfaces:**
- Consumes: `_entity_link(entity_type, entity_id)` (existing).
- Produces: `_approval_deeplink(entity_type, entity_id, request_id) -> str` — `/go/approval/<request_id>` for `form_submission`, else the existing `_entity_link(...)`.

- [ ] **Step 1: Write the failing test** `jarvis/tests/test_approval_deeplink.py`:

```python
from core.approvals.handlers._shared import _approval_deeplink

def test_form_submission_uses_landing():
    assert _approval_deeplink('form_submission', 12, 99) == '/go/approval/99'

def test_other_entities_use_entity_link():
    # invoice keeps its existing deep link, not the approval landing
    assert _approval_deeplink('invoice', 7, 99) == '/app/accounting/invoices/7'
```

- [ ] **Step 2: Run test to verify it fails.**

Run: `cd jarvis && python -m pytest tests/test_approval_deeplink.py -v`
Expected: FAIL (`_approval_deeplink` not defined).

- [ ] **Step 3: Add `_approval_deeplink`** to `_shared.py`:

```python
def _approval_deeplink(entity_type, entity_id, request_id):
    """Notification target: form submissions route through the app-or-web landing."""
    if entity_type == 'form_submission' and request_id:
        return f'/go/approval/{request_id}'
    return _entity_link(entity_type, entity_id)
```

- [ ] **Step 4: Use it in `_on_submitted`** (`event_handlers.py`). Add the import: `from ._shared import _approval_deeplink` and `from core.notifications.notify import notify_with_push`. Replace the `link = _entity_link(entity_type, entity_id)` line and the `notify_users(...)` call in the `if approver_ids:` block with:

```python
        link = _approval_deeplink(entity_type, entity_id, request_id)
        notify_with_push(
            approver_ids,
            f'New approval request: {project_title}',
            message='Please review and approve.',
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
            push_data={'type': 'approval', 'request_id': str(request_id), 'link': link},
        )
```

Leave the subsequent email loop, but it already uses `link` for the CTA (`f'{_APP_BASE_URL}{link}'`), so it now points at the landing automatically.

- [ ] **Step 5: Run test to verify it passes.**

Run: `cd jarvis && python -m pytest tests/test_approval_deeplink.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Regression — approvals handler module imports cleanly.**

Run: `cd jarvis && /Users/sebastiansabo/Documents/Git/Jarvis-3.0/.venv-phase1/bin/python3 -c "import core.approvals.handlers.event_handlers as e; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit.**

```bash
git add jarvis/core/approvals/handlers/_shared.py jarvis/core/approvals/handlers/event_handlers.py jarvis/tests/test_approval_deeplink.py
git commit -m "approvals: form-submission notifications open the app-or-web landing; push carries the deep-link"
```

---

## Task 6: Mobile — open the app from the notification link (jarvis-mobile-2)

**Files:**
- Create: `jarvis-mobile-2/src/services/deepLinks.ts`
- Modify: `jarvis-mobile-2/src/App.tsx` (init deep links)
- Modify: `jarvis-mobile-2/src/services/pushNotifications.ts` (approval tap → navigate)
- Modify: `jarvis-mobile-2/ios/App/App/Info.plist` (register custom scheme)

**Interfaces:**
- Consumes: an incoming URL `com.jarvis.mobile2://approvals?request=<id>` (universal deep link) OR a push whose `data` is `{type:'approval', request_id, link}`.
- Produces: a `push-navigate` CustomEvent with detail `/approvals?request=<id>` (the existing App.tsx listener routes it).

- [ ] **Step 1: Create the deep-link handler** `jarvis-mobile-2/src/services/deepLinks.ts`:

```typescript
import { App } from '@capacitor/app';

/** Map an incoming app URL to an in-app route, or null if unrecognised. */
export function routeForUrl(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.hostname === 'approvals' || u.pathname.replace(/\//g, '') === 'approvals') {
      const request = u.searchParams.get('request');
      return request ? `/approvals?request=${request}` : '/approvals';
    }
  } catch { /* ignore malformed urls */ }
  return null;
}

/** Route external links (com.jarvis.mobile2://approvals?request=…) into the app. */
export function initDeepLinks() {
  App.addListener('appUrlOpen', ({ url }) => {
    const route = routeForUrl(url);
    if (route) window.dispatchEvent(new CustomEvent('push-navigate', { detail: route }));
  });
}
```

- [ ] **Step 2: Init deep links in `App.tsx`.** Add `import { initDeepLinks } from '@/services/deepLinks';` and, in the same effect that registers push / on mount, call `initDeepLinks();` once.

- [ ] **Step 3: Handle the approval push tap.** In `pushNotifications.ts`, inside the `pushNotificationActionPerformed` listener, before the `channel_id` branch add:

```typescript
      if (data?.type === 'approval') {
        const link = typeof data.link === 'string' && data.link.startsWith('/approvals')
          ? data.link
          : `/approvals${data.request_id ? `?request=${data.request_id}` : ''}`;
        window.dispatchEvent(new CustomEvent('push-navigate', { detail: link }));
        return;
      }
```

- [ ] **Step 4: Register the iOS custom scheme.** In `ios/App/App/Info.plist`, add (if absent) a `CFBundleURLTypes` entry with `CFBundleURLSchemes` = `com.jarvis.mobile2`. (Android already registers `com.jarvis.mobile2` via `custom_url_scheme` in `strings.xml` + the manifest intent-filter — verify it is `BROWSABLE`/`DEFAULT`.)

- [ ] **Step 5: Typecheck + build + sync.**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npx tsc --noEmit && npm run build && npx cap sync android`
Expected: tsc exit 0; build succeeds; cap sync completes.

- [ ] **Step 6: Manual verification (device/emulator).** With `VITE_PUSH_ENABLED=true` + FCM configured (deploy prerequisite): open `com.jarvis.mobile2://approvals?request=5` (e.g. `adb shell am start -a android.intent.action.VIEW -d "com.jarvis.mobile2://approvals?request=5"`) → app opens on the Approvals screen. Tapping a delivered approval push → same. **If FCM is not yet enabled, verify only the `appUrlOpen` path; note push-tap as unverified pending FCM.**

- [ ] **Step 7: Commit.**

```bash
git add jarvis-mobile-2/src/services/deepLinks.ts jarvis-mobile-2/src/App.tsx jarvis-mobile-2/src/services/pushNotifications.ts jarvis-mobile-2/ios/App/App/Info.plist jarvis-mobile-2/android
git commit -m "mobile: open Approvals from notification deep-link (appUrlOpen + push tap)"
```

---

## Deploy checklist (post-merge, user-gated)

- Run `patch_leave_permission_second_approver.py` against staging, then prod DB (form is DB data).
- Rebuild the JARVIS React bundle if prod serves `static/react`.
- Confirm `APP_BASE_URL` env is set so email/landing links are absolute.
- Mobile device push requires `VITE_PUSH_ENABLED=true` + FCM `google-services.json`; then rebuild APK and cap sync.

## Out of scope (YAGNI)

- "Both must approve" (available via `min_approvals_override`).
- Native iOS Universal Links / Android App Links association files (using custom scheme + landing).
- Manager-only scoping of the second-approver picker (v1 lists all users; scope later).
