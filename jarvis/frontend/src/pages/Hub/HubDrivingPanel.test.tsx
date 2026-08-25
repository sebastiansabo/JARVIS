import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 11, company: 'PREMIUM' }] }),
  getBrands: vi.fn().mockResolvedValue({ brands: [] }),
  getContracts: vi.fn().mockResolvedValue({ contracts: [], total: 0, page: 1, per_page: 1000 }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
} }))
vi.mock('@/pages/Hub/DrivingSessionsList', () => ({
  default: ({ companyId, onReturn, documentType, brand }: { companyId: number; onReturn?: (id: number) => void; documentType?: string; brand?: string }) => (
    <div>sessions:{companyId}<span data-testid="sessions-doctype">{documentType ?? 'sales'}</span><span data-testid="sessions-brand">{brand ?? ''}</span><button onClick={() => onReturn?.(11)}>mock-retur</button></div>
  ),
}))
vi.mock('@/pages/Hub/DrivingCalendar', () => ({
  default: ({ companyId, onAdd }: { companyId: number; onAdd?: (departure: string, ret: string) => void }) => (
    <div>calendar:{companyId}<button onClick={() => onAdd?.('2026-08-05T11:00', '2026-08-05T12:00')}>mock-add</button></div>
  ),
}))
vi.mock('@/pages/FoiParcurs/TestDriveForm', () => ({
  default: ({ onDone, onCancel, initialDeparture, initialDocumentType }: { onDone?: (c: unknown) => void; onCancel: () => void; initialDeparture?: string; initialDocumentType?: string }) => (
    <div>form:{initialDeparture ?? ''}<span data-testid="form-doctype">{initialDocumentType ?? 'sales'}</span><button onClick={onCancel}>x</button><button onClick={() => onDone?.({ id: 1 })}>done</button></div>
  ),
}))
vi.mock('@/pages/FoiParcurs/InternalSessionForm', () => ({
  default: ({ onDone, onCancel, initialDeparture, initialCompanyId }: { onDone?: (c: unknown) => void; onCancel: () => void; initialDeparture?: string; initialCompanyId?: number }) => (
    <div>internal-form:{initialDeparture ?? ''} company:{initialCompanyId ?? 'none'}<button onClick={onCancel}>x</button><button onClick={() => onDone?.({ id: 2 })}>done</button></div>
  ),
}))
vi.mock('@/pages/FoiParcurs/TestDriveReturn', () => ({ default: ({ id }: { id: number }) => <div>return-overlay:{id}</div> }))

// Opens the "+" chooser then picks "Sesiune cu client" so tests that only
// care about the resulting form don't need to know about the chooser step.
async function openClientForm() {
  fireEvent.click(screen.getByRole('button', { name: /nou/i }))
  fireEvent.click(await screen.findByRole('button', { name: /sesiune cu client/i }))
}

import HubDrivingPanel from './HubDrivingPanel'
import { foiParcursApi } from '@/api/foiParcurs'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('HubDrivingPanel', () => {
  // usePersistedState reads/writes localStorage (e.g. the active tab), which
  // otherwise leaks across tests in this file — reset so each test starts
  // from the real defaults (tab='sessions', companyId=0).
  beforeEach(() => localStorage.clear())

  it('renders the Sessions tab by default and can open the New overlay', async () => {
    wrap(<HubDrivingPanel />)
    expect(await screen.findByText(/sessions:11/)).toBeInTheDocument()
    await openClientForm()
    expect(screen.getByText(/^form:/)).toBeInTheDocument()
  })

  it('clicking "+" opens the Client/Intern chooser', async () => {
    wrap(<HubDrivingPanel />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: /nou/i }))
    expect(await screen.findByRole('button', { name: /sesiune cu client/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sesiune internă/i })).toBeInTheDocument()
    // Neither form is rendered yet — only the chooser.
    expect(screen.queryByText(/^form:/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^internal-form:/)).not.toBeInTheDocument()
  })

  it('picking "Sesiune internă" renders InternalSessionForm (with the active company)', async () => {
    wrap(<HubDrivingPanel />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: /nou/i }))
    fireEvent.click(await screen.findByRole('button', { name: /sesiune internă/i }))
    // Auto-selected company 11 → passed through to the internal form.
    expect(await screen.findByText(/internal-form:.*company:11/)).toBeInTheDocument()
    expect(screen.queryByText(/^form:/)).not.toBeInTheDocument()
  })

  it('passes NO company to InternalSessionForm under "Toate companiile" (-1) so its picker shows all cars', async () => {
    // Seed the persisted company filter to ALL_COMPANIES (-1); the panel's
    // auto-select only kicks in for 0, so -1 sticks. The fix maps -1 → undefined
    // (companyId > 0 ? companyId : undefined), otherwise the internal form would
    // filter vehicles on company_id === -1 → an empty, unrecoverable dropdown.
    localStorage.setItem('hub-driving-company', '-1')
    wrap(<HubDrivingPanel />)
    await screen.findByText(/sessions:-1/)
    fireEvent.click(screen.getByRole('button', { name: /nou/i }))
    fireEvent.click(await screen.findByRole('button', { name: /sesiune internă/i }))
    expect(await screen.findByText(/internal-form:.*company:none/)).toBeInTheDocument()
  })

  it('opens the New form prefilled with the slot datetime when the calendar requests an add', async () => {
    wrap(<HubDrivingPanel />)
    fireEvent.mouseDown(await screen.findByRole('tab', { name: /calendar/i }))
    fireEvent.click(await screen.findByRole('button', { name: /mock-add/i }))
    fireEvent.click(await screen.findByRole('button', { name: /sesiune cu client/i }))
    expect(await screen.findByText('form:2026-08-05T11:00')).toBeInTheDocument()
  })

  it('opens the Intern form prefilled with the slot datetime when the calendar requests an add', async () => {
    wrap(<HubDrivingPanel />)
    fireEvent.mouseDown(await screen.findByRole('tab', { name: /calendar/i }))
    fireEvent.click(await screen.findByRole('button', { name: /mock-add/i }))
    fireEvent.click(await screen.findByRole('button', { name: /sesiune internă/i }))
    expect(await screen.findByText(/internal-form:2026-08-05T11:00/)).toBeInTheDocument()
  })

  it('switches to the Calendar tab', async () => {
    wrap(<HubDrivingPanel />)
    // Radix Tabs' trigger selects on `mousedown` (not `click`) — see
    // @radix-ui/react-tabs's Trigger, which wires selection to onMouseDown/
    // onFocus/onKeyDown, never onClick. fireEvent.click alone never fires
    // any of those, so the tab wouldn't switch; mousedown is the real
    // interaction that drives it (no @testing-library/user-event dependency
    // in this project to fall back on).
    fireEvent.mouseDown(await screen.findByRole('tab', { name: /calendar/i }))
    expect(await screen.findByText(/calendar:11/)).toBeInTheDocument()
  })

  it('opens the return overlay when a session row requests return', async () => {
    wrap(<HubDrivingPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /mock-retur/i }))
    expect(await screen.findByText('return-overlay:11')).toBeInTheDocument()
  })

  it('scopes the sessions list to sales by default', async () => {
    wrap(<HubDrivingPanel />)
    await screen.findByText(/sessions:11/)
    expect(screen.getByTestId('sessions-doctype')).toHaveTextContent('sales')
  })

  it('invalidates the sessions list and closes the overlay when the New form completes', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const spy = vi.spyOn(qc, 'invalidateQueries')
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><HubDrivingPanel /></MemoryRouter>
      </QueryClientProvider>
    )

    fireEvent.click(await screen.findByRole('button', { name: /nou/i }))
    fireEvent.click(await screen.findByRole('button', { name: /sesiune cu client/i }))
    expect(screen.getByText(/^form:/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /done/i }))

    expect(spy).toHaveBeenCalledWith({ queryKey: ['foi-contracts-all'] })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['odometer-history'] })
    expect(screen.queryByText(/^form:/)).not.toBeInTheDocument()
  })
})

describe('HubDrivingPanel — Service (Mașini de curtoazie) mode', () => {
  beforeEach(() => { localStorage.clear(); vi.mocked(foiParcursApi.getBrands).mockResolvedValue({ brands: ['Audi'] }) })

  it('scopes the sessions list to service', async () => {
    wrap(<HubDrivingPanel documentType="service" />)
    await screen.findByText(/sessions:11/)
    expect(screen.getByTestId('sessions-doctype')).toHaveTextContent('service')
  })

  it('passes an empty brand to children (courtesy stock is multi-brand)', async () => {
    wrap(<HubDrivingPanel documentType="service" />)
    await screen.findByText(/sessions:11/)
    expect(screen.getByTestId('sessions-brand')).toHaveTextContent('')
  })

  it('the "+" chooser offers Rent-a-car + Internal but NOT the client card', async () => {
    wrap(<HubDrivingPanel documentType="service" />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: /nou/i }))
    expect(await screen.findByRole('button', { name: /rent-a-car/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sesiune internă/i })).toBeInTheDocument()
    expect(screen.queryByText(/sesiune cu client/i)).not.toBeInTheDocument()
  })

  it('picking Rent-a-car opens the form in service context', async () => {
    wrap(<HubDrivingPanel documentType="service" />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: /nou/i }))
    fireEvent.click(await screen.findByRole('button', { name: /rent-a-car/i }))
    expect(await screen.findByText(/^form:/)).toBeInTheDocument()
    expect(screen.getByTestId('form-doctype')).toHaveTextContent('service')
  })

  it('hides the franchise brand dropdown in the Filtre modal', async () => {
    wrap(<HubDrivingPanel documentType="service" />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: /filtre/i }))
    // Company filter is always present; the "Marcă" (brand) filter is hidden in service.
    expect(await screen.findByText(/companie/i)).toBeInTheDocument()
    expect(screen.queryByText(/marcă/i)).not.toBeInTheDocument()
  })
})
