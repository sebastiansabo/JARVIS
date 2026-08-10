// @ts-check
import { test, expect } from '@playwright/test'

// ─────────────────────────────────────────────────────────────────────────
// CarPark Dispo Workspace — route-mocked regression test
//
// The Dispo workspace lives behind @login_required (OTP-based auth, no easy
// programmatic login), so this spec never talks to the real backend. Every
// /api/** call is intercepted with page.route() and answered with a
// deterministic fixture. This tests the FRONTEND wiring only: that the page
// requests the right endpoints, renders what it gets back, and fires the
// right mutation on the Reserve action.
//
// The dev server for THIS worktree is already running on :5174 — tests use
// an absolute http://127.0.0.1:5174/... URL so they target it directly
// instead of playwright.config.js's staging baseURL.
//
// NOTE: `localhost` resolves to `::1` (IPv6) on this machine, which happens
// to be a DIFFERENT project's dev server (jarvis-mobile-2) also bound to
// port 5174 — so `localhost:5174` silently hits the wrong app. Use the
// literal IPv4 loopback address to reach THIS worktree's Vite server
// (started with `--host 127.0.0.1`).
// ─────────────────────────────────────────────────────────────────────────

const APP_URL = 'http://127.0.0.1:5174/app/carpark/dispo'

/** Minimal-but-complete User object — matches types/index.ts's User interface
 *  closely enough that useAuth()/Guard/Sidebar/Layout all behave normally. */
const MOCK_USER = {
  id: 1,
  email: 'dispo.tester@autoworld.ro',
  name: 'Dispo Tester',
  role_id: 1,
  role_name: 'Admin',
  is_active: true,
  company: 'AUTOWORLD',
  company_id: 1,
  can_add_invoices: true,
  can_edit_invoices: true,
  can_delete_invoices: true,
  can_view_invoices: true,
  can_access_dashboard: true,
  can_access_accounting: true,
  can_access_settings: true,
  can_access_connectors: true,
  can_access_templates: true,
  can_access_hr: true,
  can_access_efactura: true,
  can_access_statements: true,
  is_hr_manager: false,
  can_access_crm: true,
  can_access_field_sales: true,
  can_access_marketing: true,
  can_access_approvals: true,
  can_access_dms: true,
  can_access_forms: true,
  can_access_ai_agent: true,
  can_edit_crm: true,
  can_delete_crm: true,
  can_export_crm: true,
  can_view_original_punches: true,
  can_view_adjusted_punches: true,
  can_adjust_punches: true,
  // ── The flags this spec actually cares about ──
  can_access_carpark: true,
  can_edit_carpark: true,
  can_delete_carpark: true,
  can_access_carpark_mobile: true,
  can_view_carpark_finance: true,
  can_access_service: true,
  can_access_ticketing: true,
  can_access_controlling: true,
  can_access_vouchers: true,
  can_access_facturare: true,
  permissions: {},
  permission_scopes: {},
}

// A READY_FOR_SALE row (in_stoc stage) — Reserve is offered for this status
// (DispoRowActions's RESERVE_HIDDEN_STATUSES doesn't include it).
const ROW_READY_FOR_SALE = {
  id: 101,
  vin: 'WVWZZZAUZNW123456',
  nr_stoc: 'STK-101',
  brand: 'Volkswagen',
  model: 'Golf',
  variant: 'GTI',
  status: 'READY_FOR_SALE',
  source: 'Achiziție',
  location_text: 'Cluj Showroom',
  sale_type: null,
  salesperson_user_id: null,
  acquisition_manager_id: 1,
  acquisition_date: '2026-06-01',
  listing_date: null,
  sale_date: null,
  delivery_date: null,
  supplier_payment_date: '2026-06-02',
  stock_removed_date: null,
  days_in_stock: 40,
  current_price: 25000,
  sale_price: null,
  gw_file_number: null,
  is_impus: false,
  missing_civ: false,
  stock_removed: false,
  buyer_name: null,
  reservation_id: null,
  reservation_end: null,
  reservation_client_name: null,
  reservation_deposit_amount: null,
  reservation_deposit_paid: null,
  doc_types: ['pv_intrare', 'civ'],
  acquisition_price: 20000,
  total_costs: 500,
  gross_margin: null,
  margin_pct: null,
  bonus_leasing: 0,
}

// A LISTED row — just extra pipeline data so the table isn't a single row.
const ROW_LISTED = {
  id: 102,
  vin: 'WBA5A7C50FG112233',
  nr_stoc: 'STK-102',
  brand: 'BMW',
  model: 'Seria 3',
  variant: '320d',
  status: 'LISTED',
  source: 'Achiziție',
  location_text: 'Cluj Showroom',
  sale_type: null,
  salesperson_user_id: null,
  acquisition_manager_id: null,
  acquisition_date: '2026-07-01',
  listing_date: '2026-07-15',
  sale_date: null,
  delivery_date: null,
  supplier_payment_date: null,
  stock_removed_date: null,
  days_in_stock: 10,
  current_price: 22000,
  sale_price: null,
  gw_file_number: null,
  is_impus: false,
  missing_civ: false,
  stock_removed: false,
  buyer_name: null,
  reservation_id: null,
  reservation_end: null,
  reservation_client_name: null,
  reservation_deposit_amount: null,
  reservation_deposit_paid: null,
  doc_types: ['pv_intrare'],
  acquisition_price: 18000,
  total_costs: 300,
  gross_margin: null,
  margin_pct: null,
  bonus_leasing: 0,
}

// A SOLD row — Reserve must NOT be offered for this one (RESERVE_HIDDEN_STATUSES).
const ROW_SOLD = {
  id: 103,
  vin: 'WAUZZZ8K5JA654321',
  nr_stoc: 'STK-103',
  brand: 'Audi',
  model: 'A4',
  variant: null,
  status: 'SOLD',
  source: 'Trade-in',
  location_text: 'Oradea Showroom',
  sale_type: 'CASH',
  salesperson_user_id: 1,
  acquisition_manager_id: 1,
  acquisition_date: '2026-05-01',
  listing_date: '2026-05-10',
  sale_date: '2026-07-01',
  delivery_date: null,
  supplier_payment_date: '2026-05-02',
  stock_removed_date: null,
  days_in_stock: 61,
  current_price: 30000,
  sale_price: 29500,
  gw_file_number: 'GW-1002',
  is_impus: false,
  missing_civ: false,
  stock_removed: false,
  buyer_name: 'Ion Popescu',
  reservation_id: null,
  reservation_end: null,
  reservation_client_name: null,
  reservation_deposit_amount: null,
  reservation_deposit_paid: null,
  doc_types: ['pv_intrare', 'civ', 'contract_vanzare'],
  acquisition_price: 24000,
  total_costs: 800,
  gross_margin: 4700,
  margin_pct: 15.9,
  bonus_leasing: 0,
}

const DISPO_SUMMARY_FIXTURE = {
  rows: [ROW_READY_FOR_SALE, ROW_LISTED, ROW_SOLD],
  stage_counts: {
    all: 3,
    in_pregatire: 0,
    in_stoc: 1,
    promovat: 1,
    rezervat: 0,
    vandut: 1,
    livrat: 0,
    iesit: 0,
  },
  totals: {
    acquisition_price: 62000,
    total_costs: 1600,
    sale_price: 29500,
    gross_margin: 4700,
  },
  total: 3,
  page: 1,
  per_page: 25,
}

const DISPO_KPIS_FIXTURE = {
  cars_in_stock: 12,
  reserved: 3,
  sold_this_month: 5,
  delivered_this_month: 2,
  avg_days_in_stock: 34,
  aged_over_60: 1,
  gross_margin_mtd: 15250,
}

function jsonRoute(data, status = 200) {
  return (route) =>
    route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(data),
    })
}

// Route patterns below are anchored to the exact dev-server ORIGIN (rather
// than a leading `**` glob) for a load-bearing reason: this repo's frontend
// source lives under `src/api/*.ts` (auth.ts, carpark.ts, ...), and Vite's
// dev server serves those as ES module scripts from URLs like
// `http://127.0.0.1:5174/src/api/auth.ts`. A glob of `**/api/**` matches
// that URL too (it contains the substring "/api/"), so it ends up
// intercepting the app's own JS module requests and serving them JSON —
// which breaks the module graph before React even mounts.
const ORIGIN = 'http://127.0.0.1:5174'

/** Registers every mock this spec needs. Must be called per-test (fresh
 *  page/context each time) — the catch-all is registered FIRST so the more
 *  specific routes registered after it win (Playwright checks routes
 *  newest-registered-first). */
async function mockDispoBackend(page) {
  // ── Safety net: nothing should ever reach the real backend ──
  //
  // A plain path-prefix catch-all (`${ORIGIN}/api/**`) isn't enough on its
  // own: this app also calls several NON-`/api/`-prefixed backend routes on
  // every page load — `/mobile-checkin/api/status` (Sidebar's check-in
  // status) and `/notifications/api/unread-count` (NotificationBell) both
  // fire from Layout, which wraps every route. Left unmocked, those hit the
  // real (unauthenticated) backend, which answers 401/302 — and client.ts's
  // global 401 handler does `window.location.href = '/login'`, a hard
  // navigation that blows away the whole SPA and the test with it.
  //
  // So instead of guessing every backend path prefix, this matches on
  // *resourceType*: only `fetch`/`xhr` requests (i.e. actual `api.get/post`
  // calls) are stubbed with `{}`; everything else (the document navigation,
  // JS modules, CSS, images) is passed through untouched via
  // `route.continue()` so Vite keeps serving the app normally.
  await page.route(`${ORIGIN}/**`, (route) => {
    const type = route.request().resourceType()
    if (type !== 'fetch' && type !== 'xhr') return route.continue()
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  // ── Auth — makes useAuth()/Guard pass with full carpark permissions ──
  await page.route(`${ORIGIN}/api/auth/current-user`, jsonRoute({ authenticated: true, user: MOCK_USER }))

  // ── Dispo data ──
  await page.route(`${ORIGIN}/api/carpark/dispo/summary**`, jsonRoute(DISPO_SUMMARY_FIXTURE))
  await page.route(`${ORIGIN}/api/carpark/dispo/kpis`, jsonRoute(DISPO_KPIS_FIXTURE))

  // ── Reservations (Detail page's VanzareTab uses this; harmless here) ──
  await page.route(`${ORIGIN}/api/carpark/vehicles/*/reservations`, jsonRoute({ reservations: [] }))

  // ── Filter-field sources the toolbar reads ──
  await page.route(
    `${ORIGIN}/api/carpark/vehicles/filter-options`,
    jsonRoute({ brands: ['Volkswagen', 'Audi', 'BMW'], fuel_types: ['Benzină', 'Diesel'], body_types: ['Hatchback', 'Sedan'] }),
  )
  await page.route(
    `${ORIGIN}/api/carpark/locations`,
    jsonRoute({
      locations: [
        { id: 1, name: 'Cluj Showroom', code: 'CLJ', address: null, city: 'Cluj-Napoca', type: 'showroom', capacity: 20, company_id: 1, is_active: true, created_at: '2026-01-01' },
      ],
    }),
  )

  // usersApi.getUsers() returns a bare array (not `{ users: [...] }`) — the
  // page does `for (const u of usersData ?? [])` and `.map()` over it
  // directly, so the generic `{}` catch-all would throw here. Must be a
  // real array.
  await page.route(`${ORIGIN}/api/users`, jsonRoute([{ id: 1, name: 'Dispo Tester' }]))
}

test.describe('CarPark Dispo workspace (route-mocked)', () => {
  test.beforeEach(async ({ page }) => {
    await mockDispoBackend(page)
  })

  test('renders KPI strip, pipeline tabs, and fixture rows', async ({ page }) => {
    await page.goto(APP_URL)

    // Zone 1 — KPI strip (StatCard titles from kpisData)
    await expect(page.getByText('Mașini în stoc')).toBeVisible()
    await expect(page.getByText('Peste 60 zile')).toBeVisible()
    // Finance-gated KPI — visible because MOCK_USER.can_view_carpark_finance is true
    await expect(page.getByText('Marjă brută MTD')).toBeVisible()

    // Zone 2 — pipeline stage tabs (DISPO_STAGES labels)
    await expect(page.getByRole('button', { name: /^Toate/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /^În stoc/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Rezervat/ })).toBeVisible()

    // Zone 3 — table rows from the mocked /dispo/summary fixture
    await expect(page.getByRole('row', { name: /Volkswagen/ })).toBeVisible()
    await expect(page.getByRole('row', { name: /Audi/ })).toBeVisible()
    // VIN cell renders `<span title={fullVin}>{last 6 chars}</span>`
    await expect(page.getByTitle(ROW_READY_FOR_SALE.vin)).toBeVisible()
    await expect(page.getByTitle(ROW_SOLD.vin)).toBeVisible()

    // Pagination footer reflects the fixture's `total`
    await expect(page.getByText('3 vehicule')).toBeVisible()
  })

  test('Reserve action: fills dialog and fires the mocked POST /reserve', async ({ page }) => {
    let reserveRequestBody = null

    // Test-specific route for the mutation — registered after beforeEach's
    // mocks, so (being most-recently-registered) it wins for this URL.
    await page.route(`${ORIGIN}/api/carpark/vehicles/*/reserve`, async (route) => {
      reserveRequestBody = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          vehicle: { ...ROW_READY_FOR_SALE, status: 'RESERVED' },
          reservation: {
            id: 555,
            vehicle_id: ROW_READY_FOR_SALE.id,
            client_id: null,
            client_name: 'Maria Ionescu',
            client_company: null,
            client_phone: null,
            client_email: null,
            user_id: MOCK_USER.id,
            reservation_start: '2026-08-10',
            reservation_end: '2026-09-01',
            deposit_amount: 0,
            deposit_paid: false,
            status: 'active',
            notes: null,
            created_by: MOCK_USER.id,
            created_at: '2026-08-10T10:00:00Z',
            updated_at: '2026-08-10T10:00:00Z',
          },
        }),
      })
    })

    await page.goto(APP_URL)

    // Locate the READY_FOR_SALE row (Volkswagen Golf) and open its ⋯ menu.
    const readyRow = page.getByRole('row', { name: /Volkswagen/ })
    await expect(readyRow).toBeVisible()
    await readyRow.getByRole('button', { name: 'Acțiuni' }).click()

    // DropdownMenuContent portals to document.body — query at page level.
    await page.getByRole('menuitem', { name: 'Rezervă' }).click()

    // ReserveDialog is open — fill client name + reservation end date.
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText(`Rezervă ${ROW_READY_FOR_SALE.brand} ${ROW_READY_FOR_SALE.model}`)).toBeVisible()

    await dialog.getByPlaceholder('Nume client').fill('Maria Ionescu')
    await dialog.locator('input[type="date"]').fill('2026-09-01')

    const submitBtn = dialog.getByRole('button', { name: 'Rezervă', exact: true })
    await expect(submitBtn).toBeEnabled()

    const [reserveRequest] = await Promise.all([
      page.waitForRequest((req) => req.url().includes('/reserve') && req.method() === 'POST'),
      submitBtn.click(),
    ])

    // The mocked POST was actually hit, with the form's data.
    expect(reserveRequest.url()).toContain(`/api/carpark/vehicles/${ROW_READY_FOR_SALE.id}/reserve`)
    expect(reserveRequestBody).toMatchObject({
      client_name: 'Maria Ionescu',
      reservation_end: '2026-09-01',
    })

    // Success toast + dialog closes.
    await expect(page.getByText('Vehicul rezervat')).toBeVisible()
    await expect(page.getByRole('dialog')).toBeHidden()
  })
})
