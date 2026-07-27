# Bilet de Invoire — Approval workflow (2nd approver, email + push, open-in-app)

**Date:** 2026-07-27
**Status:** Design — approved, pending spec review
**Area:** JARVIS web (`jarvis/`), jarvis-mobile-2

## Summary

Extend the existing leave-permission ("Bilet de Invoire") flow so a request can
route to an **optional second approver** (either may approve), so the approver is
notified by **email + push** (already wired), and so the notification link can
**open the mobile app** when installed. This is reuse-heavy: the approval engine,
notifications, and status lifecycle already exist. The only substantive new build
is the "open in app" link.

## Current state (reuse map — do NOT rebuild)

- **Approval engine** (`core/approvals/`): flow **#7 "Form Submission Approval"**
  (`entity_type = form_submission`) with a single `context_approver` step.
  `engine.py` completes a step when `counts['approved'] >= min_approvals`, and
  `min_approvals` defaults to **1** (with a `min_approvals_override` context hook).
- **Leave form is already wired**: `forms/services/form_service.py::_trigger_approval`
  builds a context and calls `ApprovalEngine.submit(entity_type='form_submission', …)`.
  The primary approver comes from `_resolve_form_approver(requested_by, company_id,
  explicit_approver_id)` (org hierarchy, with an explicit override already supported).
- **Approver notification on submit** already fires: `handlers/event_handlers.py::
  handle_request_created` resolves current-step approvers via `_get_current_step_approvers`
  and calls `notify_users(approver_ids, …)` **and** `_send_approval_email(…)`.
  `_get_current_step_approvers` returns `context.stakeholder_approver_ids` (a **list**)
  when present, else `[context.approver_user_id]`.
- **Notifications** (`core/notifications/notify.py`): `notify_user`/`notify_users`
  create an in-app notification **and** send FCM push via `push_service.send_push_to_users`.
  So push (ask #6) is automatic for any approver notification.
- **Status lifecycle**: `handlers/entity_form.py` sets `form_submissions.status`
  to `pending_approval` / `approved` / `rejected`; `handle_approved` also debits the
  Time Bank for `bilet-de-invoire`. The Hub Învoiri list reflects this status.
- **Mobile (jarvis-mobile-2)**: has push handling (`services/pushNotifications.ts`,
  foreground `pushNotificationReceived`) and in-app deep-links (Digest `?channel=`).
  `appId = com.jarvis.mobile2`, custom URL scheme present. **No external
  universal-link / `appUrlOpen` handler yet**, and no push-tap navigation.

## Decisions

1. **Second approver = either-approves (backup).** Two approvers on the one step;
   `min_approvals = 1` (engine default) means the first decision wins. No engine change.
2. **Approver selection = auto manager + optional second.** Primary auto-resolves
   from the org hierarchy (unchanged). Requester optionally adds a second via a picker.
3. **Open-in-app = web landing page + custom scheme**, not native Universal/App Links.
   Avoids iOS AASA / Android assetlinks setup; gives the "ask to open in app" UX.

## Slice 0 — display polish (DONE this session, ships independently)

- +Învoire moved inline into the Hub breadcrumb (opens via a `?newinvoire=1` URL flag).
- Approval **status badge** per row (`Aprobat` / `Respins` / `În așteptare`).
- Approver row in the expanded detail.
- **`leave_hours` fix**: an earlier change made the duration field store a string
  (`"1 h"`), which broke `_safe_float`. `connecteam_service._leave_hours` now computes
  hours from the start/end times (falling back to legacy numeric), fixing the `—`.

## Slice A — optional second approver (small; no engine change)

**Form**: add an optional `f_bi_second_approver` field (`user_select`, managers only)
to the Bilet form (seed + idempotent DB patch, same pattern as the duration field).

**Backend** (`form_service._trigger_approval`): build
`stakeholder_approver_ids = dedupe([primary] + ([second] if second_chosen])` and put
it in `context`. Primary still from `_resolve_form_approver`. Second read from
`answers.f_bi_second_approver`. When no second is chosen, behaviour is identical to today.

**Result**: both approvers receive in-app + push + email (existing
`handle_request_created`); either can approve (`min_approvals = 1`).

**Tests**: unit — context builder produces the right deduped `stakeholder_approver_ids`
for {no second, distinct second, second == primary}.

## Slice B — "open in app" link (the real build; 3 layers)

**Web landing** — `GET /go/approval/<request_id>`:
- Desktop / no-app path: `302` to `/app/approvals?request=<id>`.
- Mobile: minimal interstitial — *"Deschide în aplicația JARVIS?"* with
  **[Deschide app]** (navigates to `com.jarvis.mobile2://approvals?request=<id>`) and
  **[Continuă în browser]** (→ `/app/approvals?request=<id>`).
- **Auth model: public, redirect-only.** The landing route exposes no data and
  performs no action — it only chooses app-vs-web and redirects. The `/app/approvals`
  screen it lands on stays auth-gated, so an unauthenticated tap ends at the login
  screen, then the approvals list. This keeps the emailed/pushed link openable
  without a session round-trip.

**Backend**: change the `form_submission` approval email CTA and the push
`data.link` to point at `…/go/approval/<request_id>` instead of `/app/approvals`.
Scope the CTA change to the leave/form flow (leave other entity types unchanged).

**Mobile (jarvis-mobile-2)**:
- Add `@capacitor/app` `appUrlOpen` listener → parse `approvals?request=<id>` →
  navigate to the approvals screen.
- Add `pushNotificationActionPerformed` (tap) handler → same navigation using the
  push `data.link` / `request` id.
- iOS custom scheme via `Info.plist` `CFBundleURLSchemes`; Android intent-filter for
  the custom scheme (custom scheme already registered — verify).
- Per repo rule: after changes run `npm run build && npx cap sync android`.

**Tests**: unit — landing redirect/branch logic; mobile — manual/e2e appUrlOpen routing.

## Slice C — real approver name (small refinement)

`connecteam_service.get_user_submissions`: when a submission has an
`approval_request_id`, source the deciding approver (and both notified approver ids)
from the approvals decision record instead of `answers.f_bi_approved_by`. Show both
approvers + who decided in the expanded row.

## Data flow

```
Requester submits Bilet (optional 2nd approver)
  → form_service._trigger_approval
      context.approver_user_id = manager (org hierarchy)
      context.stakeholder_approver_ids = [manager, second?]   (deduped)
  → ApprovalEngine.submit(form_submission, …)  [flow #7, 1 step, min_approvals=1]
      → handle_request_created
          → notify_users([manager, second])   → in-app + FCM push
          → _send_approval_email(...)          → CTA = /go/approval/<request_id>
  → approver taps push / email link
      → /go/approval/<id>  →  app (if installed) or web  →  approvals screen
  → first approver decides  →  engine completes step (min_approvals=1)
      → entity_form.handle_approved/rejected → form_submissions.status
      → Hub Învoiri badge updates; Time Bank debited on approve
```

## Out of scope (YAGNI)

- "Both must approve" (sequential/quorum) — reachable via `min_approvals_override`,
  not built now.
- Native iOS Universal Links / Android App Links (association files) — custom scheme
  + landing page instead.
- Changes to reminder/escalation (engine already handles these).

## To verify during implementation

- Push payload shape the mobile app consumes (`data.link` vs `data.request`).
- `_resolve_form_approver` reliably returns a manager for leave requesters.
- `user_select` field renders a manager-scoped picker in the Bilet modal (confirm
  the field type supports scoping to managers, or add it).
