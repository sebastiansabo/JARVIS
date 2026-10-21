"""Shared HTML -> PDF rendering helper for the CarPark "Documente vanzare"
sale-document renderers (contract / warranty / proforma, Tasks 3-5).

Promoted from `foi_parcurs/services/route_sheet_service.py::_html_to_pdf_bytes`
(same shape: lazy `playwright.sync_api` import inside the function, headless
Chromium, `page.set_content(..., wait_until='load')`, A4 with 16mm margins)
so every sale-document renderer shares one Playwright entry point instead of
each reimplementing it.

The `playwright` import stays INSIDE the function (not at module level) so
importing this module — and therefore importing `contract.py`/future
`warranty.py`/`proforma.py` — never requires Chromium to be installed; only
actually calling `html_to_pdf_bytes()` does.
"""


def html_to_pdf_bytes(html: str) -> bytes:
    """Render an HTML string to PDF bytes via headless Chromium.

    `html` must already be a complete, self-contained HTML document (styles
    inlined/embedded) — this function does no templating, escaping, or
    token substitution; that's the caller's job (see `contract.py`'s
    `_fill_contract_html`).
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until='load')
            return page.pdf(
                format='A4', print_background=True,
                margin={'top': '16mm', 'bottom': '16mm', 'left': '16mm', 'right': '16mm'},
            )
        finally:
            browser.close()
