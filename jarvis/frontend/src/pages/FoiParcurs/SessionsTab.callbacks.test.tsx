import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { getContracts, getVehicles, getContractPdfUrl } = vi.hoisted(() => ({
  getContracts: vi.fn().mockResolvedValue({
    contracts: [
      { id: 11, status: 'FILLED', td_status: 'driving', route_type: 'TD', vin: 'VF1', client_name: 'Ion', departure_datetime: '2026-07-27T10:00', km_start: 100 },
      { id: 20, status: 'PLANNED', td_status: 'driving', route_type: 'TD', vin: 'VF3', client_name: 'Dan', departure_datetime: '2026-07-28T10:00', km_start: 300 },
    ], total: 2, page: 1, per_page: 1000,
  }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  getContractPdfUrl: vi.fn(() => '/pdf'),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getContracts, getVehicles, getContractPdfUrl } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: null }) }))

import { SessionsTab } from './index'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('SessionsTab activate/return callbacks', () => {
  it('calls onReturn instead of navigating when provided', async () => {
    const onReturn = vi.fn()
    wrap(<SessionsTab companyId={11} brand="" onReturn={onReturn} />)
    const retur = await screen.findByRole('button', { name: /retur/i })
    // callback mode renders a <button>, NOT an <a href>
    expect(screen.queryByRole('link', { name: /retur/i })).toBeNull()
    fireEvent.click(retur)
    expect(onReturn).toHaveBeenCalledWith(11)
  })

  it('calls onActivate instead of navigating when provided', async () => {
    const onActivate = vi.fn()
    wrap(<SessionsTab companyId={11} brand="" onActivate={onActivate} />)
    fireEvent.click(await screen.findByRole('button', { name: /începe sesiunea/i }))
    expect(onActivate).toHaveBeenCalledWith(20)
  })
})
