import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
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
    getLookupOptions: vi.fn(() => Promise.resolve({ vat_statuses: [] })),
  },
}))

// role + permissions read at render → mutate per test to exercise the
// permission-gating matrix (actions must be HIDDEN, not just disabled).
const auth = vi.hoisted(() => ({ role: 'user', permissions: {} as Record<string, boolean> }))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { role_name: auth.role, permissions: auth.permissions }, isLoading: false }),
}))

import ActionPanel from './ActionPanel'
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

  it('PENDING_EVALUATION + offer.manage shows "Postează ofertă inițială"', () => {
    renderPanel('PENDING_EVALUATION', { 'buyback.offer.manage': true })
    expect(screen.getByText(/Postează ofertă inițială/)).toBeInTheDocument()
  })

  it('PENDING_EVALUATION without offer.manage HIDES the offer button', () => {
    renderPanel('PENDING_EVALUATION', {})
    expect(screen.queryByText(/Postează ofertă/)).not.toBeInTheDocument()
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

  it('reopen shows for an admin on LOST status', () => {
    renderPanel('LOST', {}, { role: 'admin' })
    expect(screen.getByText(/Redeschide/)).toBeInTheDocument()
  })

  it('reopen is hidden for a non-admin/non-finalize user on LOST status', () => {
    renderPanel('LOST', {})
    expect(screen.queryByText(/Redeschide/)).not.toBeInTheDocument()
  })

  it('shows nothing actionable for a user with no permissions on PENDING_EVALUATION', () => {
    renderPanel('PENDING_EVALUATION', {})
    expect(screen.getByText(/Nicio acțiune disponibilă/)).toBeInTheDocument()
  })
})
