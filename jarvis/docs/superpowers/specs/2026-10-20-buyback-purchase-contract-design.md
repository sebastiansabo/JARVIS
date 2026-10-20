# BuyBack Purchase Contract — Design Spec

**Date:** 2026-10-20
**Status:** Draft for review
**Module:** BuyBack (+ CarPark hand-off, Settings)

## 1. Goal

When a seller **accepts the final BuyBack offer** (record → `BOUGHT`), automatically generate a **purchase contract** PDF from a **per-company × brand** template, filled with the vehicle, seller, dealer, and price data, with the **seller's digital signature embedded**. The generated contract:

- is **delivered to the advisor** (emailed) and stored on the record,
- **appears in the "Documente" section** on the car's BuyBack detail page (download + regenerate),
- **travels with the VIN into CarPark** when the record is finalized/handed off.

## 2. Decisions (from brainstorming, 2026-10-20)

| Decision | Choice |
|---|---|
| Seller legal identity | **Collect full ID** (person: CNP + CI serie/nr + address; company: nr. reg + IBAN + reprezentant legal) |
| Template granularity | **Per company × brand** |
| Signature | **Digital** — captured at acceptance, embedded in the PDF |
| Scope now | **Purchase contract only** (final-offer accept). Consignment/custody deferred. |
| Architecture | **Approach B** — BuyBack owns its contract subsystem; reuse only pure helpers/patterns from the Test-Drive engine (no cross-module coupling, no risk to live TD contracts). |

## 3. What is reused (no new build)

- **Template substitution**: copy the pure `{token}` replacer from `foi_parcurs/services/contract_template.py` into BuyBack (≈20 lines, whitelisted tokens — no Jinja2, no injection surface).
- **PDF recipe**: model the renderer on `foi_parcurs/services/pdf_service.py::generate_service_pdf` (per-company body text + Prestator block + signature, reportlab). **Must register a Unicode TTF font** (as TD does) so Romanian diacritics render correctly — a legal document cannot ASCII-fold like `offer_pdf.py`.
- **Dealer legal data**: existing `companies` columns (`reg_no, vat, iban, bank, swift, street, city, county, administrator, showroom_address, gdpr_text`).
- **Document storage/UI/download**: `photo_repository.store_documents` (private Spaces), the detail-page "Documente" section (`PhotoGallery.tsx`), and the authenticated/IDOR-guarded `download_photo` route — a contract stored as a document appears + downloads with **zero new UI**.
- **Delivery to advisor**: the offer-email attachment path (`email.py::_build_offer_attachments` + `_resolve_advisor_contact` + `send_email`).
- **Signature pad**: reuse the Test-Drive drawn-signature capture component.
- **Settings shell**: `Settings/BuyBackTab.tsx` + `buyback/routes/settings.py` pattern; template editor ported from `FoiParcurs/ContractConfigSection.tsx`.

## 4. Data model

### 4.1 `buyback_records` — new seller-identity columns (idempotent `ADD COLUMN IF NOT EXISTS`)
- Person: `seller_cnp VARCHAR(13)`, `seller_ci_serie VARCHAR(10)`, `seller_ci_number VARCHAR(20)`, `seller_address TEXT`
- Company: `seller_reg_no VARCHAR(30)`, `seller_iban VARCHAR(34)`, `seller_legal_rep VARCHAR(255)`

Wired into `_CREATE_FIELDS`, `_UPDATABLE_COLUMNS`, serialization, and `_INTAKE_TEXT_FIELDS` (so bad values 400, not 500). **Not** added to the lean `_LIST_COLUMNS` (not needed in the list). CRM sync: extend `_sync_client_contact` to push the fields CRM supports (`cnp`, `street/city`, `nr_reg`, `responsible`) to `crm_clients`. CI serie/number + client IBAN have **no** CRM column → they live on `buyback_records` as the contract's source of truth.

### 4.2 `buyback_contract_templates` — new table
```
id BIGSERIAL PK,
company_id BIGINT NOT NULL,
brand_id BIGINT,                       -- NULL = company-wide default
document_type VARCHAR(20) NOT NULL DEFAULT 'purchase',
title VARCHAR(255),
body_template TEXT,                    -- legal text with {tokens}
general_conditions TEXT,
is_active BOOLEAN NOT NULL DEFAULT TRUE,
created_by INTEGER, updated_by INTEGER,
created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
UNIQUE (company_id, brand_id, document_type)
```
DDL (idempotent) in `schema_buyback.py`. Repo `ContractTemplateRepository`: `get_active(company_id, brand_id, type)` (brand-specific → company default fallback), `upsert(...)`, `list_for_company(...)`.

### 4.3 Document type `'contract'`
Add `'contract'` to the `_DOC_TYPES` whitelists (`photo_repository.py`, `routes/photos.py`). Stored in `buyback_photos` with `photo_type='contract'`, private Spaces key `private/buyback/<record_id>/contract-<uuid>.pdf`.

## 5. Template engine + renderer

- `buyback/services/contract_template.py` — copied pure `render_contract_template(template, context)`; whitelist tokens:
  `client_name, client_type, client_cnp, client_ci, client_address, client_cui, client_reg_no, client_iban, client_legal_rep, company_name, company_address, company_reg_no, company_vat, company_iban, company_bank, company_administrator, brand, model, vin, mileage, first_registration, manufacture_date, price, price_words, contract_date, advisor_name`.
- `buyback/services/contract_pdf.py` — context builder (record + CRM fallback + `companies` legal cols + accepted offer amount + signature image) → reportlab: title, substituted `body_template`, `general_conditions`, a two-party block with the **embedded seller signature image** and a dealer signature line (signatory = `companies.administrator`). Unicode TTF registered for diacritics.
- `price` = the **accepted final offer's `amount_eur`** (at accept-time `purchase_price_eur` is still NULL; it's stamped later at finalize). Optional `price_words` (RO number-to-words) — **confirm if legally required**.

## 6. Accept → generate → deliver flow

1. **Frontend** (`ActionPanel.tsx`): on `FINAL_OFFER`, "Client a acceptat" opens a **signature dialog** (TD signature pad) → `recordDecision(accepted, { signature })`.
2. **Backend** (`routes/offers.py::record_decision` + `buyback_service.record_decision`): accept the optional `signature` (data-URL). On the final-offer accept → `BOUGHT` branch, **after** the transition, best-effort `contract.generate_contract(record, offer, signature)`:
   - render PDF → store as a `'contract'` document → email the advisor with it attached.
   - **Best-effort**: wrapped + swallowed so a generation/email failure **never** blocks the accept/`BOUGHT` (mirrors `notify_owner`/`send_offer_email`).
   - **Skip + warn** (don't fail) when no active template is configured or required seller fields are missing; surface a non-blocking warning in the response + telemetry.
3. **Regenerate** on the car page: `POST /records/<id>/contract` re-renders and replaces the `'contract'` document (reusing the stored signature, or re-signing). Gated `record.edit`.

## 7. CarPark carry-over (fixes a latent bug)

`carpark_handoff`:
- Restrict `_carry_photos` to `photo_type='gallery'` only (today it sweeps **all** rows — documents get re-uploaded as `.jpg` gallery images and can even become the cover photo).
- Add `_carry_documents(record_id, veh_id)` routing `photo_type in {document, civ, talon, contract}` rows to `carpark.repositories.document_repository.DocumentRepository.create(...)` with the **correct MIME/extension**, mapping `document_type` (contract → a carpark document type). The contract then rides the VIN into `carpark_vehicle_documents` and shows in the CarPark document UI.

## 8. Permissions / security

- Generation fires under the existing `record.edit` accept gate; regenerate = `record.edit`; template settings = admin-only (buyback settings pattern).
- Seller PII (CNP/CI/IBAN) and the contract PDF are stored **private** in Spaces; download is authenticated + IDOR-guarded (existing route). The record-export PDF already **excludes** documents. **No live PII in tests**; keep CNP/IBAN out of logs.

## 9. Testing (TDD)

- **Schema**: new columns + `buyback_contract_templates` exist (idempotent).
- **Repo**: template upsert/`get_active` (brand → company fallback); record create/update persists seller-ID fields; bad numeric/text → 400.
- **Template render**: token substitution, missing-token safety, no injection/escape issues.
- **Contract PDF**: valid PDF, diacritics present (PyPDF2 text extract), embedded signature, price from offer.
- **Accept flow**: `record_decision(accepted, signature)` on final offer → `BOUGHT` **and** a `'contract'` document created + advisor email attempted; missing template/fields → accept still succeeds, no contract, warning surfaced.
- **CarPark carry-over**: a `'contract'` document lands in `carpark_vehicle_documents` (not the gallery, not cover) with correct MIME after finalize; gallery photos still carry as before.
- **Frontend**: signature dialog on accept; settings template editor; car-page generate/regenerate; "Documente" shows the contract.
- Backend DB tests run with `DATABASE_URL=postgresql://localhost/defaultdb`; email tests stub SMTP (autouse mute).

## 10. Phasing (4 shippable PRs, each staging→prod)

- **P1 — Seller legal identity**: columns + "Date vânzător" sub-form (person/company conditional) + CRM sync. Independent, immediately useful.
- **P2 — CarPark document carry-over fix**: independent, fixes the latent gallery-corruption bug.
- **P3 — Template engine + Settings zone + renderer + manual "Generează contract" button** on the car page (no auto-trigger yet). Lets you configure templates and generate on demand.
- **P4 — Accept-time signature capture + auto-generate + deliver**. Wires it to the "Client a acceptat" action.

## 11. Out of scope (now)

Consignment/custody contracts (future template types); dealer-side digital signature; certified e-signature / qualified timestamping; bulk regeneration.

## 12. Open items / risks

- **Diacritics font**: must register a Unicode TTF in the renderer (verify the exact approach in `pdf_service.py`). Blocking for legible legal text.
- **`crm_clients` lacks CI serie/number + IBAN** → stored only on `buyback_records` (accepted; the record is the contract's source of truth).
- **Price in words** (RO): include only if legally required — confirm.
- **Dealer signatory**: defaults to `companies.administrator`; confirm per-company overrides aren't needed.
- **Signature re-use on regenerate**: reuse stored signature vs force re-sign — default to reusing, allow re-sign.
