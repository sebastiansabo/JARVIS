import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ScheduleBlockSection from './ScheduleBlockSection'
import { foiParcursApi } from '@/api/foiParcurs'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getLockoutReasons: vi.fn(() => Promise.resolve({ success: true, reasons: [{ id: 1, slug: 'service', label: 'În service', sort_order: 1, is_active: true }] })),
  getScheduledBlocks: vi.fn(() => Promise.resolve({ success: true, blocks: [] })),
  getVehicleConflicts: vi.fn(() => Promise.resolve({ success: true, conflicts: [{ id: 9, status: 'PLANNED', client_name: 'Ion', departure_datetime: '2026-09-02T10:00' }] })),
  createScheduledBlock: vi.fn(() => Promise.resolve({ success: true, block: { id: 1 } })),
  cancelScheduledBlock: vi.fn(),
} }))

const vehicle = { id: 3, vin: 'VIN1', mark: 'Audi', model: 'A4', registration_number: 'CJ01ABC' } as any

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={qc}><ScheduleBlockSection vehicle={vehicle} /></QueryClientProvider>)
}

describe('ScheduleBlockSection', () => {
  beforeEach(() => vi.clearAllMocks())
  it('shows overlap warning and sends allow_conflicts=true', async () => {
    setup()
    fireEvent.change(screen.getByLabelText('De la'), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByLabelText('Până la'), { target: { value: '2026-09-03' } })
    await waitFor(() => expect(screen.getByText(/se suprapun/i)).toBeInTheDocument())
    fireEvent.click(screen.getByText('Programează oricum'))
    await waitFor(() => expect(foiParcursApi.createScheduledBlock).toHaveBeenCalledWith(
      3, expect.objectContaining({ allow_conflicts: true, start_date: '2026-09-01', end_date: '2026-09-03' })))
  })
})
