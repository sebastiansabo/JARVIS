import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/buyback', () => ({
  buybackApi: {
    listRecords: vi.fn(() =>
      Promise.resolve({
        records: [
          {
            id: 1,
            record_code: 'BB-X',
            brand: 'BMW',
            model: '320d',
            vin: 'WBA...',
            status: 'BOUGHT',
            seller_name: 'Ion',
            advisor_name: 'Maria',
            client_asking_price_eur: 10000,
            purchase_price_eur: 9500,
            created_at: '2026-09-24',
          },
        ],
        total: 1,
        page: 1,
        per_page: 25,
      })
    ),
  },
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { role_name: 'Admin', can_access_buyback: true, permissions: {} }, isLoading: false }),
}))

import BuyBack from './index'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('BuyBack list page', () => {
  it('renders a record row with its status badge', async () => {
    wrap(<BuyBack />)
    expect(await screen.findByText('BMW 320d')).toBeInTheDocument()
    expect(screen.getByText('Achiziționat')).toBeInTheDocument()
    // purchase_price_eur (9500) renders in the "Preț achiziție €" column, ro-RO formatted
    expect(screen.getByText((9500).toLocaleString('ro-RO'))).toBeInTheDocument()
  })
})
