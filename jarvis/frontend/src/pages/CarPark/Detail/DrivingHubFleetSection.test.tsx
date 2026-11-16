import type { ReactNode } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { carparkApi } from '@/api/carpark'
import { foiParcursApi } from '@/api/foiParcurs'
import { DrivingHubFleetSection } from './DrivingHubFleetSection'
import type { DrivingHubSuggested } from '@/api/carpark'

vi.mock('@/api/carpark', () => ({
  carparkApi: {
    getDrivingHubStatus: vi.fn(),
    pushToDrivingHub: vi.fn(),
    getCompanies: vi.fn(),
  },
}))

vi.mock('@/api/foiParcurs', () => ({
  foiParcursApi: {
    getBrands: vi.fn(),
  },
}))

// The real shadcn Select is Radix-backed: while closed it renders its items
// into a detached DocumentFragment (a portal), so option labels never hit the
// queryable DOM, and jsdom lacks the layout APIs Radix probes on open. Stub
// it to plain DOM, same convention as LeasingCompanySelect.test.tsx.
vi.mock('@/components/ui/select', () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  return {
    Select: Passthrough,
    SelectTrigger: Passthrough,
    SelectContent: Passthrough,
    SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
    SelectItem: ({ children }: { children?: ReactNode }) => <div role="option">{children}</div>,
  }
})

// The dialog's own show/hide is all this component relies on — stub away
// Radix's Portal/animation machinery so content mounts/unmounts synchronously
// with the `open` prop instead of needing to wait on portal + animation frames.
vi.mock('@/components/ui/dialog', () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  return {
    Dialog: ({ open, children }: { open?: boolean; children?: ReactNode }) =>
      open ? <div>{children}</div> : null,
    DialogContent: Passthrough,
    DialogHeader: Passthrough,
    DialogFooter: Passthrough,
    DialogTitle: Passthrough,
    DialogDescription: Passthrough,
    DialogTrigger: Passthrough,
  }
})

function baseSuggested(overrides: Partial<DrivingHubSuggested> = {}): DrivingHubSuggested {
  return {
    mark: 'Dacia',
    brand: 'Dacia',
    model: 'Duster',
    registration_number: 'CJ 99 ABC',
    fuel_type: 'Diesel',
    company_id: 7,
    odometer_km: 15000,
    color: 'Alb',
    ...overrides,
  }
}

function mockStatus(overrides: {
  in_fleet?: boolean
  archived?: boolean
  fp_vehicle_id?: number | null
  suggested?: DrivingHubSuggested
} = {}) {
  vi.mocked(carparkApi.getDrivingHubStatus).mockResolvedValue({
    in_fleet: false,
    archived: false,
    fp_vehicle_id: null,
    suggested: baseSuggested(),
    ...overrides,
  })
}

function renderSection(vehicleId = 1, canEdit = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={qc}>
      <DrivingHubFleetSection vehicleId={vehicleId} canEdit={canEdit} />
    </QueryClientProvider>,
  )
  return { ...utils, qc }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(carparkApi.getCompanies).mockResolvedValue({
    companies: [
      { id: 1, name: 'Autoworld SRL' },
      { id: 2, name: 'Next Motors' },
    ],
  })
  // Default catalog contains the base suggested make ('Dacia'), so the brand
  // Select auto-selects it and the happy-path tests clear the brand gate.
  vi.mocked(foiParcursApi.getBrands).mockResolvedValue({
    success: true,
    brands: ['Dacia', 'Volkswagen'],
  })
})

describe('DrivingHubFleetSection', () => {
  it('shows "Adaugă în Driving Hub" when not in fleet', async () => {
    mockStatus({ in_fleet: false, archived: false })
    renderSection()
    expect(await screen.findByRole('button', { name: /adaugă în driving hub/i })).toBeInTheDocument()
  })

  it('shows "În flotă" + "Deschide în Driving Hub" link when in_fleet', async () => {
    mockStatus({ in_fleet: true, archived: false, fp_vehicle_id: 42 })
    renderSection()
    expect(await screen.findByText(/în flotă/i)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /deschide în driving hub/i })
    expect(link).toHaveAttribute('href', '/app/foi-parcurs')
  })

  it('shows "arhivat" and disables the add button when archived', async () => {
    mockStatus({ in_fleet: true, archived: true, fp_vehicle_id: 42 })
    renderSection()
    expect(await screen.findByText(/arhivat/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /adaugă în driving hub/i })).toBeDisabled()
  })

  it('opens the dialog and requires a capacity value before submit', async () => {
    mockStatus({ in_fleet: false, archived: false, suggested: baseSuggested({ fuel_type: 'Diesel' }) })
    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: /adaugă în driving hub/i }))

    const confirmButton = await screen.findByRole('button', { name: /adaugă în flotă/i })
    expect(confirmButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/capacitate rezervor/i), { target: { value: '55' } })
    // The fleet brand auto-selects from the catalog (make 'Dacia' matches), so
    // once capacity is filled the submit unlocks.
    await waitFor(() => expect(confirmButton).not.toBeDisabled())
  })

  it('renders the fleet brand Select from getBrands', async () => {
    mockStatus({ in_fleet: false, archived: false, suggested: baseSuggested({ fuel_type: 'Diesel' }) })
    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: /adaugă în driving hub/i }))

    expect(await screen.findByText('Marcă (flotă)')).toBeInTheDocument()
    expect(await screen.findByText('Volkswagen')).toBeInTheDocument()
    // Dacia appears as both the catalog option and the auto-selected value.
    expect(await screen.findAllByText('Dacia')).not.toHaveLength(0)
  })

  it('keeps submit disabled when the make has no catalog match', async () => {
    mockStatus({
      in_fleet: false,
      archived: false,
      suggested: baseSuggested({ fuel_type: 'Diesel', mark: 'Tesla' }),
    })
    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: /adaugă în driving hub/i }))

    // Wait for the catalog to load (brand Select rendered) — 'Tesla' isn't in
    // it, so no default is picked and submit stays blocked even with capacity.
    await screen.findByText('Marcă (flotă)')
    fireEvent.change(screen.getByLabelText(/capacitate rezervor/i), { target: { value: '55' } })
    const confirmButton = screen.getByRole('button', { name: /adaugă în flotă/i })
    await waitFor(() => expect(confirmButton).toBeDisabled())
  })

  it('falls back to the make as brand when the catalog is empty', async () => {
    vi.mocked(foiParcursApi.getBrands).mockResolvedValue({ success: true, brands: [] })
    const suggested = baseSuggested({ fuel_type: 'Diesel', company_id: 7, mark: 'Dacia' })
    mockStatus({ in_fleet: false, archived: false, suggested })
    vi.mocked(carparkApi.pushToDrivingHub).mockResolvedValue({ fp_vehicle_id: 77 })

    renderSection(8)
    fireEvent.click(await screen.findByRole('button', { name: /adaugă în driving hub/i }))

    // No fleet brand Select when the catalog is empty.
    expect(screen.queryByText('Marcă (flotă)')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/capacitate rezervor/i), { target: { value: '55' } })
    fireEvent.click(screen.getByRole('button', { name: /adaugă în flotă/i }))

    await waitFor(() =>
      expect(carparkApi.pushToDrivingHub).toHaveBeenCalledWith(
        8,
        expect.objectContaining({ brand: 'Dacia' }),
      ),
    )
  })

  it('renders a company Select when suggested.company_id is null', async () => {
    mockStatus({ in_fleet: false, archived: false, suggested: baseSuggested({ company_id: null }) })
    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: /adaugă în driving hub/i }))

    expect(await screen.findByText('Companie')).toBeInTheDocument()
    expect(await screen.findByText('Autoworld SRL')).toBeInTheDocument()
    expect(await screen.findByText('Next Motors')).toBeInTheDocument()
  })

  it('calls pushToDrivingHub with mapped payload incl. chosen fleet brand on confirm', async () => {
    const suggested = baseSuggested({ fuel_type: 'Diesel', company_id: 7 })
    mockStatus({ in_fleet: false, archived: false, suggested })
    vi.mocked(carparkApi.pushToDrivingHub).mockResolvedValue({ fp_vehicle_id: 99 })

    renderSection(5)
    fireEvent.click(await screen.findByRole('button', { name: /adaugă în driving hub/i }))

    fireEvent.change(screen.getByLabelText(/capacitate rezervor/i), { target: { value: '55' } })
    const confirmButton = screen.getByRole('button', { name: /adaugă în flotă/i })
    // Wait for the catalog to auto-select the matching brand before submitting.
    await waitFor(() => expect(confirmButton).not.toBeDisabled())
    fireEvent.click(confirmButton)

    await waitFor(() =>
      expect(carparkApi.pushToDrivingHub).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          mark: 'Dacia',
          brand: 'Dacia',
          model: 'Duster',
          registration_number: 'CJ 99 ABC',
          fuel_type: 'Diesel',
          company_id: 7,
          odometer_km: 15000,
          color: 'Alb',
          fuel_tank_capacity_liters: 55,
        }),
      ),
    )
  })
})
