import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

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
  getAllBrands: vi.fn().mockResolvedValue({ brands: [] }),
} }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { role_name: 'admin' } }) }))
// ContractConfigSection is the Service-only settings block — stub it so we can
// assert its presence/absence per context without its own API.
vi.mock('./ContractConfigSection', () => ({ default: () => <div data-testid="contract-config-section" /> }))

import { ContractsTab, SettingsTab, RoutesSettings, VehicleFormFields } from './index'
import { foiParcursApi } from '@/api/foiParcurs'

// Minimal VehicleFormValue for the pool-lock tests (only the string fields the
// form binds to; document_type varies per test).
const vehicleForm = (documentType: 'sales' | 'service') => ({
  car_id: '', vin: '', registration_number: '', mark: '', model: '', color: '',
  fuel_type: 'Diesel', fuel_tank_capacity_liters: 50, battery_capacity_kwh: 0,
  odometer_km: '', norma_combustibil: '', norma_energie: '', category: '', company_id: '',
  document_type: documentType,
  svc_tariff_eur_day: '', svc_tariff_eur_month: '', svc_km_included_day: '',
  svc_extra_km_eur: '', svc_deposit_eur: '', svc_franchise_eur: '',
  vignette_valid_until: '', itp_valid_until: '', insurance_valid_until: '',
  insurance_doc: '', talon_doc: '', civ_doc: '', registration_doc: '', offer_doc: '',
}) as never

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
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

describe('VehicleFormFields — Parc/Tip document locked to the active gate', () => {
  it('when lockDocType, the pool is fixed to the gate (service) and not editable', () => {
    wrap(<VehicleFormFields value={vehicleForm('service')} onChange={vi.fn()} brandLabel="—" companies={[]} lockDocType />)
    // Helper reads the current park, and the courtesy value is Mașini de curtoazie.
    expect(screen.getByText(/Determinat de parcul curent \(Mașini de curtoazie\)/i)).toBeInTheDocument()
  })

  it('without lockDocType the pool selector stays editable (no locked hint)', () => {
    wrap(<VehicleFormFields value={vehicleForm('sales')} onChange={vi.fn()} brandLabel="—" companies={[]} />)
    expect(screen.queryByText(/Determinat de parcul curent/i)).not.toBeInTheDocument()
  })
})
