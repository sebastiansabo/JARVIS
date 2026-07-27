import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// vi.mock factories are hoisted above top-level consts, so any values they
// reference must be wrapped in vi.hoisted() (Vitest 3.2.7).
const { getContracts, getVehicles, getContractPdfUrl } = vi.hoisted(() => ({
  getContracts: vi.fn().mockResolvedValue({
    contracts: [
      { id: 11, status: 'FILLED', td_status: 'driving', vin: 'VF1', client_name: 'Ion', departure_datetime: '2026-07-27T10:00', km_start: 100, route_type: 'TD' },
      { id: 12, status: 'COMPLETED', td_status: 'complete', vin: 'VF2', client_name: 'Ana', departure_datetime: '2026-07-20T10:00', km_start: 200, route_type: 'TD' },
    ],
    total: 2,
    page: 1,
    per_page: 1000,
  }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  // Row rendering also builds a "Descarcă PDF" link (for non-PENDING/PLANNED
  // rows) via this URL-builder — it's called synchronously during render,
  // so it must be present even though this test doesn't assert on it.
  getContractPdfUrl: vi.fn((id: number, type: string) => `/api/foi/contracts/${id}/pdf/${type}`),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getContracts, getVehicles, getContractPdfUrl } }))
// SessionsTab reads the current user via useAuthStore(selector) for the
// isAdmin gate — stub it to an anonymous (non-admin) user so no zustand
// store setup is required.
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: { user: null }) => unknown) => sel({ user: null }) }))

import { SessionsTab } from './index'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SessionsTab Retur action', () => {
  it('shows a Retur link for a driving session, not for a completed one', async () => {
    wrap(<SessionsTab companyId={11} brand="" />)
    const returLinks = await screen.findAllByRole('link', { name: /retur/i })
    // exactly one Retur (for the driving row #11), pointing at its return route
    expect(returLinks).toHaveLength(1)
    expect(returLinks[0]).toHaveAttribute('href', '/app/foi-parcurs/test-drive/11/return')
  })
})
