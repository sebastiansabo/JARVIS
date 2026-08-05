import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fieldSalesApi, type FSClient360 } from '@/api/fieldSales'

const getClient360 = vi.fn()
const refreshFiscal = vi.fn()
const updateClient = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: {
    getClient360: (...a: unknown[]) => getClient360(...a),
    refreshFiscal: (...a: unknown[]) => refreshFiscal(...a),
    updateClient: (...a: unknown[]) => updateClient(...a),
  },
}))
import ClientCard360 from './ClientCard360'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const emptyPayload: FSClient360 = {
  client: null,
  profile: null, fleet: [], last_purchases: [], last_interactions: [],
  visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
}

describe('ClientCard360', () => {
  beforeEach(() => {
    getClient360.mockReset()
    refreshFiscal.mockReset()
    updateClient.mockReset()
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
      client: null,
      profile: { id: 1, client_id: 760, client_type: 'company', industry: 'Transport', country_code: 'RO', legal_form: 'SRL', assigned_kam_id: 3, fleet_size: 1, renewal_score: 78, cui: '40123456', estimated_annual_value: 450000, priority: 'high' },
      fleet: [{ id: 1, client_id: 760, vehicle_make: 'Audi', vehicle_model: 'A6', vehicle_year: 2021, vin: null, license_plate: 'CJ11DEM', purchase_date: null, purchase_price: null, purchase_currency: 'EUR', estimated_mileage: null, financing_type: null, financing_expiry: null, warranty_expiry: null, status: 'active', renewal_candidate: true, renewal_reason: 'garantie' }],
      last_purchases: [], last_interactions: [], visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
    })
    wrap(<ClientCard360 clientId={760} />)
    expect(await screen.findByText(/Audi A6/)).toBeInTheDocument()
  })

  it('renders the fiscal data with real ANAF keys, a TVA badge, and the passed client name', async () => {
    getClient360.mockResolvedValue({
      ...emptyPayload,
      fiscal: {
        denumire: 'DEMO AGRO FERM SRL', adresa: 'DN79 KM 12, ARAD', cui: '44556677',
        nrRegCom: 'J02/1212/2019', scpTVA: true, stare_inregistrare: 'INREGISTRAT',
      },
    })
    wrap(<ClientCard360 clientId={760} clientName="DEMO Agro Ferm SRL" />)

    expect(await screen.findByText('DEMO AGRO FERM SRL')).toBeInTheDocument()
    expect(screen.getByText('DN79 KM 12, ARAD')).toBeInTheDocument()
    expect(screen.getByText(/Plătitor TVA|Platitor TVA/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'DEMO Agro Ferm SRL' })).toBeInTheDocument()
    expect(screen.queryByText(/Invalid Date/i)).not.toBeInTheDocument()
  })

  it('renders the fiscal data from a NESTED ANAF payload (real ANAF shape)', async () => {
    getClient360.mockResolvedValue({
      ...emptyPayload,
      fiscal: {
        date_generale: { denumire: 'DEMO SRL', adresa: 'STR X', cui: '123', nrRegCom: 'J1/1/2020' },
        inregistrare_scop_Tva: { scpTVA: true },
      },
    })
    wrap(<ClientCard360 clientId={760} />)

    expect(await screen.findByText('DEMO SRL')).toBeInTheDocument()
    expect(screen.getByText('STR X')).toBeInTheDocument()
    expect(screen.getByText(/Plătitor TVA|Platitor TVA/)).toBeInTheDocument()
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
        fiscal: { denumire: 'ACME SRL', adresa: 'Str. Test 1', cui: '12345678', nrRegCom: 'J02/100/2020', scpTVA: true, stare_inregistrare: 'INREGISTRAT' },
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

  it('reveals the edit form prefilled from the client row, saves, and invalidates', async () => {
    const client360Data = {
      client: { id: 760, display_name: 'ACME SRL', contact_person: 'Ion', phone: '0722000000', email: 'a@b.ro', street: null, city: 'Cluj', region: null, country: null, company_name: 'ACME SRL', nr_reg: 'J12/34/2020' },
      profile: { id: 1, client_id: 760, client_type: 'company', industry: null, country_code: 'RO', legal_form: null, assigned_kam_id: null, fleet_size: 0, priority: 'medium', renewal_score: 0, cui: null, estimated_annual_value: null },
      fleet: [], last_purchases: [], last_interactions: [], visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
    }
    getClient360.mockResolvedValue(client360Data)
    updateClient.mockResolvedValue({ success: true, client: client360Data.client })
    wrap(<ClientCard360 clientId={760} clientName="ACME SRL" />)
    fireEvent.click(await screen.findByRole('button', { name: /editeaz/i }))
    // Prefill: the existing phone shows in an input.
    const phone = await screen.findByDisplayValue('0722000000')
    fireEvent.change(phone, { target: { value: '0722999888' } })
    fireEvent.click(screen.getByRole('button', { name: /salveaz/i }))
    await waitFor(() => expect(updateClient).toHaveBeenCalledWith(760, expect.objectContaining({ phone: '0722999888' })))
  })

  it('disables Salvează when the Nume field is cleared', async () => {
    const client360Data = {
      client: { id: 760, display_name: 'ACME SRL', contact_person: 'Ion', phone: '0722000000', email: 'a@b.ro', street: null, city: 'Cluj', region: null, country: null, company_name: 'ACME Distribution SRL', nr_reg: 'J12/34/2020' },
      profile: { id: 1, client_id: 760, client_type: 'company', industry: null, country_code: 'RO', legal_form: null, assigned_kam_id: null, fleet_size: 0, priority: 'medium', renewal_score: 0, cui: null, estimated_annual_value: null },
      fleet: [], last_purchases: [], last_interactions: [], visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
    }
    getClient360.mockResolvedValue(client360Data)
    wrap(<ClientCard360 clientId={760} clientName="ACME SRL" />)
    fireEvent.click(await screen.findByRole('button', { name: /editeaz/i }))
    const nume = await screen.findByDisplayValue('ACME SRL')
    fireEvent.change(nume, { target: { value: '' } })
    expect(screen.getByRole('button', { name: /salveaz/i })).toBeDisabled()
    expect(updateClient).not.toHaveBeenCalled()
  })

  it('cancel exits edit mode without calling updateClient', async () => {
    const client360Data = {
      client: { id: 760, display_name: 'ACME SRL', contact_person: 'Ion', phone: '0722000000', email: 'a@b.ro', street: null, city: 'Cluj', region: null, country: null, company_name: 'ACME SRL', nr_reg: 'J12/34/2020' },
      profile: { id: 1, client_id: 760, client_type: 'company', industry: null, country_code: 'RO', legal_form: null, assigned_kam_id: null, fleet_size: 0, priority: 'medium', renewal_score: 0, cui: null, estimated_annual_value: null },
      fleet: [], last_purchases: [], last_interactions: [], visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
    }
    getClient360.mockResolvedValue(client360Data)
    updateClient.mockResolvedValue({ success: true, client: client360Data.client })
    wrap(<ClientCard360 clientId={760} clientName="ACME SRL" />)
    fireEvent.click(await screen.findByRole('button', { name: /editeaz/i }))
    fireEvent.click(screen.getByRole('button', { name: /anuleaz/i }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /salveaz/i })).not.toBeInTheDocument())
    expect(updateClient).not.toHaveBeenCalled()
  })
})
