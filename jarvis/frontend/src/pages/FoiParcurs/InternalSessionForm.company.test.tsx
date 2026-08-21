import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { submitInternalSession, getVehicles, getCompanies } = vi.hoisted(() => ({
  submitInternalSession: vi.fn(), getVehicles: vi.fn(), getCompanies: vi.fn(),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { submitInternalSession, getVehicles, getCompanies } }))
vi.mock('@/api/digest', () => ({ digestApi: { searchUsers: vi.fn() } }))

// user.company (a name string) drives the default company selection.
const auth = vi.hoisted(() => ({ user: { name: 'Test Advisor', company: 'AUTOWORLD' } as { name: string; company?: string } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: auth.user }) }))

import InternalSessionForm from './InternalSessionForm'

const companies = [
  { id: 16, company: 'AUTOWORLD' },
  { id: 11, company: 'Other Co' },
]
const vehicles = [
  { id: 1, vin: 'VF1AAA', mark: 'Dacia', model: 'Duster', registration_number: 'CJ01AAA', company_id: 16, odometer_km: 50000 },
  { id: 2, vin: 'VF1BBB', mark: 'Renault', model: 'Clio', registration_number: 'CJ02BBB', company_id: 11, odometer_km: 12000 },
]

function wrap(ui: React.ReactNode) {
  getVehicles.mockResolvedValue({ vehicles })
  getCompanies.mockResolvedValue({ companies })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('InternalSessionForm company filter', () => {
  // Radix Select needs a few DOM APIs jsdom doesn't implement.
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
    window.HTMLElement.prototype.releasePointerCapture = vi.fn()
  })
  beforeEach(() => { auth.user = { name: 'Test Advisor', company: 'AUTOWORLD' } })

  it('defaults the company filter to the logged-in user’s own company', async () => {
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    const trigger = await screen.findByTestId('internal-company')
    await waitFor(() => expect(trigger).toHaveTextContent('AUTOWORLD'))
  })

  it('narrows the car picker to the selected company', async () => {
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    const trigger = await screen.findByTestId('internal-company')
    await waitFor(() => expect(trigger).toHaveTextContent('AUTOWORLD')) // default company 16
    fireEvent.click(screen.getByTestId('internal-vehicle'))
    expect(await screen.findByText(/Dacia Duster/)).toBeInTheDocument() // company 16
    expect(screen.queryByText(/Renault Clio/)).not.toBeInTheDocument()  // company 11 — hidden
  })

  it('shows every car when "Toate companiile" is chosen', async () => {
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    const trigger = await screen.findByTestId('internal-company')
    await waitFor(() => expect(trigger).toHaveTextContent('AUTOWORLD'))
    fireEvent.click(trigger)
    fireEvent.click(await screen.findByText('Toate companiile'))
    fireEvent.click(screen.getByTestId('internal-vehicle'))
    expect(await screen.findByText(/Dacia Duster/)).toBeInTheDocument()
    expect(await screen.findByText(/Renault Clio/)).toBeInTheDocument()
  })

  it('seeds the company filter from initialCompanyId when embedded (Hub)', async () => {
    wrap(<InternalSessionForm embedded initialCompanyId={11} onCancel={vi.fn()} onDone={vi.fn()} />)
    const trigger = await screen.findByTestId('internal-company')
    await waitFor(() => expect(trigger).toHaveTextContent('Other Co'))
  })
})
