import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [
    { id: 1, vin: 'VINAAA1', mark: 'Volvo', model: 'XC40', brand: 'Volvo', registration_number: 'B 111 AAA', company_id: 11, is_active: true, odometer_km: 12000, fuel_type: 'benzina' },
    { id: 2, vin: 'VINBBB2', mark: 'Audi', model: 'A4', brand: 'Audi', registration_number: 'B 222 BBB', company_id: 11, is_active: true, locked_out: true, lockout_category: 'Service', fuel_type: 'motorina' },
    { id: 3, vin: 'VINCCC3', mark: 'MG', model: 'ZS', brand: 'MG', registration_number: 'B 333 CCC', company_id: 11, is_active: false, archive_category: 'Vândut', fuel_type: 'electric' },
    { id: 4, vin: 'VINDDD4', mark: 'BMW', model: 'X1', brand: 'BMW', registration_number: 'B 444 DDD', company_id: 12, is_active: true, fuel_type: 'benzina' },
    { id: 5, vin: 'VINEEE5', mark: 'Volkswagen', model: 'Caravelle', brand: 'Volkswagen', registration_number: 'B 555 EEE', company_id: 11, is_active: true, fuel_type: 'motorina', on_drive: true, on_drive_client: 'Balea Gabriel', on_drive_until: '2026-08-21T11:06:00Z' },
  ] }),
} }))

import DrivingParkList from './DrivingParkList'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DrivingParkList (read-only Hub Driving Park)', () => {
  beforeEach(() => localStorage.clear())

  it('lists active vehicles for the company with availability pills; hides archived + other companies', async () => {
    wrap(<DrivingParkList companyId={11} brand="" carFilter={[]} />)
    expect(await screen.findByText('Volvo XC40')).toBeInTheDocument()
    expect(screen.getByText('Disponibil')).toBeInTheDocument()
    expect(screen.getByText('Audi A4')).toBeInTheDocument()
    expect(screen.getByText('Blocat')).toBeInTheDocument()
    expect(screen.queryByText('MG ZS')).not.toBeInTheDocument()   // archived hidden in Active view
    expect(screen.queryByText('BMW X1')).not.toBeInTheDocument()  // other company hidden
  })

  it('shows a car currently out on a test drive as "Pe drum", not "Disponibil"', async () => {
    wrap(<DrivingParkList companyId={11} brand="" carFilter={[]} />)
    expect(await screen.findByText('Volkswagen Caravelle')).toBeInTheDocument()
    // The out-with-a-client car must not read as available…
    expect(screen.getByText('Pe drum')).toBeInTheDocument()
    // …and only the genuinely-free car keeps the Disponibil pill.
    expect(screen.getAllByText('Disponibil')).toHaveLength(1)
  })

  it('is read-only — no add/edit/lock/archive controls', async () => {
    wrap(<DrivingParkList companyId={11} brand="" carFilter={[]} />)
    await screen.findByText('Volvo XC40')
    expect(screen.queryByRole('button', { name: /adaug|editeaz|blochea|arhive|șterge|sterge/i })).not.toBeInTheDocument()
  })

  it('shows archived vehicles under the Arhivate toggle', async () => {
    wrap(<DrivingParkList companyId={11} brand="" carFilter={[]} />)
    await screen.findByText('Volvo XC40')
    fireEvent.click(screen.getByRole('button', { name: /arhivate/i }))
    expect(await screen.findByText('MG ZS')).toBeInTheDocument()
    expect(screen.getByText('Arhivat')).toBeInTheDocument()
  })
})
