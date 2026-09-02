import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

// Ratate (td_status='missed') sessions must not appear in the Foi de Parcurs
// route sheet — they're archived, not documented.
vi.mock('@/api/foiParcurs', () => {
  const now = new Date()
  const Y = now.getFullYear()
  const M = now.getMonth() + 1
  const created = `${Y}-${String(M).padStart(2, '0')}-05T10:00:00`
  const c = (id: number, vin: string, td_status: string) => ({
    id, vin, client_name: `Client ${id}`, td_status,
    km_start: id * 100, km_end: id * 100 + 40,
    year: Y, month: M, created_at: created,
  })
  // One car with a real (completed) trip, one car whose only trip is a no-show.
  const CONTRACTS = [c(1, 'VDROVE', 'complete'), c(2, 'VMISS', 'missed')]
  const VEHICLES = [
    { vin: 'VDROVE', mark: 'MG', model: 'MG ZS Driven', brand: 'MG Motor', is_active: true, company_id: 9 },
    { vin: 'VMISS', mark: 'MG', model: 'MG3 NoShow', brand: 'MG Motor', is_active: true, company_id: 9 },
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

describe('ContractsTab (Foi de Parcurs) — Ratate excluded', () => {
  beforeEach(() => vi.clearAllMocks())

  it('hides a car whose only session this month is a no-show (Ratat)', async () => {
    wrap(<ContractsTab companyId={9} brand="MG Motor" documentType="sales" />)
    await waitFor(() => expect(screen.getByText('MG ZS Driven')).toBeInTheDocument())
    // The no-show car has nothing to document → not listed.
    expect(screen.queryByText('MG3 NoShow')).not.toBeInTheDocument()
  })
})
