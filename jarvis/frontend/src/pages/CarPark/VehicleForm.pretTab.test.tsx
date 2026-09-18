import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi, test, expect } from 'vitest'
import VehicleForm from './VehicleForm'

vi.mock('@/api/carpark', () => ({
  carparkApi: {
    getLocations: () => Promise.resolve({ locations: [] }),
    getVehicle: () => Promise.resolve({ vehicle: {} }),
    getPricingHistory: () => Promise.resolve({ history: [] }),
    getBnrRate: () => Promise.resolve({}),
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
