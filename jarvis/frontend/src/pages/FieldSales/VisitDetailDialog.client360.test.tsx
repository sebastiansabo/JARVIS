import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: {
  getVisit: vi.fn().mockResolvedValue({ success: true, visit: {
    id: 9, kam_id: 3, client_id: 760, planned_date: '2026-08-04', visit_type: 'general', status: 'planned',
    client_name: 'ACME SRL', kam_name: 'George Pop',
  } }),
  getVisitTasks: vi.fn().mockResolvedValue({ success: true, tasks: [] }),
  updateVisit: vi.fn(),
} }))
import { VisitDetailDialog } from './VisitDetailDialog'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('VisitDetailDialog client360 link', () => {
  it('calls onOpenClient360 with the client id', async () => {
    const spy = vi.fn()
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} onOpenClient360={spy} />)
    fireEvent.click(await screen.findByRole('button', { name: /client 360/i }))
    expect(spy).toHaveBeenCalledWith(760)
  })
})
