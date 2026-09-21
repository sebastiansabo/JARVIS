import { render, screen, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi, test, expect } from 'vitest'
import VehicleForm from './VehicleForm'
import { carparkApi } from '@/api/carpark'

vi.mock('@/api/carpark', () => ({
  carparkApi: {
    getLocations: () => Promise.resolve({ locations: [] }),
    getVehicle: vi.fn(() => Promise.resolve({ vehicle: {} })),
    getPricingHistory: () => Promise.resolve({ history: [] }),
    getBnrRate: vi.fn(() => Promise.resolve({})),
    checkVin: () => Promise.resolve({ exists: false }),
  },
}))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => selector({ user: { company_id: 1 } }),
}))
vi.mock('@/stores/carParkStore', () => ({
  useCarParkStore: (selector: (s: unknown) => unknown) => selector({ selectedCompanyId: null }),
}))

function renderNewVehicleForm(entry = '/edit/new') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/edit/:vehicleId" element={<VehicleForm />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('the acquisition tab is renamed to "Preț"', () => {
  renderNewVehicleForm()
  expect(screen.getByRole('tab', { name: 'Preț' })).toBeInTheDocument()
})

test('the Preț tab exposes list-price and promo fields', () => {
  // Active tab is driven by the ?tab= URL param, so render straight onto it.
  renderNewVehicleForm('/edit/new?tab=comercial')
  expect(screen.getByText(/Preț listă/)).toBeInTheDocument()
  expect(screen.getByText(/Preț promo/)).toBeInTheDocument()
  expect(screen.getByText(/obligatoriu la adăugarea unei mașini/)).toBeInTheDocument()
})

test('editor LOAD reconstructs the RON entry from a canonical EUR vehicle', async () => {
  // Canonical vehicle: acquisition_price = GROSS EUR, purchase_price_net = NET EUR.
  // 40,000 net LEI @ 19% VAT, kurs 5 → gross EUR 9520, net EUR 8000 (see acquisitionCanonical.test.ts).
  // The Net-Lei field must reconstruct 40000 via netLeiFromCanonical on load.
  vi.mocked(carparkApi.getVehicle).mockResolvedValueOnce({
    vehicle: {
      acquisition_price: 9520,
      purchase_price_net: 8000,
      acquisition_currency: 'EUR',
      acquisition_exchange_rate: 5,
      purchase_vat_rate: 19,
    },
  } as never)
  renderNewVehicleForm('/edit/123?tab=comercial')
  expect(await screen.findByDisplayValue('40000')).toBeInTheDocument()
})

test('editing Net-Lei during an in-flight BNR fetch is not reverted when it resolves', async () => {
  // Regression: fetchBnr must combine the resolved kurs with the CURRENT net-LEI
  // (read from a ref), not the stale value captured when the fetch started.
  let resolveBnr: (v: { kurs: number; kurs_date: string }) => void = () => {}
  const pending = new Promise<{ kurs: number; kurs_date: string }>((res) => {
    resolveBnr = res
  })
  vi.mocked(carparkApi.getBnrRate).mockReturnValueOnce(pending as never)

  const { container } = renderNewVehicleForm('/edit/new?tab=comercial')

  // Changing the acquisition date kicks off a BNR fetch that stays pending.
  const dateInput = container.querySelector('input[type="date"]') as HTMLInputElement
  fireEvent.change(dateInput, { target: { value: '2026-01-15' } })

  // While the fetch is in flight, the user types a net-LEI amount.
  const netLei = screen.getByPlaceholderText('RON') as HTMLInputElement
  fireEvent.change(netLei, { target: { value: '40000' } })
  expect(netLei.value).toBe('40000')

  // The BNR response resolves — the field must keep 40000 (combined with the new
  // kurs), NOT revert to its stale (empty) pre-fetch value.
  await act(async () => {
    resolveBnr({ kurs: 5, kurs_date: '2026-01-15' })
  })
  expect((screen.getByPlaceholderText('RON') as HTMLInputElement).value).toBe('40000')
})
