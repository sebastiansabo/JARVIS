import { render, screen, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi, test, expect } from 'vitest'
import VehicleForm from './VehicleForm'
import { carparkApi } from '@/api/carpark'

// Task 3: the acquisition-cost editor and its JSON write path are gone. The
// edit form must no longer produce `cost_lines` on save — that legacy JSON
// blob (and its "migrate the fixed columns into it" path) is omitted
// entirely, because it was never added as a key of the form's own state.
// reconditioning_cost/transport_cost/other_costs ARE still keys of the form
// state (there's no UI to edit them anymore, but nothing strips them), so a
// hydrated edit DOES round-trip their existing values verbatim in the save
// payload — this test pins that too, so a future change doesn't
// accidentally start dropping (or re-deriving) them.
vi.mock('@/api/carpark', () => ({
  carparkApi: {
    getLocations: () => Promise.resolve({ locations: [] }),
    getVehicle: vi.fn(() =>
      Promise.resolve({
        vehicle: {
          vin: 'WVWZZZ1KZAM123456',
          brand: 'VW',
          model: 'Golf',
          category: 'SH',
          // Legacy data a pre-migration car might still carry — the save
          // payload must not resurrect or re-derive any of this.
          cost_lines: JSON.stringify([{ type: 'Transport', eur: 300 }]),
          reconditioning_cost: 500,
          transport_cost: 200,
          other_costs: 50,
        },
      }),
    ),
    getPricingHistory: () => Promise.resolve({ history: [] }),
    getBnrRate: vi.fn(() => Promise.resolve({})),
    checkVin: () => Promise.resolve({ exists: false }),
    updateVehicle: vi.fn(() => Promise.resolve({ vehicle: {} })),
  },
}))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => selector({ user: { company_id: 1 } }),
}))
vi.mock('@/stores/carParkStore', () => ({
  useCarParkStore: (selector: (s: unknown) => unknown) => selector({ selectedCompanyId: null }),
}))

function renderEditForm(entry: string) {
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

test('saving an edited vehicle omits cost_lines but round-trips the legacy cost columns', async () => {
  renderEditForm('/edit/123')

  // Wait for existingData to hydrate the form (VIN field populated).
  await screen.findByDisplayValue('WVWZZZ1KZAM123456')

  // The submit action is rendered twice (header + bottom bar); either fires
  // the same form submit.
  await act(async () => {
    fireEvent.click(screen.getAllByRole('button', { name: /Save Changes/i })[0])
  })

  expect(carparkApi.updateVehicle).toHaveBeenCalledTimes(1)
  const [, payload] = vi.mocked(carparkApi.updateVehicle).mock.calls[0] as [string, Record<string, unknown>]

  // The legacy JSON blob must never reappear in a save payload, even when the
  // loaded vehicle still carries a non-empty cost_lines.
  expect('cost_lines' in payload).toBe(false)

  // reconditioning_cost/transport_cost/other_costs are no longer editable in
  // the UI, but they ARE still keys of the form's own state — so hydrating
  // from an existing vehicle round-trips their values verbatim on save. This
  // is expected/accepted (not a regression to "fix"): pin it so a future
  // change doesn't silently start dropping or re-deriving them instead.
  expect(payload.reconditioning_cost).toBe(500)
  expect(payload.transport_cost).toBe(200)
  expect(payload.other_costs).toBe(50)
})
