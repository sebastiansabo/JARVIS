import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { listCars, addCar, removeCar, carAvailability } = vi.hoisted(() => ({
  listCars: vi.fn(), addCar: vi.fn(), removeCar: vi.fn(), carAvailability: vi.fn(),
}))
vi.mock('@/api/tdAdmin', () => ({
  tdAdminApi: { listCars, addCar, removeCar, carAvailability },
}))
const { getVehicles } = vi.hoisted(() => ({ getVehicles: vi.fn() }))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getVehicles } }))
vi.mock('sonner', () => ({ toast: { warning: vi.fn(), error: vi.fn(), success: vi.fn() } }))

import TdCarsPanel from './TdCarsPanel'

const VEHICLES = [
  { id: 1, vin: 'FREEVIN0', mark: 'MG', model: 'HS', registration_number: 'CJ 01 FREE', company_id: 9, is_active: true, locked_out: false },
  { id: 2, vin: 'BLOCKVIN', mark: 'MG', model: 'ZS', registration_number: 'CJ 02 BLK', company_id: 9, is_active: true, locked_out: true },
  { id: 3, vin: 'BUSYVIN0', mark: 'MG', model: 'MG4', registration_number: 'CJ 03 BSY', company_id: 9, is_active: true, locked_out: false },
]

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <TdCarsPanel pageId={1} companyId={9} users={[] as never} />
    </QueryClientProvider>,
  )
}

async function selectVehicle(label: string) {
  fireEvent.click(await screen.findByText('Selectează mașina'))
  fireEvent.click(await screen.findByText(label))
}

const addBtn = () => screen.getByRole('button', { name: /Adaugă/ })

describe('TdCarsPanel — on-select availability', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    listCars.mockResolvedValue({ cars: [] })
    getVehicles.mockResolvedValue({ vehicles: VEHICLES })
  })

  it('gates a blocked car: shows a blocked notice and disables Adaugă', async () => {
    carAvailability.mockResolvedValue({
      vin: 'BLOCKVIN', blocked: true, lockout_category: null,
      lockout_note: 'Service', lockout_until: null, conflicts: [],
    })
    wrap()
    await selectVehicle('CJ 02 BLK — MG ZS')
    expect(await screen.findByText(/blocat/i)).toBeInTheDocument()
    expect(addBtn()).toBeDisabled()
  })

  it('allows a busy car: warns "ocupată" but keeps Adaugă enabled', async () => {
    carAvailability.mockResolvedValue({
      vin: 'BUSYVIN0', blocked: false, lockout_category: null,
      lockout_note: null, lockout_until: null,
      conflicts: [{
        id: 9, contract_id: 'TD-1', status: 'PLANNED', route_type: 'TD',
        departure_datetime: '2099-10-01T10:00:00', return_datetime: '2099-10-01T11:00:00',
        client_name: 'Ion Client', advisor_name: null,
      }],
    })
    wrap()
    await selectVehicle('CJ 03 BSY — MG MG4')
    expect(await screen.findByText(/ocupat/i)).toBeInTheDocument()
    expect(addBtn()).not.toBeDisabled()
  })

  it('shows available for a free car and keeps Adaugă enabled', async () => {
    carAvailability.mockResolvedValue({
      vin: 'FREEVIN0', blocked: false, lockout_category: null,
      lockout_note: null, lockout_until: null, conflicts: [],
    })
    wrap()
    await selectVehicle('CJ 01 FREE — MG HS')
    expect(await screen.findByText(/disponibil/i)).toBeInTheDocument()
    expect(addBtn()).not.toBeDisabled()
  })
})
