import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getTodayVisits = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: {
    getTodayVisits: (...a: unknown[]) => getTodayVisits(...a),
    searchClients: vi.fn(), createVisit: vi.fn(),
    checkin: vi.fn(), checkout: vi.fn(), addNote: vi.fn(),
    getVisit: vi.fn(), getClient360: vi.fn(), refreshFiscal: vi.fn(),
  },
}))
// VisitDetailDialog is heavy; stub it for panel tests.
vi.mock('@/pages/FieldSales/VisitDetailDialog', () => ({
  VisitDetailDialog: ({ open, visitId }: { open: boolean; visitId: number | null }) =>
    open ? <div>detail:{visitId}</div> : null,
}))

import HubFieldSalesPanel from './HubFieldSalesPanel'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

const VISIT = {
  id: 9, kam_id: 3, client_id: 760, planned_date: '2026-08-04', planned_time: '13:30',
  visit_type: 'renewal_discussion', status: 'planned', client_name: 'DEMO Construct Grup SRL',
  kam_name: 'George Pop', renewal_score: 70, goals: 'Reinnoire',
}

describe('HubFieldSalesPanel', () => {
  beforeEach(() => { getTodayVisits.mockReset() })

  it('lists today visits and shows the quick-stat counts', async () => {
    getTodayVisits.mockResolvedValue({ success: true, visits: [VISIT], date: '2026-08-04' })
    wrap(<HubFieldSalesPanel />)
    expect(await screen.findByText('DEMO Construct Grup SRL')).toBeInTheDocument()
    // one planned visit -> "1" appears in the Planificate stat tile
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
  })

  it('shows the empty state when there are no visits', async () => {
    getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
    wrap(<HubFieldSalesPanel />)
    expect(await screen.findByText(/nicio vizit/i)).toBeInTheDocument()
  })
})
