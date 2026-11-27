import { render, waitFor } from '@testing-library/react'
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

// The "Tip stoc" trigger text (Radix SelectValue), read from the DOM. A loaded
// value must render its label here, not the "Select tip stoc" placeholder — the
// bug was Radix's hidden bubble <select> firing a spurious onValueChange('') on
// programmatic load, wiping any non-default category back to blank.
async function tipStocText(category: string): Promise<string> {
  vi.mocked(carparkApi.getVehicle).mockResolvedValueOnce({
    vehicle: { vin: 'X', brand: 'Porsche', model: 'Cayenne', category },
  } as never)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { container } = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/edit/123']}>
        <Routes>
          <Route path="/edit/:vehicleId" element={<VehicleForm />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await waitFor(() => expect(container.querySelector('input')).toBeTruthy())
  // Let the load-populate + any spurious bubble event settle.
  await new Promise((r) => setTimeout(r, 80))
  const spans = Array.from(container.querySelectorAll('[data-slot="select-value"]'))
  // Tip stoc is the last SelectField on the Vehicul tab (after Stare).
  return spans[spans.length - 1]?.textContent ?? ''
}

test('CUS vehicle keeps "Custodie" selected on edit (not reset to blank)', async () => {
  expect(await tipStocText('CUS')).toBe('Custodie')
})

test('CON vehicle normalizes to "Custodie" on edit', async () => {
  expect(await tipStocText('CON')).toBe('Custodie')
})

test('NEW vehicle keeps "Nou" selected on edit', async () => {
  expect(await tipStocText('NEW')).toBe('Nou')
})
