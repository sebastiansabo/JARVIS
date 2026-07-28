import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { getContracts, getVehicles, getContractPdfUrl, discardTestDrive } = vi.hoisted(() => ({
  getContracts: vi.fn().mockResolvedValue({
    contracts: [
      { id: 11, status: 'FILLED', td_status: 'driving', vin: 'VF1', client_name: 'Ion Pop', advisor_name: 'Cons A', departure_datetime: '2026-07-27T10:00', km_start: 100 },
      { id: 20, status: 'PLANNED', vin: 'VF3', client_name: 'Dan Ile', advisor_name: 'Cons B', departure_datetime: '2026-07-28T09:00', km_start: 300 },
      { id: 30, status: 'COMPLETED', td_status: 'complete', vin: 'VF2', client_name: 'Ana Ban', advisor_name: 'Cons C', departure_datetime: '2026-07-20T10:00', km_start: 200, km_end: 260 },
    ], total: 3, page: 1, per_page: 1000,
  }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [{ vin: 'VF1', mark: 'Volvo', model: 'XC40' }] }),
  getContractPdfUrl: vi.fn((id: number) => `/pdf/${id}`),
  discardTestDrive: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getContracts, getVehicles, getContractPdfUrl, discardTestDrive } }))

import DrivingSessionsList from './DrivingSessionsList'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DrivingSessionsList', () => {
  beforeEach(() => { getContracts.mockClear(); getVehicles.mockClear() })

  it('shows active sessions (driving + planned), hides finalized behind Arhivă', async () => {
    wrap(<DrivingSessionsList companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} />)
    expect(await screen.findByText('Ion Pop')).toBeInTheDocument()   // driving
    expect(screen.getByText('Dan Ile')).toBeInTheDocument()         // planned
    expect(screen.queryByText('Ana Ban')).not.toBeInTheDocument()   // finalized -> archived
    // vehicle name is joined from the vehicles map (mark + model)
    expect(screen.getByText('Volvo XC40')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Arhivă' }))
    expect(await screen.findByText('Ana Ban')).toBeInTheDocument()
    expect(screen.queryByText('Ion Pop')).not.toBeInTheDocument()
  })

  it('Retur calls onReturn (driving) and Începe calls onActivate (planned)', async () => {
    const onReturn = vi.fn(); const onActivate = vi.fn()
    wrap(<DrivingSessionsList companyId={11} brand="" onActivate={onActivate} onReturn={onReturn} />)
    fireEvent.click(await screen.findByRole('button', { name: /completează retur/i }))
    expect(onReturn).toHaveBeenCalledWith(11)
    fireEvent.click(screen.getByRole('button', { name: /începe sesiunea/i }))
    expect(onActivate).toHaveBeenCalledWith(20)
  })

  it('filters by search', async () => {
    wrap(<DrivingSessionsList companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} />)
    await screen.findByText('Ion Pop')
    fireEvent.change(screen.getByPlaceholderText(/caută/i), { target: { value: 'dan' } })
    expect(screen.queryByText('Ion Pop')).not.toBeInTheDocument()
    expect(screen.getByText('Dan Ile')).toBeInTheDocument()
  })

  it('expands a card to reveal details (VIN)', async () => {
    wrap(<DrivingSessionsList companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} />)
    const name = await screen.findByText('Ion Pop')
    expect(screen.queryByText('VF1')).not.toBeInTheDocument() // vin only shown when expanded
    fireEvent.click(name)
    expect(screen.getByText('VF1')).toBeInTheDocument()
  })
})
