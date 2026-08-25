import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [] }),
  getContractConfigs: vi.fn().mockResolvedValue({ configs: [] }),
} }))

import ContractConfigSection from './ContractConfigSection'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ContractConfigSection — token cheat-sheet', () => {
  // The cheat-sheet must list every placeholder the backend renderer supports
  // (jarvis/foi_parcurs/services/contract_template.py PLACEHOLDERS) — it had
  // drifted to only the first 15 of 38.
  it('lists the full backend placeholder set, grouped', () => {
    wrap(<ContractConfigSection />)
    // A representative token from each newly-added group must be present…
    expect(screen.getByText('{client_cui}')).toBeInTheDocument()          // client identity
    expect(screen.getByText('{vehicle_model}')).toBeInTheDocument()       // vehicle
    expect(screen.getByText('{company_iban}')).toBeInTheDocument()        // company legal
    expect(screen.getByText('{dealer_phone}')).toBeInTheDocument()        // company contact
    expect(screen.getByText('{svc_total_eur}')).toBeInTheDocument()       // rental pricing
    expect(screen.getByText('{svc_garantie_eur}')).toBeInTheDocument()
    // …and the original tokens still render.
    expect(screen.getByText('{client_name}')).toBeInTheDocument()
    expect(screen.getByText('{general_conditions}')).toBeInTheDocument()
  })
})
