import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { submitInternalSession, getVehicles } = vi.hoisted(() => ({
  submitInternalSession: vi.fn(),
  getVehicles: vi.fn(),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { submitInternalSession, getVehicles } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { name: 'Test Advisor' } }) }))

import InternalSessionForm from './InternalSessionForm'

const vehicles = [
  { id: 1, vin: 'VF1AAA', mark: 'Dacia', model: 'Duster', registration_number: 'CJ01AAA', company_id: 11, odometer_km: 50000 },
  { id: 2, vin: 'VF1BBB', mark: 'Renault', model: 'Clio', registration_number: 'CJ02BBB', company_id: 12, odometer_km: 12000 },
]

function wrap(ui: React.ReactNode) {
  getVehicles.mockResolvedValue({ vehicles })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('InternalSessionForm embedded mode', () => {
  // Radix Select (Mașină picker) needs a couple of DOM APIs jsdom doesn't
  // implement — opening the listbox / selecting an item would otherwise throw.
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
    window.HTMLElement.prototype.releasePointerCapture = vi.fn()
  })

  it('renders a Cancel affordance wired to onCancel when embedded', async () => {
    const onCancel = vi.fn()
    wrap(<InternalSessionForm embedded onCancel={onCancel} onDone={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /înapoi/i }))
    expect(onCancel).toHaveBeenCalled()
  })

  it('prefills Șofer with the current user name', async () => {
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    expect(await screen.findByTestId('internal-driver')).toHaveValue('Test Advisor')
  })

  it('seeds the departure datetime from initialDeparture', async () => {
    wrap(<InternalSessionForm embedded initialDeparture="2026-08-19T09:00" onCancel={vi.fn()} onDone={vi.fn()} />)
    expect(await screen.findByTestId('internal-departure')).toHaveValue('2026-08-19T09:00')
  })

  it('flags the missing fields and blocks submit until valid', async () => {
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    await screen.findByTestId('internal-driver')
    fireEvent.click(screen.getByRole('button', { name: /creează sesiunea/i }))
    expect(await screen.findByText('Alege mașina.')).toBeInTheDocument()
    expect(submitInternalSession).not.toHaveBeenCalled()
  })

  it('picking a car auto-derives company_id and pre-fills KM plecare from the odometer', async () => {
    submitInternalSession.mockResolvedValue({ success: true, contract: { id: 5, contract_id: 'INT-1' } })
    const onDone = vi.fn()
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={onDone} />)
    await screen.findByTestId('internal-driver')

    fireEvent.click(screen.getByTestId('internal-vehicle'))
    fireEvent.click(await screen.findByText(/Renault Clio/))
    expect(await screen.findByTestId('internal-km')).toHaveValue(12000)

    // Set BOTH departure and return explicitly (return must stay >= departure,
    // else quickSessionError blocks the submit — the default return is seeded
    // from the real "now" at mount, which a fixed departure could precede).
    fireEvent.change(screen.getByTestId('internal-departure'), { target: { value: '2026-08-19T09:00' } })
    fireEvent.change(screen.getByTestId('internal-return'), { target: { value: '2026-08-19T10:00' } })
    fireEvent.click(screen.getByRole('button', { name: /creează sesiunea/i }))

    await waitFor(() => expect(submitInternalSession).toHaveBeenCalledWith(expect.objectContaining({
      is_internal: true,
      company_id: 12,
      vin: 'VF1BBB',
      advisor_name: 'Test Advisor',
      departure_datetime: '2026-08-19T09:00',
      odometer_start: 12000,
    })))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ id: 5, contract_id: 'INT-1' }))
  })

  it('surfaces a backend 409 (locked_out) error inline', async () => {
    const { ApiError } = await import('@/api/client')
    submitInternalSession.mockRejectedValue(new ApiError(409, { error: 'Mașină blocată în parcul auto', locked_out: true }))
    wrap(<InternalSessionForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    await screen.findByTestId('internal-driver')

    fireEvent.click(screen.getByTestId('internal-vehicle'))
    fireEvent.click(await screen.findByText(/Dacia Duster/))
    fireEvent.click(screen.getByRole('button', { name: /creează sesiunea/i }))

    expect(await screen.findByText('Mașină blocată în parcul auto')).toBeInTheDocument()
  })
})
