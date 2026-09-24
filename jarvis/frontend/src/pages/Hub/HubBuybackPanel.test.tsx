import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/buyback', () => ({
  buybackApi: {
    listRecords: vi.fn(() => Promise.resolve({ records: [], total: 0, page: 1, per_page: 200 })),
  },
}))
vi.mock('@/pages/BuyBack/BuyBackForm', () => ({
  default: () => <div>mock-buyback-form</div>,
}))

let mockUser: Record<string, unknown> = {}
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: mockUser, isLoading: false }),
}))

import HubBuybackPanel from './HubBuybackPanel'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <HubBuybackPanel onBack={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('HubBuybackPanel create-button gating', () => {
  it('hides "Solicitare nouă" without buyback.record.create', async () => {
    mockUser = { role_name: 'user', permissions: {} }
    wrap()
    await screen.findByText('Nicio solicitare')
    expect(screen.queryByRole('button', { name: /solicitare nouă/i })).not.toBeInTheDocument()
  })

  it('shows "Solicitare nouă" with buyback.record.create', async () => {
    mockUser = { role_name: 'user', permissions: { 'buyback.record.create': true } }
    wrap()
    expect(await screen.findByRole('button', { name: /solicitare nouă/i })).toBeInTheDocument()
  })

  it('shows "Solicitare nouă" for admins regardless of permissions', async () => {
    mockUser = { role_name: 'admin', permissions: {} }
    wrap()
    expect(await screen.findByRole('button', { name: /solicitare nouă/i })).toBeInTheDocument()
  })
})
