import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

// vi.mock factories are hoisted above the file, so the fixture is built inside.
// The Foi de Parcurs tab defaults its period filter to the current month, so the
// contracts are stamped with the current month — keeps the test date-independent.
vi.mock('@/api/foiParcurs', () => {
  const now = new Date()
  const Y = now.getFullYear()
  const M = now.getMonth() + 1
  const created = `${Y}-${String(M).padStart(2, '0')}-05T10:00:00`
  const c = (id: number, vin: string) => ({
    id, vin, client_name: `Client ${id}`,
    km_start: id * 100, km_end: id * 100 + 40,
    year: Y, month: M, created_at: created,
  })
  // Two MG cars (one archived) + one Mazda car, all with a trip this month.
  const CONTRACTS = [c(1, 'VMG'), c(2, 'VMGA'), c(3, 'VMZ')]
  const VEHICLES = [
    { vin: 'VMG', mark: 'MG', model: 'MG ZS Active', brand: 'MG Motor', is_active: true, company_id: 9 },
    { vin: 'VMGA', mark: 'MG', model: 'MG3 Archived', brand: 'MG Motor', is_active: false, company_id: 9 },
    { vin: 'VMZ', mark: 'Mazda', model: 'CX-60 Mazda', brand: 'Mazda', is_active: true, company_id: 9 },
  ]
  return { foiParcursApi: {
    getContracts: vi.fn().mockResolvedValue({ contracts: CONTRACTS, total: CONTRACTS.length, page: 1, per_page: 500 }),
    getVehicles: vi.fn().mockResolvedValue({ vehicles: VEHICLES }),
    listRouteSheets: vi.fn().mockResolvedValue({ sheets: [] }),
    getRouteSheetXlsxUrl: (vin: string) => `/xlsx/${vin}`,
    getRouteSheetContractsZipUrl: (vin: string) => `/zip/${vin}`,
    getSessionImportTemplateUrl: (id: number) => `/template/${id}`,
    correctSession: vi.fn(),
  } }
})
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { role_name: 'admin' } }) }))

import { ContractsTab } from './index'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('ContractsTab (Foi de Parcurs) — make filter + archived badge', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows only the selected make, including its archived cars (badged)', async () => {
    wrap(<ContractsTab companyId={9} brand="MG Motor" documentType="sales" />)
    // Both MG cars appear — the archived one is not dropped by the filter…
    await waitFor(() => expect(screen.getByText('MG ZS Active')).toBeInTheDocument())
    expect(screen.getByText('MG3 Archived')).toBeInTheDocument()
    // …and it's badged so it's distinguishable.
    expect(screen.getByText('Arhivat')).toBeInTheDocument()
    // The Mazda car is filtered out.
    expect(screen.queryByText('CX-60 Mazda')).not.toBeInTheDocument()
  })

  it('switches to Mazda when the make changes', async () => {
    wrap(<ContractsTab companyId={9} brand="Mazda" documentType="sales" />)
    await waitFor(() => expect(screen.getByText('CX-60 Mazda')).toBeInTheDocument())
    expect(screen.queryByText('MG ZS Active')).not.toBeInTheDocument()
    expect(screen.queryByText('MG3 Archived')).not.toBeInTheDocument()
  })

  it('shows every make when brand is empty (Service/rental context)', async () => {
    wrap(<ContractsTab companyId={9} brand="" documentType="sales" />)
    await waitFor(() => expect(screen.getByText('MG ZS Active')).toBeInTheDocument())
    expect(screen.getByText('CX-60 Mazda')).toBeInTheDocument()
  })
})
