import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 1, name: 'A' }, isLoading: false }) }))
vi.mock('@/api/buyback', () => ({ buybackApi: {
  getLookupOptions: () => Promise.resolve({}),
  getVinHistory: () => Promise.resolve({ history: [] }),
  getCompanies: () => Promise.resolve({ companies: [] }),
  searchCrmClients: () => Promise.resolve({ clients: [] }),
} }))

import BuyBackForm from './BuyBackForm'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}><MemoryRouter><BuyBackForm /></MemoryRouter></QueryClientProvider>
  )
}

describe('Date vânzător sub-section', () => {
  it('shows the section heading + an always-present address field', async () => {
    wrap()
    expect(await screen.findByText('Date vânzător')).toBeInTheDocument()
    expect(screen.getByText(/Adresă/)).toBeInTheDocument()
  })
})
