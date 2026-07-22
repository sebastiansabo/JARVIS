# Monthly *Foaie de Parcurs* Generator (per car) — Design

**Date:** 2026-07-22
**Module:** `jarvis/foi_parcurs`
**Status:** Approved (brainstorm)

## Goal

From the *Foi de Parcurs* tab, let a user generate a monthly **Foaie de
Parcurs** document for a single car — aggregating all that car's driving
sessions for the selected month into one document. Output in **PDF**
(AI-drafted) and **Excel** (deterministic). Triggered **per row**.

## Legacy engine (context)

`services/pdf_service.py` generates route-sheet PDFs with ReportLab, strictly
**per session** (`generate_legal_pdf(contract)` / `generate_custom_pdf`). No
monthly, per-car aggregation exists. Diacritics are stripped to ASCII because
Helvetica can't render them. `route_service` itinerary generation is a
placeholder. AI is available via `ai_agent.services.llm_client.ask(...)`
(default `claude-sonnet-4-6`). Playwright is a dependency (Chromium present
locally).

## UX

Each car row in `RouteSheetsTable` gets a **dropdown** ("Foaie de parcurs ▾"):

- **Generează PDF (previzualizare)** → opens a modal, calls the PDF endpoint,
  shows the returned PDF inline (`<iframe>` of a blob URL). Buttons:
  **Regenerează** (bypasses cache) and **Descarcă**.
- **Descarcă Excel** → direct `.xlsx` download.

Generation uses the filter's **month + year**. A *foaie de parcurs* is
monthly, so a specific month is **required**: when "Toate lunile" is selected,
the dropdown items are disabled with a hint "Selectează o lună".

## Backend

### Endpoints (`routes/route_sheet.py`, registered in `routes/__init__.py`)

- `POST /api/foi-parcurs/route-sheet/pdf` — body `{vin, year, month, regenerate?}`.
  Aggregate → AI → Playwright → PDF. Returns the PDF inline (`send_file`,
  `as_attachment=False`). Cached at
  `static/pdfs/foi-parcurs/routesheet-<vin>-<year>-<month>.pdf`;
  `regenerate=true` rebuilds.
- `GET /api/foi-parcurs/route-sheet/xlsx?vin=&year=&month=` — deterministic
  workbook, `as_attachment=True`.

Both `@login_required`; scope the aggregation to the caller's `company_id`
implicitly via the sessions' `company_id` (matches the tab's company filter).

### Service (`services/route_sheet_service.py`)

- `aggregate_month(vin, year, month) -> dict` — fetch the car's sessions via
  `FoiParcursRepository.get_contracts(vin=vin, per_page=big)`, filter to the
  period (`c.year ?? created_at`, `c.month ?? created_at`), sort by date.
  Attach vehicle (make/model/registration) and company legal (Prestator, via
  `CompanyRepository().get(company_id)` + `dealer_config` phone). Returns a
  **locked-facts** dict: `{company, vehicle, period, trips:[{date, km_start,
  km_end, distance_km, route_type, driver, itinerary}], totals:{km, sessions,
  clients}}`.
- `render_pdf(data, regenerate=False) -> path` — build a fixed HTML/CSS
  **skeleton** (header, Prestator block, trip table with real km/dates/drivers,
  totals, signature area). Call `llm_client.ask()` to compose Romanian
  **itinerary/purpose text per trip + a monthly summary** returned as a strict
  JSON map (`{trip_id: text, summary: text}`); we inject those into the
  skeleton. Render HTML→PDF with Playwright (sync API, headless Chromium).
- `render_xlsx(data) -> bytes` — `openpyxl` grid: title rows (car, period,
  company), trip table (Data, Traseu, Client/Șofer, KM start, KM end, KM
  parcurși, Tip), totals row.

### AI grounding / guardrails

AI receives the trip data but **only writes prose** into named slots
(itinerary/purpose per trip + summary). All numbers, dates, km, drivers are
rendered by us from the DB — the model cannot change them. System prompt:
"Nu inventa și nu modifica niciun număr sau dată; compune doar textul de
traseu/scop și un rezumat lunar; răspunde strict în JSON." Model
`claude-sonnet-4-6` via `llm_client.ask` (provider fallback chain). On AI
failure, fall back to the session's stored `itinerary` (no hard failure).

## Decisions

- **Excel is deterministic** (no AI) — it's a tabular log.
- **Month is required** for generation (disabled on "Toate lunile").
- **PDF cached** per (vin, year, month); "Regenerează" bypasses cache.

## Risks

- **Playwright Chromium on the server:** needs `playwright install chromium`
  in the DO build. Present locally. Mitigation: a startup check + a ReportLab
  fallback renderer if Chromium is missing (degraded layout, still valid).
- **AI latency** (a few seconds) → modal spinner; PDF cached after first build.
- **AI JSON parsing:** strict JSON extraction with a regex fallback (mirror
  `license_ocr_service._extract_json`); on parse failure use stored itineraries.

## Out of scope (YAGNI)

- Email delivery of the monthly sheet (existing per-contract email stays).
- Signatures capture on the monthly sheet (static signature area only).
- Bulk "generate all cars" — per-row only.
