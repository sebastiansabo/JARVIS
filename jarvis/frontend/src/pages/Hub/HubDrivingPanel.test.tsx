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
  default: ({ companyId, onReturn }: { companyId: number; onReturn?: (id: number) => void }) => (
    <div>sessions:{companyId}<button onClick={() => onReturn?.(11)}>mock-retur</button></div>
  ),
}))
vi.mock('@/pages/Hub/DrivingCalendar', () => ({
  default: ({ companyId, onAdd }: { companyId: number; onAdd?: (departure: string, ret: string) => void }) => (
    <div>calendar:{companyId}<button onClick={() => onAdd?.('2026-08-05T11:00', '2026-08-05T12:00')}>mock-add</button></div>
  ),
}))
vi.mock('@/pages/FoiParcurs/TestDriveForm', () => ({
  default: ({ onDone, onCancel, initialDeparture }: { onDone?: (c: unknown) => void; onCancel: () => void; initialDeparture?: string }) => (
    <div>form:{initialDeparture ?? ''}<button onClick={onCancel}>x</button><button onClick={() => onDone?.({ id: 1 })}>done</button></div>
  ),
}))
vi.mock('@/pages/FoiParcurs/InternalSessionForm', () => ({
  default: ({ onDone, onCancel, initialDeparture }: { onDone?: (c: unknown) => void; onCancel: () => void; initialDeparture?: string }) => (
    <div>internal-form:{initialDeparture ?? ''}<button onClick={onCancel}>x</button><button onClick={() => onDone?.({ id: 2 })}>done</button></div>
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

  it('picking "Sesiune internă" renders InternalSessionForm', async () => {
    wrap(<HubDrivingPanel />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: /nou/i }))
    fireEvent.click(await screen.findByRole('button', { name: /sesiune internă/i }))
    expect(await screen.findByText(/^internal-form:/)).toBeInTheDocument()
    expect(screen.queryByText(/^form:/)).not.toBeInTheDocument()
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
    expect(await screen.findByText('internal-form:2026-08-05T11:00')).toBeInTheDocument()
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
