import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi, test, expect } from 'vitest'
import { RevenuesTab } from './RevenuesTab'

// Mirror of CostsTab's RON+EUR+curs display, for revenues (prop-based).
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/api/carpark', () => ({
  carparkApi: { createRevenue: vi.fn(), updateRevenue: vi.fn(), deleteRevenue: vi.fn() },
}))

const revenues = [
  { id: 1, vehicle_id: 1, revenue_type: 'sale', description: '', amount: 5000, currency: 'RON', vat_amount: 950, exchange_rate_eur: 5.0, amount_eur: 1000, vat_amount_eur: 190, invoice_number: null, invoice_id: null, client_name: 'X', date: '2025-11-17', created_by: null, created_at: '' },
  { id: 2, vehicle_id: 1, revenue_type: 'commission', description: '', amount: 200, currency: 'EUR', vat_amount: 0, exchange_rate_eur: null, amount_eur: 200, vat_amount_eur: 0, invoice_number: null, invoice_id: null, client_name: 'Y', date: '2025-11-18', created_by: null, created_at: '' },
]

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <RevenuesTab vehicleId={1} revenues={revenues as never} canEdit />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('a RON revenue shows RON prominent, the EUR equivalent + curs; subtotal is EUR', () => {
  renderTab()
  expect(screen.getAllByText('Vânzare').length).toBeGreaterThan(0)  // Tip badge + breakdown chip
  expect(screen.getByText(/5\.000,00/)).toBeInTheDocument()            // original RON net (unique)
  expect(screen.getByText(/curs 5,0000/)).toBeInTheDocument()          // the BNR rate
  expect(screen.getAllByText(/1\.000,00/).length).toBeGreaterThan(0)   // EUR equivalent
  expect(screen.getAllByText(/1\.200,00/).length).toBeGreaterThan(0)   // EUR subtotal (1000+200)
  expect(screen.queryByText(/5\.200,00/)).toBeNull()                   // not the raw mixed sum
})
