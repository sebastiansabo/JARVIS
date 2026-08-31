import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

// The foaie is gated to the actual DRIVE month (departure_datetime), not the
// created date. A session created this month but driven on the 1st of next month
// belongs to next month and must not appear in the current month's foaie.
vi.mock('@/api/foiParcurs', () => {
  const now = new Date()
  const Y = now.getFullYear()
  const M = now.getMonth() + 1 // 1-based current month
  const iso = (y: number, m: number, d: number) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}T10:00:00`
  const thisMonthDrive = iso(Y, M, 15)
  // 1st of next month (roll over December → January).
  const nY = M === 12 ? Y + 1 : Y
  const nM = M === 12 ? 1 : M + 1
  const nextMonthDrive = iso(nY, nM, 1)
  const createdThisMonth = iso(Y, M, 28)

  const CONTRACTS = [
    { id: 1, vin: 'VNOW', client_name: 'This Month', td_status: 'complete', is_internal: false,
      km_start: 100, km_end: 140, departure_datetime: thisMonthDrive, created_at: createdThisMonth },
    // Created this month, but DROVE on the 1st of next month → gated out.
    { id: 2, vin: 'VNEXT', client_name: 'Next Month', td_status: 'complete', is_internal: false,
      km_start: 200, km_end: 240, departure_datetime: nextMonthDrive, created_at: createdThisMonth },
  ]
  const VEHICLES = [
    { vin: 'VNOW', mark: 'MG', model: 'MG ZS ThisMonth', brand: 'MG Motor', is_active: true, company_id: 9 },
    { vin: 'VNEXT', mark: 'MG', model: 'MG3 NextMonth', brand: 'MG Motor', is_active: true, company_id: 9 },
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

describe('ContractsTab (Foi de Parcurs) — month gated by drive date', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the drive in the current month and gates out the 1st-of-next-month drive', async () => {
    wrap(<ContractsTab companyId={9} brand="MG Motor" documentType="sales" />)
    await waitFor(() => expect(screen.getByText('MG ZS ThisMonth')).toBeInTheDocument())
    expect(screen.queryByText('MG3 NextMonth')).not.toBeInTheDocument()
  })
})
