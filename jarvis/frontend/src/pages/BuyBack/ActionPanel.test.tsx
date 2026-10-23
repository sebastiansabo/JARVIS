import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/buyback', () => ({
  buybackApi: {
    postOffer: vi.fn(() => Promise.resolve({ offer: {} })),
    recordDecision: vi.fn(() => Promise.resolve({ record: {} })),
    saveInspection: vi.fn(() => Promise.resolve({})),
    uploadInspectionReport: vi.fn(() => Promise.resolve({})),
    finalize: vi.fn(() => Promise.resolve({ record: {} })),
    retryHandoff: vi.fn(() => Promise.resolve({})),
    cancelRecord: vi.fn(() => Promise.resolve({})),
    reopenRecord: vi.fn(() => Promise.resolve({})),
    hold: vi.fn(() => Promise.resolve({ record: {} })),
    resume: vi.fn(() => Promise.resolve({ record: {} })),
    transferToCustody: vi.fn(() => Promise.resolve({ vehicle: { id: 77 } })),
    proposeConsignment: vi.fn(() => Promise.resolve({ offer: {} })),
    getLookupOptions: vi.fn(() =>
      Promise.resolve({ vat_statuses: [], hold_reasons: [{ value: 'Poze lipsă', label: 'Poze lipsă' }] })
    ),
  },
}))

// role + permissions read at render → mutate per test to exercise the
// permission-gating matrix (actions must be HIDDEN, not just disabled).
const auth = vi.hoisted(() => ({ role: 'user', permissions: {} as Record<string, boolean> }))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { role_name: auth.role, permissions: auth.permissions }, isLoading: false }),
}))

import ActionPanel from './ActionPanel'
import { buybackApi } from '@/api/buyback'
import type { BuybackRecord, BuybackOffer } from '@/types/buyback'

function renderPanel(
  status: string,
  perms: Record<string, boolean>,
  opts: { offers?: BuybackOffer[]; record?: Partial<BuybackRecord>; role?: string } = {}
) {
  auth.role = opts.role ?? 'user'
  auth.permissions = perms
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const record = { id: 5, status, carpark_vehicle_id: null, ...opts.record } as unknown as BuybackRecord
  return render(
    <QueryClientProvider client={qc}>
      <ActionPanel record={record} offers={opts.offers ?? []} />
    </QueryClientProvider>
  )
}

describe('ActionPanel permission gating', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('PENDING_EVALUATION + offer.manage shows "Postează ofertă"', () => {
    renderPanel('PENDING_EVALUATION', { 'buyback.offer.manage': true })
    expect(screen.getByText(/Postează ofertă/)).toBeInTheDocument()
  })

  it('PENDING_EVALUATION without offer.manage HIDES the offer button', () => {
    renderPanel('PENDING_EVALUATION', {})
    expect(screen.queryByText(/Postează ofertă/)).not.toBeInTheDocument()
  })

  it('INITIAL_OFFER + offer.manage shows "Postează ofertă" (re-send a revised offer)', () => {
    // The acquisition handler can issue as many offers as needed — the button
    // stays available while the record is still awaiting the seller's decision.
    renderPanel('INITIAL_OFFER', { 'buyback.offer.manage': true })
    expect(screen.getByText(/Postează ofertă/)).toBeInTheDocument()
  })

  it('offer dialog has an editable Preț Piață input pre-filled from the record', async () => {
    renderPanel('PENDING_EVALUATION', { 'buyback.offer.manage': true },
      { record: { id: 5, market_price_eur: 21500 } })
    fireEvent.click(screen.getByText(/Postează ofertă/))
    // acquisition sets/confirms the researched retail value here; pre-filled
    expect(await screen.findByDisplayValue('21500')).toBeInTheDocument()
  })

  it('posts the offer including the edited Preț Piață (retail)', async () => {
    renderPanel('PENDING_EVALUATION', { 'buyback.offer.manage': true },
      { record: { id: 5, market_price_eur: 21500 } })
    fireEvent.click(screen.getByText(/Postează ofertă/))
    const spinners = await screen.findAllByRole('spinbutton')  // [0]=Sumă, [1]=Preț Piață
    fireEvent.change(spinners[0], { target: { value: '9000' } })
    fireEvent.click(screen.getByText('Trimite oferta'))
    await waitFor(() => expect(buybackApi.postOffer).toHaveBeenCalled())
    expect(buybackApi.postOffer).toHaveBeenCalledWith(5, expect.objectContaining({
      amount_eur: 9000, market_price_eur: 21500,
    }))
  })

  it('INITIAL_OFFER + record.edit shows Accept/Decline', () => {
    renderPanel('INITIAL_OFFER', { 'buyback.record.edit': true })
    expect(screen.getByText(/Client a acceptat/)).toBeInTheDocument()
    expect(screen.getByText(/Client a refuzat/)).toBeInTheDocument()
  })

  it('INITIAL_OFFER without record.edit HIDES Accept/Decline', () => {
    renderPanel('INITIAL_OFFER', {})
    expect(screen.queryByText(/Client a acceptat/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Client a refuzat/)).not.toBeInTheDocument()
  })

  it('INSPECTION + inspection.manage shows the inspection form', () => {
    renderPanel('INSPECTION', { 'buyback.inspection.manage': true })
    expect(screen.getByText(/Salvează inspecția/)).toBeInTheDocument()
  })

  it('INSPECTION without inspection.manage HIDES the inspection form', () => {
    renderPanel('INSPECTION', {})
    expect(screen.queryByText(/Salvează inspecția/)).not.toBeInTheDocument()
  })

  it('INSPECTION + offer.manage shows "Postează ofertă finală"', () => {
    renderPanel('INSPECTION', { 'buyback.offer.manage': true })
    expect(screen.getByText(/Postează ofertă finală/)).toBeInTheDocument()
  })

  it('INSPECTION without offer.manage HIDES "Postează ofertă finală"', () => {
    renderPanel('INSPECTION', {})
    expect(screen.queryByText(/Postează ofertă finală/)).not.toBeInTheDocument()
  })

  const pendingFinalOffer = [{
    id: 9, record_id: 5, offer_type: 'final', amount_eur: 10000,
    client_decision: 'pending', created_at: '2026-10-20',
  } as unknown as BuybackOffer]

  it('FINAL_OFFER + offer.manage shows "Corectează oferta finală"', () => {
    renderPanel('FINAL_OFFER', { 'buyback.offer.manage': true }, { offers: pendingFinalOffer })
    expect(screen.getByText(/Corectează oferta finală/)).toBeInTheDocument()
  })

  it('FINAL_OFFER without offer.manage HIDES "Corectează oferta finală"', () => {
    renderPanel('FINAL_OFFER', {}, { offers: pendingFinalOffer })
    expect(screen.queryByText(/Corectează oferta finală/)).not.toBeInTheDocument()
  })

  it('correcting a final offer pre-fills the current amount and posts the new final price', async () => {
    renderPanel('FINAL_OFFER', { 'buyback.offer.manage': true }, { offers: pendingFinalOffer })
    fireEvent.click(screen.getByText(/Corectează oferta finală/))
    // amount is pre-filled from the current pending final offer
    expect(await screen.findByDisplayValue('10000')).toBeInTheDocument()
    const spinners = await screen.findAllByRole('spinbutton')  // [0]=Sumă
    fireEvent.change(spinners[0], { target: { value: '9500' } })
    fireEvent.click(screen.getByText('Trimite oferta'))
    await waitFor(() => expect(buybackApi.postOffer).toHaveBeenCalled())
    expect(buybackApi.postOffer).toHaveBeenCalledWith(5, expect.objectContaining({
      offer_type: 'final', amount_eur: 9500,
    }))
  })

  it('BOUGHT + finalize permission + no carpark id shows "Finalizează"', () => {
    renderPanel('BOUGHT', { 'buyback.record.finalize': true }, { record: { carpark_vehicle_id: null } })
    expect(screen.getByText(/Finalizează/)).toBeInTheDocument()
  })

  it('BOUGHT without finalize permission HIDES "Finalizează"', () => {
    renderPanel('BOUGHT', {}, { record: { carpark_vehicle_id: null } })
    expect(screen.queryByText(/Finalizează/)).not.toBeInTheDocument()
  })

  it('BOUGHT with carpark_vehicle_id shows the read-only label instead of Finalizează', () => {
    renderPanel('BOUGHT', { 'buyback.record.finalize': true }, { record: { carpark_vehicle_id: 42 } })
    expect(screen.queryByText(/Finalizează/)).not.toBeInTheDocument()
    expect(screen.getByText(/CarPark #42/)).toBeInTheDocument()
  })

  it('cancel is hidden on terminal statuses even with record.edit', () => {
    renderPanel('BOUGHT', { 'buyback.record.edit': true }, { record: { carpark_vehicle_id: 1 } })
    expect(screen.queryByText(/Anulează/)).not.toBeInTheDocument()
  })

  it('cancel shows on a non-terminal status with record.edit', () => {
    renderPanel('PENDING_EVALUATION', { 'buyback.record.edit': true })
    expect(screen.getByText(/Anulează/)).toBeInTheDocument()
  })

  it('cancel is hidden without record.edit', () => {
    renderPanel('PENDING_EVALUATION', {})
    expect(screen.queryByText(/Anulează/)).not.toBeInTheDocument()
  })

  it('reopen shows for an admin (implicit edit) on LOST status', () => {
    renderPanel('LOST', {}, { role: 'admin' })
    expect(screen.getByText(/Redeschide/)).toBeInTheDocument()
  })

  it('reopen shows for a holder of buyback.record.edit on LOST status', () => {
    renderPanel('LOST', { 'buyback.record.edit': true })
    expect(screen.getByText(/Redeschide/)).toBeInTheDocument()
  })

  it('reopen is hidden for a plain user on LOST status', () => {
    renderPanel('LOST', {})
    expect(screen.queryByText(/Redeschide/)).not.toBeInTheDocument()
  })

  it('reopen is hidden for an Acquisition user (finalize but no edit) on LOST status', () => {
    // Reopen is gated by buyback.record.edit; buyback.record.finalize (held by
    // Acquisition) must NOT reveal a button that would 403 on click.
    renderPanel('LOST', { 'buyback.record.finalize': true })
    expect(screen.queryByText(/Redeschide/)).not.toBeInTheDocument()
  })

  it('shows nothing actionable for a user with no permissions on PENDING_EVALUATION', () => {
    renderPanel('PENDING_EVALUATION', {})
    expect(screen.getByText(/Nicio acțiune disponibilă/)).toBeInTheDocument()
  })

  it('PENDING_EVALUATION + record.hold shows "Suspendă"', () => {
    renderPanel('PENDING_EVALUATION', { 'buyback.record.hold': true })
    expect(screen.getByText(/Suspendă/)).toBeInTheDocument()
  })

  it('PENDING_EVALUATION without record.hold HIDES "Suspendă"', () => {
    renderPanel('PENDING_EVALUATION', {})
    expect(screen.queryByText(/Suspendă/)).not.toBeInTheDocument()
  })

  it('ON_HOLD + record.hold shows "Reia" and HIDES "Suspendă"', () => {
    renderPanel('ON_HOLD', { 'buyback.record.hold': true })
    expect(screen.getByText(/Reia/)).toBeInTheDocument()
    expect(screen.queryByText(/Suspendă/)).not.toBeInTheDocument()
  })

  it('a non-active, non-hold status (BOUGHT) HIDES both "Suspendă" and "Reia"', () => {
    renderPanel('BOUGHT', { 'buyback.record.hold': true }, { record: { carpark_vehicle_id: 1 } })
    expect(screen.queryByText(/Suspendă/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Reia/)).not.toBeInTheDocument()
  })

  it('hold dialog submit is disabled until a reason is chosen', () => {
    renderPanel('PENDING_EVALUATION', { 'buyback.record.hold': true })
    fireEvent.click(screen.getByText('Suspendă'))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Suspendă').closest('button')).toBeDisabled()
  })

  it('LOST + custody permission shows "Transferă în custodie"', () => {
    renderPanel('LOST', { 'buyback.record.custody': true }, { record: { carpark_vehicle_id: null } })
    expect(screen.getByText(/Transferă în custodie/)).toBeInTheDocument()
  })

  it('LOST without custody permission HIDES the custody button', () => {
    renderPanel('LOST', {}, { record: { carpark_vehicle_id: null } })
    expect(screen.queryByText(/Transferă în custodie/)).not.toBeInTheDocument()
  })

  it('LOST already transferred HIDES the button and shows the CarPark link', () => {
    renderPanel('LOST', { 'buyback.record.custody': true }, { record: { carpark_vehicle_id: 77 } })
    expect(screen.queryByText(/Transferă în custodie/)).not.toBeInTheDocument()
    expect(screen.getByText(/Custodie/)).toBeInTheDocument()
  })

  it('LOST already transferred HIDES Redeschide (reopen) even with record.edit', () => {
    renderPanel('LOST', { 'buyback.record.edit': true }, { record: { carpark_vehicle_id: 77 } })
    expect(screen.queryByText(/Redeschide/)).not.toBeInTheDocument()
  })

  it('non-LOST HIDES the custody button', () => {
    renderPanel('BOUGHT', { 'buyback.record.custody': true }, { record: { carpark_vehicle_id: null } })
    expect(screen.queryByText(/Transferă în custodie/)).not.toBeInTheDocument()
  })

  // ── Consignment proposal (Propune consignație) ──
  it('PENDING_EVALUATION + offer.manage shows "Propune consignație"', () => {
    renderPanel('PENDING_EVALUATION', { 'buyback.offer.manage': true })
    expect(screen.getByText(/Propune consignație/)).toBeInTheDocument()
  })

  it('PENDING_EVALUATION without offer.manage HIDES "Propune consignație"', () => {
    renderPanel('PENDING_EVALUATION', {})
    expect(screen.queryByText(/Propune consignație/)).not.toBeInTheDocument()
  })

  it('CONSIGNMENT_OFFER + record.edit shows consignment accept/decline + proposed terms', () => {
    const offers = [
      {
        id: 9,
        record_id: 5,
        offer_type: 'consignment',
        amount_eur: 15000,
        client_decision: 'pending',
        consignment_terms: {
          owner_price: 15000,
          currency: 'EUR',
          commission_type: 'percent',
          commission_value: 10,
          min_sale_price: 14000,
          contract_number: 'CS-9',
          agreement_date: '2026-10-14',
          expiry_date: '2027-01-01',
        },
      },
    ] as unknown as BuybackOffer[]
    renderPanel('CONSIGNMENT_OFFER', { 'buyback.record.edit': true }, { offers })
    expect(screen.getByText(/Acceptă consignația/)).toBeInTheDocument()
    expect(screen.getByText(/Refuză consignația/)).toBeInTheDocument()
    expect(screen.getByText(/Termeni consignație propuși/)).toBeInTheDocument()
  })

  it('CONSIGNMENT_OFFER without record.edit HIDES the decision buttons', () => {
    renderPanel('CONSIGNMENT_OFFER', {})
    expect(screen.queryByText(/Acceptă consignația/)).not.toBeInTheDocument()
  })

  it('CONSIGNAT with a CarPark vehicle shows the consignment link', () => {
    renderPanel('CONSIGNAT', {}, { record: { carpark_vehicle_id: 77 } })
    expect(screen.getByText(/Consignat → CarPark #77/)).toBeInTheDocument()
  })
})
