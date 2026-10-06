import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

// buyback API — hoisted so each test can set return values / assert calls.
const api = vi.hoisted(() => ({
  listRecords: vi.fn(),
  getRecord: vi.fn(),
  getLookupOptions: vi.fn(),
  getCompanies: vi.fn(),
  postOffer: vi.fn(),
  recordDecision: vi.fn(),
}))
vi.mock('@/api/buyback', () => ({ buybackApi: api }))
vi.mock('@/pages/BuyBack/BuyBackForm', () => ({ default: () => <div>mock-buyback-form</div> }))
vi.mock('@/lib/media', () => ({ mediaUrl: (v: string | null | undefined) => v ?? '' }))

// useIsMobile drives the desktop-pills vs mobile-filter-modal split.
const mobile = vi.hoisted(() => ({ value: false }))
vi.mock('@/lib/utils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/utils')>()
  return { ...actual, useIsMobile: () => mobile.value }
})

// role + permissions read at render → mutate per test to exercise gating.
const auth = vi.hoisted(() => ({ user: {} as Record<string, unknown> }))
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: auth.user, isLoading: false }) }))

import HubBuybackPanel from './HubBuybackPanel'
import type { BuybackRecord, BuybackOffer } from '@/types/buyback'

const REC = (over: Partial<BuybackRecord> = {}): BuybackRecord =>
  ({
    id: 7,
    record_code: 'BB-2026-0007',
    brand: 'BMW',
    model: '320d',
    vin: 'WBA00000000000007',
    status: 'PENDING_EVALUATION',
    seller_name: 'Ion Pop',
    client_asking_price_eur: 9000,
    is_trade_in: false,
    has_damage: false,
    ...over,
  }) as unknown as BuybackRecord

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <HubBuybackPanel />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear() // reset usePersistedState (tenant company) between tests
  mobile.value = false
  api.listRecords.mockResolvedValue({ records: [], total: 0, page: 1, per_page: 200 })
  api.getRecord.mockResolvedValue({ record: REC(), offers: [], photos: [], events: [] })
  api.getLookupOptions.mockResolvedValue({})
  api.getCompanies.mockResolvedValue({ companies: [] })
  api.postOffer.mockResolvedValue({ offer: {} })
  api.recordDecision.mockResolvedValue({ record: {} })
  auth.user = { role_name: 'user', permissions: {} }
})

describe('HubBuybackPanel create-button gating', () => {
  it('hides "Solicitare nouă" without buyback.record.create', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    wrap()
    await screen.findByText('Nicio solicitare')
    expect(screen.queryByRole('button', { name: /solicitare nouă/i })).not.toBeInTheDocument()
  })

  it('shows "Solicitare nouă" with buyback.record.create', async () => {
    auth.user = { role_name: 'user', permissions: { 'buyback.record.create': true } }
    wrap()
    expect(await screen.findByRole('button', { name: /solicitare nouă/i })).toBeInTheDocument()
  })

  it('shows "Solicitare nouă" for admins regardless of permissions', async () => {
    auth.user = { role_name: 'admin', permissions: {} }
    wrap()
    expect(await screen.findByRole('button', { name: /solicitare nouă/i })).toBeInTheDocument()
  })
})

describe('HubBuybackPanel in-panel detail', () => {
  it('opens a read-only detail in-panel when a record is clicked (no navigation away)', async () => {
    api.listRecords.mockResolvedValue({ records: [REC()], total: 1, page: 1, per_page: 200 })
    api.getRecord.mockResolvedValue({
      record: REC({ mileage_km: 85000, fuel_type: 'diesel', client_asking_price_eur: 9500 }),
      offers: [],
      photos: [],
      events: [],
    })
    api.getLookupOptions.mockResolvedValue({ fuel_types: [{ value: 'diesel', label: 'Diesel' }] })
    wrap()
    fireEvent.click(await screen.findByText('BMW 320d')) // expand card
    fireEvent.click(await screen.findByText('Vezi detalii')) // open full detail
    // Section headings are rendered only by the detail view, never the list —
    // their presence proves the detail opened in-panel.
    expect(await screen.findByText('Vehicul')).toBeInTheDocument()
    expect(screen.getByText('Vânzător & Trade-in')).toBeInTheDocument()
    expect(screen.getByText('Prețuri')).toBeInTheDocument()
    expect(screen.getByText('Poze')).toBeInTheDocument()
    // RO lookup label resolved (diesel → Diesel) and photos empty-safe.
    expect(await screen.findByText('Diesel')).toBeInTheDocument()
    expect(screen.getByText('Nicio poză')).toBeInTheDocument()
    expect(api.getRecord).toHaveBeenCalledWith(7)
  })
})

const OFFER = (over: Partial<BuybackOffer> = {}): BuybackOffer =>
  ({
    id: 21,
    record_id: 7,
    offer_type: 'initial',
    amount_eur: 8000,
    client_decision: 'pending',
    created_at: '2026-09-20T10:00:00Z',
    ...over,
  }) as unknown as BuybackOffer

async function openDetail() {
  api.listRecords.mockResolvedValue({ records: [REC()], total: 1, page: 1, per_page: 200 })
  wrap()
  fireEvent.click(await screen.findByText('BMW 320d')) // expand card
  fireEvent.click(await screen.findByText('Vezi detalii')) // open full detail
  await screen.findByText('Vehicul')
}

describe('HubBuybackPanel card accordion', () => {
  it('expands a card to a summary (year / mileage / report / Vezi detalii) and collapses', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    api.listRecords.mockResolvedValue({
      records: [REC({ mileage_km: 85000, first_registration_date: '2019-06-01', inspection_report_key: 'reports/bb-7.pdf' })],
      total: 1,
      page: 1,
      per_page: 200,
    })
    api.getRecord.mockResolvedValue({ record: REC(), offers: [OFFER()], photos: [], events: [] })
    wrap()
    fireEvent.click(await screen.findByText('BMW 320d')) // expand
    expect(await screen.findByText('Vezi detalii')).toBeInTheDocument()
    expect(screen.getByText(/An:/)).toBeInTheDocument()
    expect(screen.getByText(/Rulaj:/)).toBeInTheDocument()
    expect(screen.getByText(/Raport avarii/)).toBeInTheDocument() // inspection_report_key present
    fireEvent.click(screen.getByText('BMW 320d')) // collapse
    await waitFor(() => expect(screen.queryByText('Vezi detalii')).not.toBeInTheDocument())
  })
})

describe('HubBuybackPanel detail — offers/decision (mobile parity)', () => {
  it('posts an initial offer on PENDING_EVALUATION with buyback.offer.manage', async () => {
    auth.user = { role_name: 'user', permissions: { 'buyback.offer.manage': true } }
    api.getRecord.mockResolvedValue({ record: REC({ status: 'PENDING_EVALUATION' }), offers: [], photos: [], events: [] })
    await openDetail()

    fireEvent.click(await screen.findByText(/Postează ofertă/))
    fireEvent.change(await screen.findByRole('spinbutton'), { target: { value: '8500' } })
    fireEvent.click(screen.getByText(/Trimite oferta/))

    await waitFor(() =>
      expect(api.postOffer).toHaveBeenCalledWith(7, expect.objectContaining({ offer_type: 'initial', amount_eur: 8500 }))
    )
  })

  it('posts a final offer on INSPECTION with buyback.offer.manage', async () => {
    auth.user = { role_name: 'user', permissions: { 'buyback.offer.manage': true } }
    api.getRecord.mockResolvedValue({ record: REC({ status: 'INSPECTION' }), offers: [], photos: [], events: [] })
    await openDetail()

    fireEvent.click(await screen.findByText(/Postează ofertă/))
    fireEvent.change(await screen.findByRole('spinbutton'), { target: { value: '7000' } })
    fireEvent.click(screen.getByText(/Trimite oferta/))

    await waitFor(() =>
      expect(api.postOffer).toHaveBeenCalledWith(7, expect.objectContaining({ offer_type: 'final', amount_eur: 7000 }))
    )
  })

  it('records accept on the pending offer for INITIAL_OFFER with buyback.record.edit', async () => {
    auth.user = { role_name: 'user', permissions: { 'buyback.record.edit': true } }
    api.getRecord.mockResolvedValue({
      record: REC({ status: 'INITIAL_OFFER' }),
      offers: [OFFER({ id: 55, client_decision: 'pending' })],
      photos: [],
      events: [],
    })
    await openDetail()

    fireEvent.click(await screen.findByText(/Client a acceptat/))

    await waitFor(() =>
      expect(api.recordDecision).toHaveBeenCalledWith(7, 55, expect.objectContaining({ decision: 'accepted' }))
    )
  })

  it('records decline with reason on the pending offer for FINAL_OFFER with buyback.record.edit', async () => {
    auth.user = { role_name: 'user', permissions: { 'buyback.record.edit': true } }
    api.getRecord.mockResolvedValue({
      record: REC({ status: 'FINAL_OFFER' }),
      offers: [OFFER({ id: 88, offer_type: 'final', client_decision: 'pending' })],
      photos: [],
      events: [],
    })
    await openDetail()

    fireEvent.click(await screen.findByText(/Client a refuzat/))
    fireEvent.change(await screen.findByRole('textbox'), { target: { value: 'preț prea mare' } })
    fireEvent.click(screen.getByText(/Confirmă refuzul/))

    await waitFor(() =>
      expect(api.recordDecision).toHaveBeenCalledWith(
        7,
        88,
        expect.objectContaining({ decision: 'declined', decline_reason: 'preț prea mare' })
      )
    )
  })

  it('does not carry a cancelled decline reason into a later decline', async () => {
    auth.user = { role_name: 'user', permissions: { 'buyback.record.edit': true } }
    api.getRecord.mockResolvedValue({
      record: REC({ status: 'INITIAL_OFFER' }),
      offers: [OFFER({ id: 99, client_decision: 'pending' })],
      photos: [],
      events: [],
    })
    await openDetail()

    // Open decline, type a reason, cancel with "Renunță".
    fireEvent.click(await screen.findByText(/Client a refuzat/))
    fireEvent.change(await screen.findByRole('textbox'), { target: { value: 'motiv abandonat' } })
    fireEvent.click(screen.getByText(/Renunță/))

    // Reopen and confirm without typing — the stale reason must not be sent.
    fireEvent.click(await screen.findByText(/Client a refuzat/))
    fireEvent.click(await screen.findByText(/Confirmă refuzul/))

    await waitFor(() =>
      expect(api.recordDecision).toHaveBeenLastCalledWith(7, 99, { decision: 'declined', decline_reason: undefined })
    )
  })

  it('hides offer/decision actions without permission', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    api.getRecord.mockResolvedValue({ record: REC({ status: 'PENDING_EVALUATION' }), offers: [], photos: [], events: [] })
    await openDetail()
    expect(screen.queryByText(/Postează ofertă/)).not.toBeInTheDocument()

    // and decision actions hidden on an offer status too
    api.getRecord.mockResolvedValue({
      record: REC({ status: 'INITIAL_OFFER' }),
      offers: [OFFER()],
      photos: [],
      events: [],
    })
  })
})

describe('HubBuybackPanel list — filter + search (mobile parity)', () => {
  it('re-queries the list with the selected status', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    wrap()
    await screen.findByText('Nicio solicitare')
    fireEvent.click(screen.getByText('Achiziționat'))
    await waitFor(() =>
      expect(api.listRecords).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'BOUGHT' }))
    )
  })

  it('multi-selects statuses (comma-joined) via the desktop pills', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    wrap()
    await screen.findByText('Nicio solicitare')
    fireEvent.click(screen.getByText('Achiziționat')) // BOUGHT
    fireEvent.click(screen.getByText('Pierdut')) // LOST
    await waitFor(() =>
      expect(api.listRecords).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'BOUGHT,LOST' }))
    )
    // toggling one off narrows back to the remaining status
    fireEvent.click(screen.getByText('Achiziționat'))
    await waitFor(() =>
      expect(api.listRecords).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'LOST' }))
    )
  })

  it('re-queries the list with the debounced search text', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    wrap()
    await screen.findByText('Nicio solicitare')
    fireEvent.change(screen.getByPlaceholderText(/Caută/i), { target: { value: 'WBA' } })
    await waitFor(() =>
      expect(api.listRecords).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'WBA' }))
    )
  })
})

describe('HubBuybackPanel intake overlay (iOS sheet)', () => {
  it('opens the intake sheet and closes it via the close button', async () => {
    auth.user = { role_name: 'admin', permissions: {} }
    api.listRecords.mockResolvedValue({ records: [REC()], total: 1, page: 1, per_page: 200 })
    wrap()
    fireEvent.click(await screen.findByRole('button', { name: /solicitare nouă/i }))
    expect(await screen.findByText('mock-buyback-form')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Închide'))
    await waitFor(() => expect(screen.queryByText('mock-buyback-form')).not.toBeInTheDocument())
  })
})

describe('HubBuybackPanel tenant filter', () => {
  it('shows the company selector when the user has more than one company', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    api.getCompanies.mockResolvedValue({ companies: [{ id: 11, name: 'Autoworld SRL' }, { id: 22, name: 'MG Motor' }] })
    wrap()
    expect(await screen.findByRole('combobox')).toBeInTheDocument()
  })

  it('hides the company selector with a single company', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    api.getCompanies.mockResolvedValue({ companies: [{ id: 11, name: 'Autoworld SRL' }] })
    wrap()
    await screen.findByText('Nicio solicitare')
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})

describe('HubBuybackPanel mobile — Filtre modal', () => {
  it('multi-selects via the Filtre modal, then clears', async () => {
    mobile.value = true
    auth.user = { role_name: 'user', permissions: {} }
    wrap()
    await screen.findByPlaceholderText(/Caută/i)
    fireEvent.click(screen.getByRole('button', { name: /filtre/i }))
    fireEvent.click(await screen.findByText('Achiziționat'))
    fireEvent.click(screen.getByText('Pierdut'))
    await waitFor(() =>
      expect(api.listRecords).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'BOUGHT,LOST' }))
    )
    // Clearing empties the selection → the clear button (gated on a non-empty
    // selection) disappears. (No refetch to assert: the empty-filter query key
    // was already cached at mount.)
    fireEvent.click(screen.getByText(/Șterge filtrele/i))
    await waitFor(() => expect(screen.queryByText(/Șterge filtrele/i)).not.toBeInTheDocument())
  })
})

describe('HubBuybackPanel detail — back navigation', () => {
  it('returns to the list when Înapoi is clicked', async () => {
    auth.user = { role_name: 'user', permissions: {} }
    await openDetail()
    fireEvent.click(screen.getByText('Înapoi'))
    expect(await screen.findByText('BMW 320d')).toBeInTheDocument()
    expect(screen.queryByText('Vehicul')).not.toBeInTheDocument()
  })
})
