import { render, screen, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi, test, expect, beforeEach } from 'vitest'
import VehicleForm from './VehicleForm'
import { carparkApi } from '@/api/carpark'

vi.mock('@/api/carpark', () => ({
  carparkApi: {
    getLocations: () => Promise.resolve({ locations: [] }),
    getVehicle: vi.fn(() => Promise.resolve({ vehicle: {} })),
    getPricingHistory: () => Promise.resolve({ history: [] }),
    getBnrRate: vi.fn(() => Promise.resolve({})),
    checkVin: () => Promise.resolve({ exists: false }),
    decodeDocument: vi.fn(),
  },
}))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => selector({ user: { company_id: 1 } }),
}))
vi.mock('@/stores/carParkStore', () => ({
  useCarParkStore: (selector: (s: unknown) => unknown) => selector({ selectedCompanyId: null }),
}))

function renderForm(entry: string) {
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

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

test('a new vehicle starts gated: scan prompt visible, the form tabs hidden', () => {
  renderForm('/edit/new')
  expect(screen.getByRole('button', { name: /Scanează/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Introdu manual/i })).toBeInTheDocument()
  // The full form (its tabs) must not be rendered until the gate is passed.
  expect(screen.queryByRole('tab', { name: 'Preț' })).toBeNull()
})

test('clicking "Introdu manual" reveals the full form', () => {
  renderForm('/edit/new')
  fireEvent.click(screen.getByRole('button', { name: /Introdu manual/i }))
  expect(screen.getByRole('tab', { name: 'Preț' })).toBeInTheDocument()
})

test('edit mode is never gated — the form is visible immediately', async () => {
  vi.mocked(carparkApi.getVehicle).mockResolvedValueOnce({
    vehicle: { brand: 'VW', model: 'Golf' },
  } as never)
  renderForm('/edit/123')
  expect(await screen.findByRole('tab', { name: 'Preț' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Introdu manual/i })).toBeNull()
})

test('restoring a saved draft reveals the form past the scan gate', () => {
  localStorage.setItem('carpark-draft-new', JSON.stringify({ brand: 'VW', model: 'Golf' }))
  renderForm('/edit/new')
  // The gate is up, but a draft banner offers to resume.
  expect(screen.queryByRole('tab', { name: 'Preț' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /Restaurează ciorna/i }))
  // Resuming must reveal the form, not leave the restored data hidden behind the gate.
  expect(screen.getByRole('tab', { name: 'Preț' })).toBeInTheDocument()
})

test('scanning a document and applying reveals the prefilled form', async () => {
  vi.mocked(carparkApi.decodeDocument).mockResolvedValueOnce({
    success: true,
    data: {
      vehicle_fields: { brand: 'Audi', registration_number: 'B123ABC' },
      provider: 'Talon',
      confidence: 0.9,
      document_type: 'talon',
    },
  } as never)

  const { container } = renderForm('/edit/new')
  const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
  const file = new File(['x'], 'talon.jpg', { type: 'image/jpeg' })

  await act(async () => {
    fireEvent.change(fileInput, { target: { files: [file] } })
  })

  // The review dialog appears; applying it passes the gate and shows the form.
  const applyBtn = await screen.findByRole('button', { name: /Aplică datele/i })
  fireEvent.click(applyBtn)

  expect(carparkApi.decodeDocument).toHaveBeenCalledWith(file)
  expect(screen.getByRole('tab', { name: 'Preț' })).toBeInTheDocument()
})
