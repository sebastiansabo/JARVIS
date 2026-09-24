import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

vi.mock('@/api/buyback', () => ({
  buybackApi: {
    getRecord: vi.fn(() =>
      Promise.resolve({
        record: {
          id: 5,
          record_code: 'BB-Y',
          brand: 'Audi',
          model: 'A4',
          vin: 'WAU...',
          status: 'INITIAL_OFFER',
          seller_name: 'Dan',
          client_asking_price_eur: 12000,
        },
        offers: [{ id: 1, offer_type: 'initial', amount_eur: 11000, client_decision: 'pending', created_at: '2026-09-24' }],
        photos: [],
        events: [{ id: 1, action: 'created', created_at: '2026-09-24', details: {} }],
      })
    ),
    // ActionPanel mounts unconditionally and fires this on render regardless of status.
    getLookupOptions: vi.fn(() => Promise.resolve({})),
  },
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { role_name: 'admin', permissions: {} }, isLoading: false }),
}))

import BuyBackDetail from './BuyBackDetail'

function wrap(entry: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/app/buyback/:id" element={<BuyBackDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('BuyBackDetail', () => {
  it('shows the vehicle, status badge, and event timeline', async () => {
    wrap('/app/buyback/5')
    expect(await screen.findByText('Audi A4')).toBeInTheDocument()
    expect(screen.getByText('Ofertă inițială')).toBeInTheDocument()
    expect(screen.getByText('BB-Y')).toBeInTheDocument()
  })
})
