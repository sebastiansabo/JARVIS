import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

// Internal (company) drives are not listed on the client Foaie de Parcurs — their
// KM surfaces as a gap between client drives instead.
vi.mock('@/api/foiParcurs', () => {
  const now = new Date()
  const Y = now.getFullYear()
  const M = now.getMonth() + 1
  const created = `${Y}-${String(M).padStart(2, '0')}-05T10:00:00`
  const c = (id: number, vin: string, is_internal: boolean) => ({
    id, vin, client_name: `Client ${id}`, td_status: 'complete', is_internal,
    km_start: id * 100, km_end: id * 100 + 40,
    year: Y, month: M, created_at: created,
  })
  // One car with a client drive, one car whose only drive is internal.
  const CONTRACTS = [c(1, 'VCLIENT', false), c(2, 'VINT', true)]
  const VEHICLES = [
    { vin: 'VCLIENT', mark: 'MG', model: 'MG ZS Client', brand: 'MG Motor', is_active: true, company_id: 9 },
    { vin: 'VINT', mark: 'MG', model: 'MG3 InternalOnly', brand: 'MG Motor', is_active: true, company_id: 9 },
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

describe('ContractsTab (Foi de Parcurs) — internal drives excluded', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not list a car whose only session this month is internal', async () => {
    wrap(<ContractsTab companyId={9} brand="MG Motor" documentType="sales" />)
    await waitFor(() => expect(screen.getByText('MG ZS Client')).toBeInTheDocument())
    expect(screen.queryByText('MG3 InternalOnly')).not.toBeInTheDocument()
  })
})
