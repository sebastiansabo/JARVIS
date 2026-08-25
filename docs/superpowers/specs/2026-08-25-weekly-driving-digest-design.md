# Weekly Driving Digest — Design Spec

**Date:** 2026-08-25
**Branch:** `feature/foi-parcurs-driving-digest` (off `dev`)
**Status:** design approved (product decisions confirmed); pending spec review → implementation plan

## Overview

A scheduled, AI-narrated **weekly digest of driving activity** (Foi de Parcurs). Every Monday
08:00 (Europe/Bucharest) it emails, for the **previous Mon–Sun**:

- **One report per Company-Brand** → that company's managers.
- **One cumulative group report** → the Board.

It reuses the Phase-1 Rapoarte aggregates (no new SQL) and the existing `ai_agent` LLM to
generate a Romanian narrative, delivered as an HTML email plus a short in-app notification.

## Goals / non-goals

**Goals**
- Zero new report SQL — call `FoiParcursRepository.report_bundle` + `FPVehicleRepository.report_fleet`.
- AI narrative via the DB-configured model (`ai_agent`), with a deterministic templated fallback.
- Per-Company-Brand distribution + a Board cumulative.
- Safe on staging (must not double-send real emails).

**Non-goals (v1)**
- No new UI/tab (this is a backend scheduled job). A manual "send now" admin trigger is optional.
- No PDF attachment (HTML body only) — can add later.
- No per-user digest preferences beyond the enable flag + recipient resolution below.

## Architecture / components

1. **`jarvis/foi_parcurs/services/driving_digest_service.py`** (new) — orchestrator:
   - `_week_range()` → previous Mon 00:00 .. Sun 23:59 (Europe/Bucharest), returned as `date_from`/`date_to` strings matching the reports' `COALESCE(departure,created)` filter.
   - `_enumerate_company_brands()` → `CompanyRepository.get_all_with_vat_and_brands()`, filtered to FOI brands (mirror `foi_parcurs/routes/vehicles.py` `show_in_foi_parcurs`), yielding `(company_id, company_name, brand)`.
   - `_collect(company_id, brand)` → dict from `report_bundle(company_id, from, to, 'sales', brand=brand)` + `report_fleet(company_id, 'sales', brand=brand)` (kpis, top_advisors, utilization, by_status, client_vs_internal, by_brand, fuel, top_odometer, distance).
   - `_collect_board()` → same with `company_id=None`, `brand=None` (group-wide).
   - `_narrative(metrics, scope_label)` → AI text (see §AI).
   - `_render_company_html(...)` / `_render_board_html(...)` → HTML sections.
   - `generate_and_send()` → gate → build → resolve recipients → send email + in-app note.

2. **`jarvis/tasks/driving_digest.py`** (new) — thin `run_weekly_driving_digest()` wrapper (try/except, logs), mirroring `tasks/ai_tasks.py:run_daily_digest`.

3. **`jarvis/tasks/cleanup.py`** (edit) — import + one `scheduler.add_job(run_weekly_driving_digest, 'cron', day_of_week='mon', hour=5, minute=0, id='weekly_driving_digest', replace_existing=True, misfire_grace_time=3600, coalesce=True)` (05:00 UTC = 08:00 RO summer; mirror the HR weekly digest block).

## AI narrative

- Helper: `from ai_agent.services.llm_client import ask`; model from `ModelConfigRepository().get_default().model_name` (falls back to `claude-sonnet-4-6`). Keep this model — the provider always sends `temperature`, and a sonnet-5-class model would 400 on it.
- **System prompt** (RO): "Ești JARVIS, asistentul intern AUTOWORLD. Scrie un rezumat săptămânal concis despre activitatea de driving pentru {scope}. Acoperă: performanță & clasament (consilieri/mașini), alerte & anomalii (retururi ratate, mașini nefolosite), mix client vs. intern & firmă vs. persoană, ocupare & distanțe. Ton profesional, la obiect, în română. Format text simplu."
- **User content:** `json.dumps(metrics, default=str)`.
- **Fallback:** `_narrative_plain(metrics)` — deterministic RO summary of the top figures, used when no model/API key.

## Delivery

- **Email:** `core.services.notification_service.send_email(to_email, subject, html_body, skip_global_cc=True)` looped per recipient (per HR weekly digest). Subject e.g. `Digest Driving — {company} {brand} — săptămâna {dd.mm}–{dd.mm}`. Board subject: `Digest Driving — Grup AUTOWORLD — ...`.
- **In-app note:** `core.notifications.notify.notify_users(user_ids, title, message, link='/app/foi-parcurs', type='info')` — short "Digestul săptămânal de driving este disponibil".
- Guard with `is_smtp_configured()`.

## Recipients

- **Per Company-Brand:** the company's managers via `CompanyRepository.get_responsables(company_id)` (→ user ids/emails); fallback `companies.alert_email`. In-app note to those user ids.
- **Board cumulative:** users with `role_name == 'board'` (via `UserRepository().get_all()` filtered), matching `foi_parcurs/routes/reports.py` `_GROUP_ROLES`. Optionally an override list from notification settings.

## Staging safety (gate)

`generate_and_send()` returns early unless **both**:
1. notification setting `weekly_driving_digest_enabled == 'true'`, AND
2. running on prod — `os.environ.get('FLASK_ENV') == 'production'` (or the app's existing `is_production`).

Staging may build/log the digest but must not email. (There is no scheduler-level env gate — confirmed.)

## Testing

- `_week_range()` returns correct previous Mon–Sun boundaries (tz-aware).
- `generate_and_send()` no-ops when disabled / non-prod (asserts no email sent).
- Recipient resolution: company managers per section; Board = role 'board'.
- HTML render + narrative with a **mocked** LLM (fake `ask`) — assert sections present, fallback path when LLM raises.
- Company-Brand enumeration filters to FOI brands.
- LLM + email + DB are mocked (unit tests); metrics assembly validated against the local dev DB manually.

## Out of scope / follow-ups
- PDF attachment; admin "send now" trigger; per-user opt-in; localization beyond RO.
