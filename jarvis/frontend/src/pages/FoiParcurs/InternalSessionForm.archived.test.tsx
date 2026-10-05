import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { submitInternalSession, getVehicles, getCompanies } = vi.hoisted(() => ({
  submitInternalSession: vi.fn(), getVehicles: vi.fn(), getCompanies: vi.fn(),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { submitInternalSession, getVehicles, getCompanies } }))
vi.mock('@/api/digest', () => ({ digestApi: { searchUsers: vi.fn() } }))

const auth = vi.hoisted(() => ({ user: { name: 'Test Advisor', company: 'AUTOWORLD' } as { name: string; company?: string } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: auth.user }) }))

import InternalSessionForm from './InternalSessionForm'

const companies = [{ id: 16, company: 'AUTOWORLD' }]
// All in company 16 so the default company filter keeps them in scope; the only
// difference under test is is_active (archived) / locked_out (blocked).
const vehicles = [
  { id: 1, vin: 'VF1ACTIVE', mark: 'Dacia', model: 'Duster', registration_number: 'CJ01AAA', company_id: 16, odometer_km: 50000, is_active: true },
  { id: 2, vin: 'VF1ARCH', mark: 'Opel', model: 'Astra', registration_number: 'CJ02ARC', company_id: 16, odometer_km: 80000, is_active: false },
  { id: 3, vin: 'VF1LOCK', mark: 'Ford', model: 'Focus', registration_number: 'CJ03LCK', company_id: 16, odometer_km: 30000, is_active: true, locked_out: true },
]

function wrap(ui: React.ReactNode) {
  getVehicles.mockResolvedValue({ vehicles })
  getCompanies.mockResolvedValue({ companies })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('InternalSessionForm archived/blocked car visibility', () => {
  // Radix Select needs a few DOM APIs jsdom doesn't implement.
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
    window.HTMLElement.prototype.releasePointerCapture = vi.fn()
  })
  beforeEach(() => { auth.user = { name: 'Test Advisor', company: 'AUTOWORLD' } })

  it('hides archived (is_active=false) cars from the picker', async () => {
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    const trigger = await screen.findByTestId('internal-company')
    await waitFor(() => expect(trigger).toHaveTextContent('AUTOWORLD'))
    fireEvent.click(screen.getByTestId('internal-vehicle'))
    expect(await screen.findByText(/Dacia Duster/)).toBeInTheDocument() // active — shown
    expect(screen.queryByText(/Opel Astra/)).not.toBeInTheDocument()    // archived — hidden
  })

  it('still shows blocked (locked_out) cars — they surface a 409 on submit by design', async () => {
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    const trigger = await screen.findByTestId('internal-company')
    await waitFor(() => expect(trigger).toHaveTextContent('AUTOWORLD'))
    fireEvent.click(screen.getByTestId('internal-vehicle'))
    expect(await screen.findByText(/Ford Focus/)).toBeInTheDocument()   // blocked — still shown
  })
})
