# Service Courtesy-Car — Rental Pricing + AutoWorld Contract — Design

- **Date:** 2026-08-24
- **Branch:** `feature/foi-parcurs-service-impl` (extends the shipped Service context; currently on staging)
- **Status:** Design — building on the branch
- **Builds on:** `2026-08-24-foi-parcurs-service-courtesy-cars-design.md` (the Service/document_type context)

## 1. Problem

The Service ("Mașini de curtoazie") context now exists (document_type axis, separate fleet pool, per-company+brand contract config, templated PDF). This adds the **rental layer**: each courtesy car has its own price, a tariffs policy governs km/deposit/franchise, a Service session auto-computes the rental like a rent-a-car system, and the exported contract is the **real AutoWorld închiriere contract** (face + terms) filled per company. **Sales/test-drive is entirely unaffected** — all of this is gated to `document_type='service'`.

## 2. Decisions (locked)

| Question | Decision |
|---|---|
| Contract source | The two legacy AutoWorld docs (face `rev6` + termeni-condiții `rev7_2023`), `~/Desktop/cortoazie` |
| Seed scope | Every active **(company, brand)** gets the contract config |
| Prestator legal identity | **Each company's own** details — via `{company_*}` placeholders resolved from the `companies` row (one template serves all) |
| Missing face fields | **Captured digitally** (form), derived from the contract |
| Car pricing | **Daily rate + monthly rate** per car; system picks by duration |
| Tariffs policy scope | **Per car, with a company default** fallback |
| Daily vs monthly | **< 30 days → daily** (rate × days); **≥ 30 days → monthly** (rate × ceil(days/30)); advisor may override the computed total |
| Currency | EUR (contract paid in RON at Autoworld curs — display note only) |

## 3. Grounding (what already exists — no duplication)

- `companies` already has the full Prestator block: `company, vat, reg_no, iban, bank, swift, street, city, county, postal_code, administrator, gdpr_text`. → per-company legal identity needs no new table.
- `crm_clients` has `street, city, region, email, cui, company_name, nr_reg, driver_license_number, cnp`; `crm_client_contacts` has `driver_license_serie` (C.I.). → Beneficiar block + C.I. serie already available.
- `fp_vehicles` (pool via `document_type`), `foi_de_parcurs` (Service sessions), `fp_contract_configs` (per company+brand template), `fp_company_config` (per-company), `generate_service_contract_pdf` (renders template+blocks) — all from the prior build.

## 4. Data model (idempotent additive DDL, `schema_incremental.py`)

**4.1 Per-car price + policy override** — `fp_vehicles`:
```
svc_tariff_eur_day    NUMERIC(10,2)   -- daily rate (Service cars)
svc_tariff_eur_month  NUMERIC(10,2)   -- monthly rate
svc_km_included_day   INTEGER         -- NULL = use company default
svc_extra_km_eur      NUMERIC(10,2)   -- NULL = default
svc_deposit_eur       NUMERIC(10,2)   -- garanție; NULL = default
svc_franchise_eur     NUMERIC(10,2)   -- franșiză; NULL = default
```

**4.2 Company default policy** — `fp_company_config`:
```
svc_km_included_day   INTEGER
svc_extra_km_eur      NUMERIC(10,2)
svc_deposit_eur       NUMERIC(10,2)
svc_franchise_eur     NUMERIC(10,2)
```

**4.3 Session pricing snapshot** — `foi_de_parcurs` (frozen at create/activate so a later price change never rewrites a signed contract):
```
svc_rate_basis    VARCHAR(8)     -- 'day' | 'month'
svc_tariff_eur    NUMERIC(10,2)  -- applied unit rate
svc_units         INTEGER        -- days or months charged
svc_total_eur     NUMERIC(12,2)
svc_km_included_day INTEGER
svc_extra_km_eur  NUMERIC(10,2)
svc_garantie_eur  NUMERIC(10,2)
svc_fransiza_eur  NUMERIC(10,2)
svc_order_ref  -- already exists as service_order_ref
```

## 5. Pricing service (pure, testable)

`compute_service_pricing(vehicle, company_policy, departure, return_dt) -> dict`:
- `days = ceil((return - departure) / 24h)`, min 1.
- basis = `'month'` if `days >= 30` else `'day'`; `units = ceil(days/30)` if month else `days`.
- `rate = vehicle.svc_tariff_eur_month if month else vehicle.svc_tariff_eur_day`.
- `total = rate * units`.
- policy fields resolve **car value ?? company default ?? None**.
- Returns the snapshot dict. Advisor override on the form replaces `total`/fields before persist.
- Pure function (no DB) → unit-tested.

## 6. UI

**6.1 Vehicle add/edit** (existing `VehicleFormFields`) — when pool = *Mașini de curtoazie*, reveal a **Preț & politică** section: daily rate, monthly rate, and optional km/day, extra-km €, garanție, franșiză (placeholder text shows the company default when blank).

**6.2 Company default policy** — in the Settings setup zone, alongside the contract editor: km/day, extra-km €, garanție, franșiră defaults per company.

**6.3 Service session form** — after car + dates chosen, show an auto-filled **rental summary**: basis (zi/lună), rate, units, **total €**, garanție, franșiză, km inclus/zi, extra-km €. Editable. Persisted as the snapshot.

## 7. Contract templates (S2) — authored from the docx

**`body_template` (face)** — placeholders throughout: Prestator `{company_name} {company_street} {company_city} {company_reg_no} {company_vat} {company_iban} {company_bank} {company_administrator} {dealer_phone}`; Beneficiar `{client_name} {client_address} {client_ci_serie} {client_phone} {client_email} {client_company} {client_cui}`; vehicul `{brand} {vehicle_model} {vin} {registration_number}`; perioadă `{departure_datetime} {return_datetime}`; `{km_start} {km_end}`; comercial `{svc_tariff_eur} {svc_rate_basis} {svc_units} {svc_total_eur} {svc_limita_km_zi} {svc_extra_km_eur} {svc_garantie_eur} {svc_fransiza_eur}`.

**`general_conditions` (T&C rev7)** — the 12 numbered sections verbatim + the **"Valoarea facturabilă a daunelor"** price table + GDPR (RO+EN) + consent lines.

Seeded (S4) for every (company, brand); each PDF resolves its own company's legal block.

## 8. PDF (S6) — `generate_service_contract_pdf`, ordered

1. Title (from config).
2. **Părțile** — Prestator (company legal block) + Beneficiar (client), rendered from the body_template prose.
3. **Obiect** — vehicul + perioadă.
4. **Predare/Primire** — KM predare/preluare + daune (existing structured blocks).
5. **Tarif** — rate/basis/units/total, limită km/zi, extra-km, garanție, franșiză (from snapshot).
6. **Condiții generale** — numbered T&C sections.
7. **Damage price table** — real ReportLab table.
8. **GDPR + consimțământ + semnături** — existing signature blocks.
Context dict extended: fetch the `companies` row (Prestator) + client `cui`/`company`/C.I. serie (from crm) + the svc_* snapshot. No-config → fallback to legal PDF (unchanged).

## 9. Scope / tasks

S1 schema (car price+policy, company default, session snapshot) · S2 author face + T&C templates · S3 pricing service (pure, TDD) · S4 extend PLACEHOLDERS + PDF context (company legal + client cui/ci + snapshot) · S5 seed fp_contract_configs per (company,brand) idempotent · S6 vehicle price/policy UI + company-default UI + session rental summary + payload/persist + auto-fill · S7 ordered PDF render (face + T&C + damage table + GDPR).

## 10. Isolation / safety

All `svc_*` reads/writes and the pricing/PDF branches are gated on `document_type='service'`. Sales sessions never touch pricing. Existing rows default NULL (no pricing) → Sales unchanged. Idempotent DDL; parameterised SQL.

## 11. Open / deferred

- Duration-discount tiers beyond day/month — deferred.
- Actual invoice/eurofib billing from the rental — out of scope (contract only).
- The face's two-column daune/observatii layout — render structurally in code (reuse existing damage block).
