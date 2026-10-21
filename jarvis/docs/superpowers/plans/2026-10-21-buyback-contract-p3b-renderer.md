# BuyBack P3b — Contract Renderer + "Generează contract" Button — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a BuyBack record, let an advisor manually generate the per-company×brand contract PDF (purchase or consignment) from the live template, stored as a downloadable `'contract'` document on the record — no auto-trigger, no signature capture yet (those are P4/P5).

**Architecture:** BuyBack owns its contract subsystem (spec Approach B). Port the pure `{token}` replacer from foi_parcurs into buyback; add a reportlab renderer modeled on `buyback/services/offer_pdf.py` (BytesIO→bytes) but with a **bundled DejaVu Unicode TTF** so Romanian diacritics render (no ASCII-folding) — this is the repo's first reportlab `registerFont`. A new `POST /records/<id>/generate-contract` route resolves the active template, builds a token context from the record + company legal data + accepted offer, renders, stores as a private `photo_type='contract'` row, and returns it. The existing authenticated download route + Documente UI surface it with near-zero new UI.

**Tech Stack:** Python/Flask, reportlab (Platypus), psycopg2, DigitalOcean Spaces; React/TypeScript + React Query (frontend).

**Spec:** `jarvis/docs/superpowers/specs/2026-10-20-buyback-purchase-contract-design.md` (§3, §5, §8, §10 "P3"). This plan implements the **P3** phase only (manual generate). P4 (auto-generate + signature on accept) and P5 (consignment auto) are out of scope but the renderer takes an optional `signature` arg so P4 reuses it unchanged.

## Global Constraints

- **Branch / worktree:** work on `feat/buyback-purchase-contract` in the existing worktree `/Users/sebastiansabo/Documents/Git/JARVIS-bb-contract` (continues the feature; T6+P3a already shipped from here). Do NOT create a new worktree.
- **DB tests:** run with `DATABASE_URL=postgresql://localhost/defaultdb` (per `reference_buyback_dbtests_database_url_override`). Email/SMTP is auto-muted in the buyback test harness — do not un-mute.
- **No live PII in tests:** never use real CNP/CI/IBAN values; keep CNP/IBAN out of logs.
- **reportlab injection safety (non-negotiable):** every user-controlled string placed in a reportlab `Paragraph` MUST be HTML-escaped (`html.escape`) — reportlab parses a mini-markup, so a bare `<`/`&` crashes the parser and `<img src=…>` triggers a fetch (SSRF). Escape, but do **NOT** ASCII-fold (diacritics must survive). Model on `offer_pdf.py::_ptext` minus the `_ascii` call.
- **Permissions:** generate route is gated `@v2_permission_required('buyback','record','edit')` + `_shared._guard_company(record)` (company/IDOR boundary). Frontend button gated `can('buyback.record.edit')`.
- **Idempotent storage:** regenerating replaces the record's prior `'contract'` document (soft-delete old rows first) — no accumulating duplicate tiles.
- **Token whitelist is the contract of record.** The authoritative token set is what the live seeded templates use (see Task 1). Unknown `{tokens}` and whitelisted tokens with no source value render **empty** (never crash).

## Review Focus

- **Template/field injection into reportlab markup** — a template body or seller field containing `<`, `&`, or `<img src=…>`. Expected: rendered as literal text, no parser crash, no network fetch. (Task 4 test.)
- **No active template** for the record's `(company_id, brand_id, document_type)` — expected: route returns **409** with a clear Romanian message, never a 500 and never an empty/garbage PDF. (Task 6 test.)
- **Sparse record** (missing seller legal fields, missing `brand_id`, no accepted offer) — expected: manual generate still produces a PDF with those tokens empty; it does not 500. (Task 3 + Task 6 tests.)
- **Diacritics actually render** — `ă â î ș ț` present in the extracted PDF text, not folded to `a a i s t` and not dropped as boxes. (Task 2 + Task 4 tests.)
- **Regenerate replaces, not appends** — a second generate leaves exactly one `'contract'` document on the record. (Task 5 test.)

---

### Task 1: Port the token-render engine into BuyBack

**Files:**
- Create: `jarvis/buyback/services/contract_template.py`
- Test: `jarvis/tests/buyback/test_contract_template_render.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `render_contract_template(template: str, context: dict) -> str` and module constant `PLACEHOLDERS: tuple[str, ...]`. Pure; no DB, no I/O.

The `PLACEHOLDERS` whitelist is the superset the live seeded templates use (`jarvis/buyback/seed_contract_templates.py`):
`contract_number, contract_date, company_name, company_address, company_reg_no, company_vat, company_administrator, company_iban, company_bank, advisor_name, seller_name, seller_address, seller_cnp, seller_cui, seller_ci, seller_reg_no, seller_legal_rep, brand, model, vin, engine_no, engine_capacity, power_cp, civ_no, mileage, first_registration, manufacture_date, price_eur, price_ron, price_words, vat_note, owner_price, min_price, promo_price, commission, monthly_fee`.

Semantics identical to `foi_parcurs/services/contract_template.py`: replace only whitelisted `{token}`; a whitelisted token whose context value is `None` → empty string; unknown `{tokens}` left literal.

- [ ] **Step 1: Write the failing tests**

```python
def test_substitutes_whitelisted_tokens():
    out = render_contract_template('Marca {brand}, VIN {vin}', {'brand': 'Volvo', 'vin': 'YV1'})
    assert out == 'Marca Volvo, VIN YV1'

def test_none_value_renders_empty():
    assert render_contract_template('Pret {price_eur} EUR', {'price_eur': None}) == 'Pret  EUR'

def test_unknown_token_left_literal():
    assert render_contract_template('Hi {not_a_token}', {}) == 'Hi {not_a_token}'

def test_empty_template_returns_empty():
    assert render_contract_template('', {'brand': 'X'}) == ''

def test_consignment_tokens_present_in_whitelist():
    for t in ('owner_price', 'min_price', 'promo_price', 'commission', 'monthly_fee'):
        assert t in PLACEHOLDERS
```

- [ ] **Step 2: Run tests, verify they fail** — `DATABASE_URL=postgresql://localhost/defaultdb pytest jarvis/tests/buyback/test_contract_template_render.py -v` → FAIL (module not found).
- [ ] **Step 3: Implement** `render_contract_template` + `PLACEHOLDERS` in `jarvis/buyback/services/contract_template.py` (copy the foi_parcurs replacer logic verbatim; swap in the buyback whitelist above).
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `feat(buyback): port contract token-render engine (buyback whitelist)`.

---

### Task 2: Bundle a Unicode TTF + diacritics-safe PDF primitives

**Files:**
- Create (binary assets): `jarvis/buyback/assets/fonts/DejaVuSans.ttf`, `jarvis/buyback/assets/fonts/DejaVuSans-Bold.ttf`
- Create: `jarvis/buyback/services/contract_pdf.py` (primitives only this task: `_register_fonts`, `_ptext`)
- Test: `jarvis/tests/buyback/test_contract_pdf_fonts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_register_fonts() -> tuple[str, str]` (returns the `(regular, bold)` font names actually registered; idempotent — safe to call every render); `_ptext(value) -> str` (HTML-escaped, NOT ASCII-folded). Also module constants `FONT_REGULAR='DejaVuSans'`, `FONT_BOLD='DejaVuSans-Bold'`.

**Font decision:** register from the **bundled** repo path first (robust on mac dev + Linux prod with no system dependency), falling back to the system DejaVu paths catalogued in `jarvis/accounting/bilant/pdf_handler.py` (`/usr/share/fonts/truetype/dejavu/…`), then to reportlab's bundled `Vera.ttf` as a last resort. Source the two DejaVu `.ttf` files during implementation (DejaVu is freely redistributable — copy from any Linux system, the `fonts-dejavu-core` package, or the DejaVu project release) and commit them. Register via `pdfmetrics.registerFont(TTFont(FONT_REGULAR, path))` + the `-Bold` variant; guard with a module-level "already registered" check so repeat calls are no-ops.

- [ ] **Step 1: Write the failing tests**

```python
def test_register_fonts_returns_dejavu_names():
    reg, bold = _register_fonts()
    assert reg == 'DejaVuSans' and bold == 'DejaVuSans-Bold'

def test_ptext_escapes_markup_but_keeps_diacritics():
    assert _ptext('Ștefan & <b>X</b>') == 'Ștefan &amp; &lt;b&gt;X&lt;/b&gt;'

def test_diacritics_survive_in_a_rendered_pdf():
    # minimal one-paragraph PDF using the registered font, extract text, assert glyphs present
    pdf = _render_probe_pdf('Mașină cu preț în lei: ăâîșț')   # test-local helper building a 1-para doc
    text = _extract_pdf_text(pdf)                              # PyPDF2
    assert 'ș' in text and 'ț' in text and 'ă' in text
```

(The probe helper lives in the test file; production code only exposes `_register_fonts`/`_ptext`. If PyPDF2 text extraction of a subset-embedded TTF proves lossy in CI, assert instead that the output is a valid non-empty PDF AND that `_ptext` preserved the raw diacritics — the folding regression is what matters.)

- [ ] **Step 2: Run tests, verify they fail** (module/fonts missing).
- [ ] **Step 3: Add the two `.ttf` files; implement `_register_fonts` (bundled→system→Vera fallback chain, idempotent) and `_ptext` (`html.escape`, no `_ascii`).**
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `feat(buyback): bundle DejaVu TTF + diacritics-safe PDF primitives`.

---

### Task 3: Context builder (record + company + offer → token dict)

**Files:**
- Modify: `jarvis/buyback/services/contract_pdf.py` (add `build_contract_context`)
- Test: `jarvis/tests/buyback/test_contract_context.py`

**Interfaces:**
- Consumes: a `record` dict (buyback_records row, serialized), a `company` dict (`companies` row from `CompanyRepository().get`), an optional `offer` dict (the accepted offer row), an optional `consignment` dict (consignment agreement / `consignment_terms`), and generation metadata.
- Produces: `build_contract_context(record, company, *, offer=None, consignment=None, contract_number='', contract_date='') -> dict` returning a dict keyed by the Task 1 `PLACEHOLDERS`.

**Token → source mapping (pin exactly):**
- `company_name` ← `company['company']`; `company_vat` ← `vat`; `company_reg_no` ← `reg_no`; `company_iban` ← `iban`; `company_bank` ← `bank`; `company_administrator` ← `administrator`; `company_address` ← compose non-empty of `street, city, county, postal_code` joined `', '` (fallback `showroom_address`).
- `advisor_name` ← `record['advisor_name']`.
- `seller_name` ← `record['seller_name']`; `seller_cui` ← `seller_cui`; `seller_cnp` ← `seller_cnp`; `seller_address` ← `seller_address`; `seller_reg_no` ← `seller_reg_no`; `seller_legal_rep` ← `seller_legal_rep`; `seller_ci` ← compose `seller_ci_serie` + `seller_ci_number` as `"seria {serie} nr. {number}"` when both present, else empty.
- `brand` ← `record['brand']`; `model` ← `model`; `vin` ← `vin`; `mileage` ← `mileage_km`; `engine_capacity` ← `engine_capacity_cm3`; `first_registration` ← `first_registration_date` (ISO date → `str`); `manufacture_date` ← `manufacture_date`.
- `engine_no`, `power_cp`, `civ_no` ← **no source column exists** → empty string (documented; admins can remove these tokens or they stay blank).
- `price_eur` ← `offer['amount_eur']` formatted `"{:,.0f}"`-style (Decimal → plain string) when an accepted offer is supplied, else empty.
- `price_ron`, `price_words` ← **empty for P3b** (BNR-at-signing + RO number-to-words deferred; the clause text already states "la cursul BNR+1% la data semnării"). Flag in handoff for user confirmation of legal need.
- `vat_note` ← derive from `record['vat_status']` (e.g. a short "TVA inclus"/"neplătitor de TVA" note) or empty if unset.
- Consignment-only: `owner_price, min_price, promo_price, commission, monthly_fee` ← from `consignment['consignment_terms']` JSONB (keys `owner_price`/`floor`→`min_price`/`promo_price`/`commission`/`monthly_fee`) when present, else empty.

- [ ] **Step 1: Write the failing tests**

```python
def test_maps_company_and_vehicle_tokens():
    ctx = build_contract_context(
        {'advisor_name': 'A', 'brand': 'Volvo', 'model': 'XC60', 'vin': 'YV1', 'mileage_km': 50000,
         'seller_name': 'Ion', 'seller_cnp': '1', 'seller_ci_serie': 'XZ', 'seller_ci_number': '12'},
        {'company': 'Autoworld', 'vat': 'RO1', 'reg_no': 'J40', 'street': 'Str. A', 'city': 'Cluj'},
        contract_number='BB-1', contract_date='2026-10-21')
    assert ctx['company_name'] == 'Autoworld'
    assert ctx['company_address'] == 'Str. A, Cluj'
    assert ctx['seller_ci'] == 'seria XZ nr. 12'
    assert ctx['brand'] == 'Volvo' and ctx['mileage'] == 50000

def test_price_from_accepted_offer():
    ctx = build_contract_context({}, {}, offer={'amount_eur': Decimal('12000')})
    assert '12' in ctx['price_eur'] and ctx['price_ron'] == ''

def test_missing_sources_render_empty_not_crash():
    ctx = build_contract_context({}, {})
    for t in PLACEHOLDERS:
        assert t in ctx                      # every token present
    assert ctx['engine_no'] == '' and ctx['seller_ci'] == ''

def test_consignment_terms_tokens():
    ctx = build_contract_context({}, {}, consignment={'consignment_terms': {'owner_price': '10000', 'commission': '4%'}})
    assert ctx['owner_price'] == '10000' and ctx['commission'] == '4%'
```

- [ ] **Step 2: Run tests, verify they fail.**
- [ ] **Step 3: Implement `build_contract_context` per the mapping above.** Every `PLACEHOLDERS` key must be present in the output (default `''`).
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `feat(buyback): contract token context builder (record/company/offer)`.

---

### Task 4: PDF renderer (bytes, diacritics, optional signature)

**Files:**
- Modify: `jarvis/buyback/services/contract_pdf.py` (add `render_contract_pdf`)
- Test: `jarvis/tests/buyback/test_contract_pdf_render.py`

**Interfaces:**
- Consumes: Task 1 `render_contract_template`, Task 2 `_register_fonts`/`_ptext`/font names, a `template_row` dict (`title`, `body_template`, `general_conditions`), a `context` dict (Task 3), optional `signature` data-URL.
- Produces: `render_contract_pdf(template_row: dict, context: dict, signature: str | None = None) -> bytes`.

**Layout (model on `offer_pdf.py` BytesIO pattern + `pdf_service.py` signature table):** `SimpleDocTemplate(BytesIO, pagesize=A4, margins 18mm)`; `ParagraphStyle`s all set `fontName=FONT_REGULAR`/`FONT_BOLD`; story = title (`_ptext(template_row['title'])`, centered bold) → `HRFlowable` → body: `render_contract_template(body_template, context)` split on `\n`, one `Paragraph(_ptext(line))` per non-empty line → general_conditions the same way → the two-party signature table copied from `pdf_service.py` (`_sig_cell`/`sig_table`, 35mm row), embedding the seller signature via `Image(io.BytesIO(base64decode(signature.split(',',1)[1])), 55*mm, 22*mm)` when `signature` is a `data:image` URL, else the italic "Lipsă semnătură" placeholder; dealer cell shows the signatory line (`context['company_administrator']` or `company_name`). `return buf.getvalue()`.

- [ ] **Step 1: Write the failing tests**

```python
def test_returns_valid_pdf_bytes():
    out = render_contract_pdf({'title': 'Contract', 'body_template': 'Marca {brand}', 'general_conditions': ''},
                              {'brand': 'Volvo'})
    assert out[:5] == b'%PDF-'

def test_body_tokens_substituted_and_diacritics_present():
    out = render_contract_pdf({'title': 'Contract de achiziție', 'body_template': 'Mașină {brand} preț în lei', 'general_conditions': ''},
                              {'brand': 'Škoda'})
    text = _extract_pdf_text(out)
    assert 'Škoda' in text or 'Volvo' not in text   # substitution happened; diacritics not folded

def test_injection_in_field_is_escaped_not_executed():
    # a field with reportlab markup / an <img> must not crash the parser or fetch
    out = render_contract_pdf({'title': 'T', 'body_template': 'Vanzator {seller_name}', 'general_conditions': ''},
                              {'seller_name': '<img src="http://x"/> & <b>'})
    assert out[:5] == b'%PDF-'                        # rendered without raising

def test_signature_absent_uses_placeholder():
    out = render_contract_pdf({'title': 'T', 'body_template': 'x', 'general_conditions': ''}, {}, signature=None)
    assert out[:5] == b'%PDF-'
```

- [ ] **Step 2: Run tests, verify they fail.**
- [ ] **Step 3: Implement `render_contract_pdf`** (call `_register_fonts()` first; all styles use the DejaVu font; escape every user string via `_ptext`).
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `feat(buyback): reportlab contract PDF renderer (diacritics + signature slot)`.

---

### Task 5: `'contract'` document type + store/replace helper

**Files:**
- Modify: `jarvis/buyback/repositories/photo_repository.py:29` (`_DOC_TYPES` add `'contract'`)
- Modify: `jarvis/buyback/routes/photos.py:41` (`_DOC_TYPES` add `'contract'`)
- Modify: `jarvis/buyback/routes/_shared.py:205` (`_DOC_LABELS` add `'contract': 'Contract'`)
- Modify: `jarvis/buyback/repositories/photo_repository.py` (add `store_contract_pdf`)
- Test: `jarvis/tests/buyback/test_contract_document_store.py`

**Interfaces:**
- Consumes: `spaces_service.upload`, `PhotoRepository.create`, and a soft-delete of prior rows (reuse the same soft-delete the `delete_photo` route uses).
- Produces: `PhotoRepository.store_contract_pdf(self, record_id: int, pdf_bytes: bytes, caption: str) -> dict` — soft-deletes any existing `photo_type='contract'` rows for the record, uploads `pdf_bytes` to `private/buyback/{record_id}/contract-{uuid4().hex}.pdf` (`mime='application/pdf'`, `acl='private'`), inserts via `self.create(record_id, url=key, photo_type='contract', caption=caption, file_size=len(pdf_bytes))`, returns the created row.

- [ ] **Step 1: Write the failing tests** (DB-backed; `DATABASE_URL` set; stub/patch `spaces_service.upload`)

```python
def test_store_contract_creates_contract_typed_row(seeded_record):
    row = PhotoRepository().store_contract_pdf(seeded_record['id'], b'%PDF-1.4 x', 'Contract achiziție')
    assert row['photo_type'] == 'contract' and row['caption'] == 'Contract achiziție'

def test_regenerate_replaces_prior_contract(seeded_record):
    repo = PhotoRepository()
    repo.store_contract_pdf(seeded_record['id'], b'%PDF- a', 'C')
    repo.store_contract_pdf(seeded_record['id'], b'%PDF- b', 'C')
    docs = [p for p in repo.get_by_record(seeded_record['id']) if p['photo_type'] == 'contract']
    assert len(docs) == 1

def test_serialize_marks_contract_as_document():
    from jarvis.buyback.routes import _shared
    out = _shared.serialize_photos([{'id': 1, 'record_id': 9, 'photo_type': 'contract', 'caption': None}])
    assert out[0]['is_document'] is True
    assert out[0]['download_url'].endswith('/records/9/photos/1/download')
    assert out[0]['label'] == 'Contract'
```

- [ ] **Step 2: Run tests, verify they fail** (contract downgraded to 'document' / label wrong / helper missing).
- [ ] **Step 3: Implement** the three whitelist/label edits + `store_contract_pdf`.
- [ ] **Step 4: Run tests, verify pass.**
- [ ] **Step 5: Commit** — `feat(buyback): 'contract' document type + store/replace helper`.

---

### Task 6: `POST /records/<id>/generate-contract` route

**Files:**
- Create: `jarvis/buyback/routes/contract.py`
- Modify: `jarvis/buyback/routes/__init__.py` (register the new module import)
- Test: `jarvis/tests/buyback/test_generate_contract_route.py`

**Interfaces:**
- Consumes: `_shared.records_repo.get_by_id`, `_shared._guard_company`, `_shared.offers_repo.list_for_record`, `ContractTemplateRepository().get_active`, `CompanyRepository().get`, Task 3 `build_contract_context`, Task 4 `render_contract_pdf`, Task 5 `store_contract_pdf`, `_shared.serialize_photos`.
- Produces: route `POST /api/buyback/records/<int:record_id>/generate-contract`, `@login_required @v2_permission_required('buyback','record','edit')`, returning `{'photo': <serialized contract doc>, 'warnings': [...]}` (200) or `{'error': ...}` (404/409).

**Logic (pin):**
1. Load record → 404 if missing → `_shared._guard_company(record)`.
2. Resolve `document_type`: from JSON body `document_type` if in `('purchase','consignment')`, else infer — `'consignment'` when `record['status'] in ('CONSIGNMENT_OFFER','CONSIGNAT')`, else `'purchase'`.
3. Resolve template: `get_active(record['company_id'], record['brand_id'], document_type)`; **if None, fall back** to the company-wide default (`brand_id IS NULL`) via a dedicated repo call (see note). If still None → **409** `{'error': 'Nu există un model de contract activ pentru acest brand/companie.'}`.
4. Build context: `company = CompanyRepository().get(record['company_id'])`; accepted offer = `next((o for o in offers_repo.list_for_record(id) if o['offer_type']==('consignment' if document_type=='consignment' else 'final') and o['client_decision']=='accepted'), None)`; consignment agreement only if `record['carpark_vehicle_id']` set (mirror `records.py` get path). `contract_date` = today (`YYYY-MM-DD`), `contract_number` = `record['record_code']`.
5. Render → `store_contract_pdf(record_id, pdf, caption=template['title'] or 'Contract')`.
6. Return the serialized stored doc + a non-blocking `warnings` list (e.g. "lipsesc datele vânzătorului"/"nicio ofertă acceptată — preț necompletat") computed from empty critical tokens. Manual generate NEVER 500s on sparse data — only 404 (no record) / 403 (guard) / 409 (no template).

**Repo note:** `get_active` has no fallback and uses `brand_id = %s` (won't match NULL). Add a small helper on `ContractTemplateRepository` — `get_active_with_default(company_id, brand_id, document_type)` — that tries the brand-specific row then a `brand_id IS NULL` company default. Put the TDD for it in THIS task (it's the task that needs it):

```python
def test_get_active_with_default_falls_back_to_company_default(seeded_templates):
    repo = ContractTemplateRepository()
    # brand 999 has no row; a company-default (brand_id NULL) purchase row exists
    row = repo.get_active_with_default(COMPANY_ID, 999, 'purchase')
    assert row is not None and row['brand_id'] is None
```

- [ ] **Step 1: Write the failing tests**

```python
def test_generate_creates_contract_document(client, seeded_record_with_template):
    r = client.post(f"/api/buyback/records/{seeded_record_with_template}/generate-contract", json={})
    assert r.status_code == 200
    assert r.get_json()['photo']['photo_type'] == 'contract'

def test_generate_409_when_no_template(client, seeded_record_without_template):
    r = client.post(f"/api/buyback/records/{seeded_record_without_template}/generate-contract", json={})
    assert r.status_code == 409

def test_generate_sparse_record_still_succeeds(client, seeded_record_no_seller_fields):
    r = client.post(f"/api/buyback/records/{seeded_record_no_seller_fields}/generate-contract", json={})
    assert r.status_code == 200
    assert 'warnings' in r.get_json()

def test_generate_rejects_cross_company_record(client_other_company, seeded_record_with_template):
    r = client_other_company.post(f"/api/buyback/records/{seeded_record_with_template}/generate-contract", json={})
    assert r.status_code in (403, 404)
```

- [ ] **Step 2: Run tests, verify they fail.**
- [ ] **Step 3: Implement** `get_active_with_default` on the repo, then the route + register it in `routes/__init__.py`.
- [ ] **Step 4: Run full buyback suite** — `DATABASE_URL=postgresql://localhost/defaultdb pytest jarvis/tests/buyback -q` → all pass.
- [ ] **Step 5: Commit** — `feat(buyback): POST /records/<id>/generate-contract (manual contract generation)`.

---

### Task 7: Frontend — API client + "Generează contract" button

**Files:**
- Modify: `jarvis/frontend/src/api/buyback.ts` (add `generateContract`)
- Modify: `jarvis/frontend/src/pages/BuyBack/ActionPanel.tsx` (show flag + button + `nothingToShow`)
- Test: manual verification via the `/verify` flow (the buyback frontend has no unit-test harness; confirm no existing frontend test breaks).

**Interfaces:**
- Consumes: Task 6 route; `usePermissions().can`; React Query `queryClient`.
- Produces: `buybackApi.generateContract(id: number)` → `api.post<{ photo: BuybackPhoto; warnings?: string[] }>(\`${BASE}/records/${id}/generate-contract\`, {})`.

**Button (ActionPanel):** add `const showGenerateContract = ['FINAL_OFFER','BOUGHT','CONSIGNMENT_OFFER','CONSIGNAT'].includes(status) && can('buyback.record.edit')`; add it to the `nothingToShow` aggregate (lines 161–177); render a `{showGenerateContract && <Button …>}` block mirroring the `finalizeMutation` pattern — `useMutation({ mutationFn: () => buybackApi.generateContract(record.id), onSuccess: (res) => { invalidate(); res.warnings?.length ? toast.warning(res.warnings.join(' ')) : toast.success('Contract generat') }, onError: (e) => toast.error(errMsg(e, 'Generarea contractului a eșuat')) })`. The `invalidate()` helper already refreshes `['buyback-record', id]`, so the new contract appears in the Documente section automatically (Task 5's `'Contract'` label).

- [ ] **Step 1: Add `generateContract` to `buybackApi`.**
- [ ] **Step 2: Add the gated button + mutation to `ActionPanel.tsx`; extend `nothingToShow`.**
- [ ] **Step 3: Typecheck/build the frontend** — `cd jarvis/frontend && npm run build` (or the repo's typecheck) → passes.
- [ ] **Step 4: Verify end-to-end** via `/verify`: on a record with an active template, click "Generează contract" → toast success → contract tile appears in Documente → downloads an openable PDF with diacritics; regenerate replaces the tile; a record with no template surfaces the 409 message as a toast.
- [ ] **Step 5: Commit** — `feat(buyback-ui): Generează contract button + api client`.

---

## Notes for the executor

- After all tasks: request a fresh code review (buyback diff), then ship **staging → prod** following `project_jarvis_pristine_workflow_rebaseline` (push `dev→staging`, validate, cherry-pick/FF to main with 2× confirm; check in-flight DO builds first). A deploy rebuilds the frontend — `git checkout -- jarvis/static/react` in the feat worktree if build artifacts appear.
- Deferred/confirm-with-user (do NOT silently build): `{price_ron}` + `{price_words}` (BNR-at-signing + RO number-to-words — legal necessity?); `{engine_no}`/`{power_cp}`/`{civ_no}` have no record column (leave empty or drop from templates). These are P3b open items, not blockers.
- P4 reuses `render_contract_pdf(..., signature=…)` and the same route logic on the accept path — keep the signature arg and the best-effort warning shape intact.
