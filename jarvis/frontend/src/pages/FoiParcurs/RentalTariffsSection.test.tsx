import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import RentalTariffsSection from './RentalTariffsSection'
import { foiParcursApi } from '@/api/foiParcurs'

vi.mock('@/api/foiParcurs', () => ({
  foiParcursApi: {
    getRentalIntervals: vi.fn(),
    getRentalCategories: vi.fn(),
    putRentalInterval: vi.fn(),
    deleteRentalInterval: vi.fn(),
    addRentalCategory: vi.fn(),
    putRentalCategory: vi.fn(),
    deleteRentalCategory: vi.fn(),
    setRentalPrice: vi.fn(),
  },
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('RentalTariffsSection', () => {
  beforeEach(() => {
    ;(foiParcursApi.getRentalIntervals as any).mockResolvedValue({
      success: true, intervals: [{ id: 1, label: '1-8 zile', min_days: 1, max_days: 8, sort_order: 0 }],
    })
    ;(foiParcursApi.getRentalCategories as any).mockResolvedValue({
      success: true, categories: [{ id: 7, name: 'SUV+', models_note: 'x', franchise_eur: 250, extra_km_eur: 0.25, sort_order: 0, is_active: true, prices: { 1: 33 } }],
    })
  })

  it('renders the category row and interval header', async () => {
    wrap(<RentalTariffsSection companyId={11} />)
    await waitFor(() => expect(screen.getByText('SUV+')).toBeInTheDocument())
    expect(screen.getByText('1-8 zile')).toBeInTheDocument()
    expect(screen.getByDisplayValue('33')).toBeInTheDocument()
  })
})
