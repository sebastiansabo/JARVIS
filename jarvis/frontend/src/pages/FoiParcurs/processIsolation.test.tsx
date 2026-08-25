import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Broad foiParcursApi mock — every mount-time getter returns a benign shape so
// the tabs render without network. Call args are asserted where relevant.
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getContracts: vi.fn().mockResolvedValue({ contracts: [], total: 0, page: 1, per_page: 500 }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  listRouteSheets: vi.fn().mockResolvedValue({ sheets: [] }),
  getCompanies: vi.fn().mockResolvedValue({ companies: [] }),
  getKmConfigs: vi.fn().mockResolvedValue({ configs: [] }),
  getLockoutReasons: vi.fn().mockResolvedValue({ reasons: [] }),
  getArchiveReasons: vi.fn().mockResolvedValue({ reasons: [] }),
  getContractPdfUrl: (id: number) => `/pdf/${id}`,
  getSessionImportTemplateUrl: (id: number) => `/template/${id}`,
} }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { role_name: 'admin' } }) }))
// ContractConfigSection is the Service-only settings block — stub it so we can
// assert its presence/absence per context without its own API.
vi.mock('./ContractConfigSection', () => ({ default: () => <div data-testid="contract-config-section" /> }))

import { ContractsTab, SettingsTab, RoutesSettings } from './index'
import { foiParcursApi } from '@/api/foiParcurs'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ContractsTab (Foi de Parcurs) — document_type gating', () => {
  beforeEach(() => { vi.mocked(foiParcursApi.getContracts).mockClear(); vi.mocked(foiParcursApi.getVehicles).mockClear() })

  it('scopes contracts + vehicles to service when documentType="service"', async () => {
    wrap(<ContractsTab companyId={11} documentType="service" />)
    await waitFor(() => expect(foiParcursApi.getContracts).toHaveBeenCalled())
    expect(foiParcursApi.getContracts).toHaveBeenCalledWith(expect.objectContaining({ document_type: 'service' }))
    expect(foiParcursApi.getVehicles).toHaveBeenCalledWith(false, 'service')
  })

  it('defaults to sales scope when documentType is omitted', async () => {
    wrap(<ContractsTab companyId={11} />)
    await waitFor(() => expect(foiParcursApi.getContracts).toHaveBeenCalled())
    expect(foiParcursApi.getContracts).toHaveBeenCalledWith(expect.objectContaining({ document_type: 'sales' }))
    expect(foiParcursApi.getVehicles).toHaveBeenCalledWith(false, 'sales')
  })
})

describe('SettingsTab — strict Vânzări / Mașini de curtoazie split', () => {
  it('Vânzări shows general settings and hides the Service contract setup', async () => {
    wrap(<SettingsTab documentType="sales" />)
    expect(await screen.findByText(/Route KM Limits per Company/i)).toBeInTheDocument()
    expect(screen.queryByTestId('contract-config-section')).not.toBeInTheDocument()
  })

  it('Mașini de curtoazie shows the Service contract setup and hides the general KM limits', async () => {
    wrap(<SettingsTab documentType="service" />)
    expect(await screen.findByTestId('contract-config-section')).toBeInTheDocument()
    expect(screen.queryByText(/Route KM Limits per Company/i)).not.toBeInTheDocument()
  })
})

describe('RoutesSettings — context-aware section', () => {
  it('renders the itinerary/company-config header in sales', () => {
    wrap(<RoutesSettings companies={[{ id: 11, company: 'PREMIUM' }]} documentType="sales" />)
    expect(screen.getByText(/Itinerary Routes per Company/i)).toBeInTheDocument()
    expect(screen.queryByText(/Politică implicită mașini de curtoazie/i)).not.toBeInTheDocument()
  })

  it('renders the courtesy default-policy header in service', () => {
    wrap(<RoutesSettings companies={[{ id: 11, company: 'PREMIUM' }]} documentType="service" />)
    expect(screen.getByText(/Mașini de curtoazie — politică companie/i)).toBeInTheDocument()
    expect(screen.queryByText(/Itinerary Routes per Company/i)).not.toBeInTheDocument()
  })
})
