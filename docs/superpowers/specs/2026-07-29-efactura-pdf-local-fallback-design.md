# e-Factura invoice — in-app preview (no ANAF, no PDF)

**Date:** 2026-07-29
**Status:** Implemented on dev
**Branch:** dev

## Problem

A Viewer opening an invoice from Command Center → My Invoices hit:

```
{"error":"HTTPSConnectionPool(host='api.anaf.ro', … /transformare/FACT1/DA …
too many 503 error responses"}
```

Investigation confirmed this is **not** a permission gate and **not** a connector bug — the
OAuth token, invoice fetch, and ZIP/XML download all work. The invoice PDF was generated *live
on every click* by POSTing the stored XML to ANAF's `transformare/FACT1/DA` endpoint (ANAF's
flakiest service), and that endpoint was returning HTTP 503. The raw error was leaked to the
browser with a misleading 404.

## Decision history (why not a local PDF render)

Initial plan was a cache + local PDF fallback. A spike proved an **ANAF-exact local PDF is
infeasible**: our stack is libxslt (XSLT 1.0 only), ANAF publishes no visualization stylesheet
(only XSD + Schematron for validation), and the standard UBL stylesheet (OpenPEPPOL/EN 16931) is
XSLT 2.0 (needs a native engine, and still isn't ANAF-exact).

The user then re-scoped: **they don't need a PDF at all — just to see the invoice content in
JARVIS.** That dissolves the ANAF dependency entirely.

## Approach (shipped)

A read-only, in-app **preview** built from data we already store.

**Backend** — `GET /profile/api/invoices/<id>/preview` in `core/profile/routes.py`:
- Ownership check (`is_invoice_visible_to_user`), same as the PDF route.
- Resolves the invoice XML via `invoice_xml_service.get_invoice_xml_by_jarvis_id()`: prefers the
  stored `efactura_invoices.xml_content`; if missing, fetches the ZIP once from ANAF's
  **descarcare** endpoint (`download_message`), extracts the invoice XML, caches it back, and
  returns it. Parsed with the existing `parse_invoice_xml()`. 404 only if there is no e-Factura
  record / no download id / ANAF fetch fails.
- The happy path makes **no ANAF call, no PDF, no Playwright** → works even during a full ANAF
  transformare/PDF outage. Only the rare missing-XML case touches ANAF (via descarcare, the same
  endpoint the "Download ZIP" button uses — confirmed working).
- Serialisation lives in a pure, unit-tested helper `core/connectors/efactura/invoice_preview.py`
  (`build_invoice_preview(xml) -> dict`): parties, invoice no/series/dates, currency, line items,
  VAT breakdown, totals, payment (IBAN/terms), note. Decimals → plain strings, dates → ISO.
- SQL stays in `EFacturaInvoiceRepository` (`get_xml_source_info` joins `efactura_invoice_refs`
  and coalesces `download_id`→`message_id` for the descarcare id; `save_xml_content` caches back).

**Frontend** — `pages/Profile/`:
- `InvoicePreviewModal.tsx` — shadcn `Dialog`; fetches the endpoint via React Query; renders
  Furnizor/Client, an articole table, TVA breakdown, totals, and payment/note; loading +
  error states.
- `Profile/index.tsx` — a **Preview (eye)** button on each e-Factura row
  (`drive_link.startsWith('/efactura/')`), in both the mobile card and desktop table. The
  existing **PDF download** button is kept alongside (official copy when ANAF is up).
- `api/profile.ts` — `getInvoicePreview(id)` + `InvoicePreview` types.

## Testing

- `tests/efactura/test_invoice_preview.py` (4): full UBL → correct fields; output is
  JSON-serialisable (no Decimal/date leaks); minimal UBL doesn't crash; invalid XML raises.
- `tests/efactura/test_invoice_xml_service.py` (7): ZIP extraction skips signatures; stored XML
  returned without ANAF; missing XML fetches + caches; no download id / ANAF failure / no record
  → None.
- Verified against **staging** (real ANAF XML): 8/8 invoices parse correctly; all 636 staging
  invoices already have `xml_content` (missing = 0); the descarcare id resolves via
  `COALESCE(download_id, message_id)`.
- Frontend `tsc -b` clean.

## Out of scope / rejected

- Local PDF render (ANAF-exact infeasible; own-template render dropped in favour of preview).
- PDF caching / graceful-degrade renderer (no longer needed — preview happy path never calls ANAF).
- The existing PDF-download route is unchanged (still hits ANAF; still useful when ANAF is up).
