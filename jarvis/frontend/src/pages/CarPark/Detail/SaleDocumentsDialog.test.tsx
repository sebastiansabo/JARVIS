import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { carparkSaleDocsApi } from '@/api/carparkSaleDocs'
import { SaleDocumentsDialog } from './SaleDocumentsDialog'
import type { Vehicle } from '@/types/carpark'

vi.mock('@/api/carparkSaleDocs', () => ({
  carparkSaleDocsApi: {
    generate: vi.fn(() => Promise.resolve(new Blob(['%PDF'], { type: 'application/pdf' }))),
    save: vi.fn(() => Promise.resolve({ document: { id: 1 } })),
    listLeasingCompanies: vi.fn(() => Promise.resolve({ leasing_companies: [] })),
    createLeasingCompany: vi.fn(),
  },
}))

// The leasing picker owns its own react-query cache and a Radix Select —
// irrelevant to this dialog's own logic, so stub it down to a marker div
// (same convention as LeasingCompanySelect.test.tsx stubbing `ui/select`).
vi.mock('./LeasingCompanySelect', () => ({
  LeasingCompanySelect: () => <div data-testid="leasing-select" />,
}))

// jsdom has neither URL.createObjectURL nor a real window.open; the
// "Generează" handler calls both to pop the rendered PDF into a new tab —
// without these stubs it throws before carparkSaleDocsApi.generate's
// mocked promise can even be asserted on.
global.URL.createObjectURL = vi.fn(() => 'blob:mock')
window.open = vi.fn()

function baseVehicle(overrides: Partial<Vehicle> = {}): Vehicle {
  return {
    id: 42,
    vin: 'WAUZZZ8K9DA012345',
    brand: 'Audi',
    model: 'A4',
    sale_type: 'CASH',
    sale_price: 25000,
    current_price: 27000,
    price_currency: 'EUR',
    sale_date: '2026-10-01',
    fuel_type: 'Diesel',
    ...overrides,
  } as Vehicle
}

function renderDialog(vehicle = baseVehicle(), onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={qc}>
      <SaleDocumentsDialog vehicle={vehicle} onClose={onClose} />
    </QueryClientProvider>,
  )
  return { ...utils, onClose, qc }
}

// The three doc rows render in this fixed order (Contract, Proformă,
// Garanție), so "the contract row's button" is reliably index 0.
const contractGenerateButton = () => screen.getAllByRole('button', { name: /^generează$/i })[0]
const contractSaveButton = () => screen.getAllByRole('button', { name: /salvează în documente/i })[0]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SaleDocumentsDialog', () => {
  it('renders the form with the three document rows and a contract-number input', () => {
    renderDialog()
    expect(screen.getByText('Contract')).toBeInTheDocument()
    expect(screen.getByText('Proformă')).toBeInTheDocument()
    expect(screen.getByText('Garanție')).toBeInTheDocument()
    expect(screen.getByLabelText(/nr\. contract/i)).toBeInTheDocument()
  })

  it('"Generează" on the Contract row calls generate with vehicle.id and the typed contract_number', async () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText(/nr\. contract/i), { target: { value: 'CTR-99' } })

    fireEvent.click(contractGenerateButton())

    await waitFor(() =>
      expect(carparkSaleDocsApi.generate).toHaveBeenCalledWith(
        42,
        expect.objectContaining({
          doc_type: 'contract',
          form: expect.objectContaining({ contract_number: 'CTR-99' }),
        }),
      ),
    )
  })

  it('shows the leasing picker for a leasing sale_type', () => {
    renderDialog(baseVehicle({ sale_type: 'BT LEASING' }))
    expect(screen.getByTestId('leasing-select')).toBeInTheDocument()
  })

  it('hides the leasing picker for a CASH sale', () => {
    renderDialog(baseVehicle({ sale_type: 'CASH' }))
    expect(screen.queryByTestId('leasing-select')).not.toBeInTheDocument()
  })

  it('"Salvează în Documente" on the Contract row calls save and invalidates the documents query', async () => {
    const { qc } = renderDialog()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')

    fireEvent.change(screen.getByLabelText(/nr\. contract/i), { target: { value: 'CTR-1' } })
    fireEvent.click(contractSaveButton())

    await waitFor(() =>
      expect(carparkSaleDocsApi.save).toHaveBeenCalledWith(
        42,
        expect.objectContaining({
          doc_type: 'contract',
          form: expect.objectContaining({ contract_number: 'CTR-1' }),
        }),
      ),
    )
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['carpark', 'documents', 42] }),
    )
  })
})
