import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { submitInternalSession, updatePlan, getContract, getVehicles, getCompanies } = vi.hoisted(() => ({
  submitInternalSession: vi.fn(), updatePlan: vi.fn(), getContract: vi.fn(),
  getVehicles: vi.fn(), getCompanies: vi.fn(),
}))
vi.mock('@/api/foiParcurs', () => ({
  foiParcursApi: { submitInternalSession, updatePlan, getContract, getVehicles, getCompanies },
}))
vi.mock('@/api/digest', () => ({ digestApi: { searchUsers: vi.fn() } }))

const auth = vi.hoisted(() => ({ user: { name: 'Logged In', company: 'AUTOWORLD' } as { name: string; company?: string } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: auth.user }) }))

import InternalSessionForm from './InternalSessionForm'

const companies = [{ id: 16, company: 'AUTOWORLD' }, { id: 11, company: 'Other Co' }]
const vehicles = [
  { id: 1, vin: 'VF1AAA', mark: 'Dacia', model: 'Duster', registration_number: 'CJ01AAA', company_id: 16, odometer_km: 50000 },
]
// A PLANNED internal draft — the row "Corectează" edits in place.
const draft = {
  id: 7, contract_id: 'FP-7', is_internal: true, status: 'PLANNED', route_type: 'TD',
  company_id: 16, vin: 'VF1AAA', advisor_name: 'Draft Driver',
  departure_datetime: '2026-07-28T09:00:00', return_datetime: '2026-07-28T10:00:00',
  itinerary: 'tur service',
}

function wrap(ui: React.ReactNode) {
  getVehicles.mockResolvedValue({ vehicles })
  getCompanies.mockResolvedValue({ companies })
  getContract.mockResolvedValue({ contract: draft })
  updatePlan.mockResolvedValue({ success: true, contract: draft })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('InternalSessionForm edit mode (Corectează a planned internal draft)', () => {
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
    window.HTMLElement.prototype.releasePointerCapture = vi.fn()
  })
  beforeEach(() => {
    submitInternalSession.mockReset(); updatePlan.mockReset(); getContract.mockReset()
    auth.user = { name: 'Logged In', company: 'AUTOWORLD' }
  })

  it('prefills from the draft and hides the client-form chrome (mode toggle + km)', async () => {
    wrap(<InternalSessionForm embedded editId={7} onCancel={vi.fn()} onDone={vi.fn()} />)
    // Driver comes from the draft (advisor_name), NOT the logged-in user.
    expect(await screen.findByText('Draft Driver')).toBeInTheDocument()
    expect(screen.queryByText('Logged In')).not.toBeInTheDocument()
    // Slim edit: no Începe acum/Planifică toggle and no KM field.
    expect(screen.queryByTestId('internal-mode-now')).not.toBeInTheDocument()
    expect(screen.queryByTestId('internal-mode-plan')).not.toBeInTheDocument()
    expect(screen.queryByTestId('internal-km')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /salvează modificările/i })).toBeInTheDocument()
  })

  it('saves via updatePlan (not submitInternalSession) and reports done', async () => {
    const onDone = vi.fn()
    wrap(<InternalSessionForm embedded editId={7} onCancel={vi.fn()} onDone={onDone} />)
    // Wait for the draft to prefill (driver badge) before submitting — the save
    // button renders immediately, but the payload needs the loaded fields.
    await screen.findByText('Draft Driver')
    fireEvent.click(screen.getByRole('button', { name: /salvează modificările/i }))
    await waitFor(() => expect(updatePlan).toHaveBeenCalledTimes(1))
    const [id, payload] = updatePlan.mock.calls[0]
    expect(id).toBe(7)
    expect(payload).toMatchObject({
      company_id: 16, vin: 'VF1AAA', advisor_name: 'Draft Driver',
      departure_datetime: '2026-07-28T09:00', itinerary: 'tur service',
    })
    expect(submitInternalSession).not.toHaveBeenCalled()
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(draft))
  })

  it('keeps the prefilled car when the draft loads before the vehicle list', async () => {
    // Force the draft (getContract) to resolve BEFORE the vehicle list: a naive
    // "drop car not in list" reconciler would wipe the just-prefilled vin while
    // the list is still empty. Submit must still carry the draft's car.
    let resolveVehicles!: (v: { vehicles: typeof vehicles }) => void
    getVehicles.mockReturnValue(new Promise((res) => { resolveVehicles = res }))
    getCompanies.mockResolvedValue({ companies })
    getContract.mockResolvedValue({ contract: draft })
    updatePlan.mockResolvedValue({ success: true, contract: draft })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const onDone = vi.fn()
    render(<QueryClientProvider client={qc}><MemoryRouter>
      <InternalSessionForm embedded editId={7} onCancel={vi.fn()} onDone={onDone} />
    </MemoryRouter></QueryClientProvider>)
    await screen.findByText('Draft Driver')           // draft prefilled, vehicles still pending
    await act(async () => { resolveVehicles({ vehicles }) }) // now the list arrives
    // Retry the submit until the loaded car resolves — asserts the prefilled vin
    // survived the list arriving (the bug cleared it, leaving a vehicle_required).
    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: /salvează modificările/i }))
      expect(updatePlan).toHaveBeenCalled()
    })
    expect(updatePlan.mock.calls[0][1]).toMatchObject({ vin: 'VF1AAA' })
  })
})
