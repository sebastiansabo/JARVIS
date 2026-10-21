import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/buyback', () => ({
  buybackApi: {
    getContractBrands: () => Promise.resolve({ brands: [{ id: 7, name: 'Audi' }] }),
    listContractTemplates: () => Promise.resolve({
      templates: [{
        id: 1, company_id: 11, brand_id: 7, document_type: 'purchase',
        title: 'Achizitie Audi', body_template: 'Vanzator {seller_name}',
        general_conditions: '', is_active: true,
      }],
    }),
    putContractTemplate: vi.fn(() => Promise.resolve({ template: {} })),
  },
}))

import BuyBackContractsSection from './BuyBackContractsSection'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('BuyBackContractsSection', () => {
  it('renders Contracte with a per-brand card pre-filled from the template', async () => {
    wrap(<BuyBackContractsSection companyId={11} />)
    expect(await screen.findByText('Contracte')).toBeInTheDocument()
    // the purchase card for Audi is pre-filled with the seeded title
    expect(await screen.findByDisplayValue('Achizitie Audi')).toBeInTheDocument()
    expect(screen.getAllByText('Salvează').length).toBeGreaterThan(0)
  })
})
