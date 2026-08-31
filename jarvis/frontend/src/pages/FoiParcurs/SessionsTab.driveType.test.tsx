import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// One external (client) TD session — the case the cleaning tool fixes.
const { getContracts, getVehicles, getContractPdfUrl, setDriveType } = vi.hoisted(() => ({
  getContracts: vi.fn().mockResolvedValue({
    contracts: [
      { id: 42, status: 'FILLED', td_status: 'driving', route_type: 'TD', vin: 'VF9', company_name: 'AutoWorld', client_name: 'Ion', is_internal: false, departure_datetime: '2026-07-27T10:00', km_start: 100 },
    ], total: 1, page: 1, per_page: 1000,
  }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  getContractPdfUrl: vi.fn(() => '/pdf'),
  setDriveType: vi.fn().mockResolvedValue({ success: true, contract: { id: 42, is_internal: true } }),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getContracts, getVehicles, getContractPdfUrl, setDriveType } }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

let mockUser: { role_name?: string } | null = null
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: mockUser }) }))

import { SessionsTab } from './index'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('SessionsTab drive-type cleaning action', () => {
  beforeEach(() => {
    setDriveType.mockClear()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('lets an admin mark an external session as internal', async () => {
    mockUser = { role_name: 'admin' }
    wrap(<SessionsTab companyId={0} brand="" />)
    // Expand the row to reveal the footer correction actions.
    fireEvent.click(await screen.findByText('AutoWorld'))
    fireEvent.click(await screen.findByRole('button', { name: /marchează ca intern/i }))
    await waitFor(() => expect(setDriveType).toHaveBeenCalledWith(42, true))
  })

  it('hides the action from non-admins', async () => {
    mockUser = { role_name: 'consilier' }
    wrap(<SessionsTab companyId={0} brand="" />)
    fireEvent.click(await screen.findByText('AutoWorld'))
    // Footer renders (Istoric is visible to everyone) but the admin action does not.
    await screen.findByRole('button', { name: /istoric/i })
    expect(screen.queryByRole('button', { name: /marchează ca intern/i })).toBeNull()
  })
})
