import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { getLockEvents, getLockoutReasons } = vi.hoisted(() => ({
  getLockEvents: vi.fn(),
  getLockoutReasons: vi.fn(),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getLockEvents, getLockoutReasons } }))

import { VehicleLockHistory } from './VehicleLockHistory'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('VehicleLockHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getLockoutReasons.mockResolvedValue({
      reasons: [{ id: 1, slug: 'service', label: 'În service', sort_order: 1, is_active: true }],
    })
  })

  it('renders lock and unlock rows with actor names, reason label and note', async () => {
    getLockEvents.mockResolvedValue({
      events: [
        { id: 2, action: 'unlock', category: null, note: null, actor_id: 3, actor_name: 'Ion Pop', created_at: '2026-08-28T09:12:00+00:00' },
        { id: 1, action: 'lock', category: 'service', note: 'bară avariată', actor_id: 1, actor_name: 'Sebastian Sabo', created_at: '2026-08-31T14:05:00+00:00' },
      ],
    })
    wrap(<VehicleLockHistory vehicleId={7} />)
    expect(await screen.findByText('Deblocat')).toBeInTheDocument()
    expect(screen.getByText('Blocat')).toBeInTheDocument()
    expect(screen.getByText(/Sebastian Sabo/)).toBeInTheDocument()
    expect(screen.getByText(/Ion Pop/)).toBeInTheDocument()
    expect(screen.getByText(/În service/)).toBeInTheDocument()
    expect(screen.getByText(/bară avariată/)).toBeInTheDocument()
  })

  it('shows an empty-state when there are no events', async () => {
    getLockEvents.mockResolvedValue({ events: [] })
    wrap(<VehicleLockHistory vehicleId={7} />)
    expect(await screen.findByText(/Fără istoric/)).toBeInTheDocument()
  })
})
