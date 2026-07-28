import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const pad = (n: number) => String(n).padStart(2, '0')
const now = new Date()
const todayIso = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T10:00`

const { getContracts, getVehicles } = vi.hoisted(() => ({ getContracts: vi.fn(), getVehicles: vi.fn() }))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getContracts, getVehicles } }))

import DrivingCalendar from './DrivingCalendar'

getContracts.mockResolvedValue({
  contracts: [
    { id: 11, status: 'FILLED', td_status: 'driving', vin: 'VF1', client_name: 'Ion Pop', departure_datetime: todayIso, km_start: 100 },
  ], total: 1, page: 1, per_page: 1000,
})
getVehicles.mockResolvedValue({ vehicles: [{ vin: 'VF1', mark: 'Volvo', model: 'XC40' }] })

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DrivingCalendar', () => {
  it('offers Day/Week/Month views and shows today’s session in the default Week view', async () => {
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Zi' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Săptămână' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Lună' })).toBeInTheDocument()
    expect(await screen.findByText('Ion Pop')).toBeInTheDocument()   // in this week
  })

  it('switches to Month view (weekday grid)', async () => {
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} />)
    await screen.findByText('Ion Pop')
    fireEvent.click(screen.getByRole('button', { name: 'Lună' }))
    expect(screen.getByText('Lu')).toBeInTheDocument()   // Monday-first weekday header
  })

  it('tapping a driving session opens the return overlay via onReturn', async () => {
    const onReturn = vi.fn()
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={onReturn} />)
    fireEvent.click(await screen.findByText('Ion Pop'))
    expect(onReturn).toHaveBeenCalledWith(11)
  })
})
