import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fieldSalesApi, type FSClient360 } from '@/api/fieldSales'

const getClient360 = vi.fn()
const refreshFiscal = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: {
    getClient360: (...a: unknown[]) => getClient360(...a),
    refreshFiscal: (...a: unknown[]) => refreshFiscal(...a),
  },
}))
import ClientCard360 from './ClientCard360'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const emptyPayload: FSClient360 = {
  profile: null, fleet: [], last_purchases: [], last_interactions: [],
  visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
}

describe('ClientCard360', () => {
  beforeEach(() => {
    getClient360.mockReset()
    refreshFiscal.mockReset()
  })
  afterEach(() => {
    vi.restoreAllMocks()
    // The refresh-error test swaps in a fresh rejecting vi.fn() on
    // fieldSalesApi.refreshFiscal; re-wire it back to the shared `refreshFiscal`
    // mock so a later test can't inherit that rejecting stub (no ordering dep).
    ;(fieldSalesApi as { refreshFiscal: (...a: unknown[]) => unknown }).refreshFiscal = (...a) => refreshFiscal(...a)
  })

  it('renders fleet vehicles from the 360 payload', async () => {
    getClient360.mockResolvedValue({
      profile: { id: 1, client_id: 760, client_type: 'company', industry: 'Transport', country_code: 'RO', legal_form: 'SRL', assigned_kam_id: 3, fleet_size: 1, renewal_score: 78, cui: '40123456', estimated_annual_value: 450000, priority: 'high' },
      fleet: [{ id: 1, client_id: 760, vehicle_make: 'Audi', vehicle_model: 'A6', vehicle_year: 2021, vin: null, license_plate: 'CJ11DEM', purchase_date: null, purchase_price: null, purchase_currency: 'EUR', estimated_mileage: null, financing_type: null, financing_expiry: null, warranty_expiry: null, status: 'active', renewal_candidate: true, renewal_reason: 'garantie' }],
      last_purchases: [], last_interactions: [], visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
    })
    wrap(<ClientCard360 clientId={760} />)
    expect(await screen.findByText(/Audi A6/)).toBeInTheDocument()
  })

  it('shows the API error message when the 360 fetch fails', async () => {
    getClient360.mockRejectedValue({ data: { error: 'Clientul nu a fost gasit' } })
    wrap(<ClientCard360 clientId={760} />)
    expect(await screen.findByText('Clientul nu a fost gasit')).toBeInTheDocument()
  })

  it('renders empty-state copy for every section when the payload has no data', async () => {
    getClient360.mockResolvedValue(emptyPayload)
    wrap(<ClientCard360 clientId={760} />)
    expect(await screen.findByText(/Niciun vehicul/i)).toBeInTheDocument()
    expect(screen.getByText(/Nicio achizitie/i)).toBeInTheDocument()
    expect(screen.getByText(/Niciun istoric de vizite/i)).toBeInTheDocument()
    expect(screen.getByText(/Nicio potrivire in stoc/i)).toBeInTheDocument()
    expect(screen.getByText(/Date fiscale indisponibile/i)).toBeInTheDocument()
  })

  it('the Reimprospateaza button calls refreshFiscal and re-fetches the payload', async () => {
    getClient360
      .mockResolvedValueOnce(emptyPayload)
      .mockResolvedValueOnce({
        ...emptyPayload,
        fiscal: { company_name: 'ACME SRL', address: 'Str. Test 1', is_vat_payer: true, is_inactive: false, inactivation_date: null, fetched_at: '2026-08-01T10:00:00Z' },
      })
    refreshFiscal.mockResolvedValue({ success: true })
    wrap(<ClientCard360 clientId={760} />)

    const btn = await screen.findByRole('button', { name: /reimprospateaza/i })
    fireEvent.click(btn)

    expect(await screen.findByText('ACME SRL')).toBeInTheDocument()
    expect(refreshFiscal).toHaveBeenCalledWith(760)
  })

  it('shows the inline error when the refresh-fiscal mutation fails', async () => {
    getClient360.mockResolvedValue(emptyPayload)
    // Reassign a fresh rejecting mock directly on the mocked module (rather than
    // the shared `refreshFiscal` wrapper, which the resolve-path test above also
    // uses). This mirrors the reject-path convention in NoteCaptureModal.test.tsx
    // and avoids a false-positive "unhandled rejection" Vitest flags when a
    // rejecting mock shares a mutation-backed wrapper with a prior resolving
    // test. afterEach re-wires the wrapper so this doesn't leak.
    ;(fieldSalesApi.refreshFiscal as ReturnType<typeof vi.fn>) = vi.fn().mockRejectedValue({ data: { error: 'ANAF indisponibil momentan' } })
    wrap(<ClientCard360 clientId={760} />)

    const btn = await screen.findByRole('button', { name: /reimprospateaza/i })
    fireEvent.click(btn)

    await waitFor(() => expect(screen.getByText('ANAF indisponibil momentan')).toBeInTheDocument())
  })
})
