import { render, screen, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi, test, expect, beforeEach } from 'vitest'
import { CostsTab } from './CostsTab'
import { carparkApi } from '@/api/carpark'

// The flat Financiar Costuri table: one row per cost ENTRY (no cost-line
// grouping / budget columns / expand-collapse), mirroring the already-flat
// RevenuesTab, with a single-step "Adaugă cost".
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/api/carpark', () => ({
  carparkApi: {
    getCosts: vi.fn(() =>
      Promise.resolve({
        costs: [
          { id: 1, cost_type: 'achizitie', amount: 1000, vat_amount: 190, vat_rate: 19, currency: 'EUR', amount_eur: 1000, vat_amount_eur: 190, date: '2025-11-17', supplier_name: 'AUTOWORLD PREMIUM SRL', invoice_number: '37825142', invoice_id: null, description: 'Pachet anvelope', cost_line_id: 5 },
          { id: 2, cost_type: 'repair', amount: 500, vat_amount: 0, vat_rate: 0, currency: 'EUR', amount_eur: 500, vat_amount_eur: 0, date: '2025-11-18', supplier_name: 'B SRL', invoice_number: null, invoice_id: null, description: 'Schimb ulei', cost_line_id: 6 },
        ],
      }),
    ),
    createCost: vi.fn(() => Promise.resolve({ cost: { id: 3 } })),
    updateCost: vi.fn(() => Promise.resolve({ cost: {} })),
    deleteCost: vi.fn(() => Promise.resolve({ success: true })),
    linkCostInvoice: vi.fn(() => Promise.resolve({ success: true })),
    searchLinkableEntities: vi.fn(() => Promise.resolve({ results: [] })),
  },
}))

beforeEach(() => vi.clearAllMocks())

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CostsTab vehicleId={1} canEdit currency="EUR" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('renders every cost entry in one flat table with a subtotal row', async () => {
  renderTab()
  // Both entries render as flat rows, Tip taken from each cost's cost_type.
  await screen.findByText('Achiziție')
  expect(screen.getByText('Reparație')).toBeInTheDocument()
  // Subtotal footer: Σ Net = 1500 and Σ Total = 1690 (ro-RO), each unique to
  // the footer (no individual row shows these values).
  expect(screen.getByText('1.500,00')).toBeInTheDocument()
  expect(screen.getByText('1.690,00')).toBeInTheDocument()
})

test('the Tip is editable inline — selecting another cost_type calls updateCost', async () => {
  renderTab()
  await screen.findByText('Achiziție')
  // Click the Tip badge to edit, then pick a different category.
  await act(async () => { fireEvent.click(screen.getByText('Achiziție')) })
  const select = screen.getByRole('combobox', { name: /Tip cost/i })
  await act(async () => { fireEvent.change(select, { target: { value: 'repair' } }) })

  expect(carparkApi.updateCost).toHaveBeenCalledTimes(1)
  const [id, payload] = vi.mocked(carparkApi.updateCost).mock.calls[0] as [number, Record<string, unknown>]
  expect(id).toBe(1)
  expect(payload.cost_type).toBe('repair')
})

test('a RON cost shows the original RON figure AND its EUR equivalent; subtotal is EUR', async () => {
  vi.mocked(carparkApi.getCosts).mockResolvedValueOnce({
    costs: [
      { id: 10, cost_type: 'transport', amount: 5000, vat_amount: 950, currency: 'RON', exchange_rate_eur: 5.0, amount_eur: 1000, vat_amount_eur: 190, date: '2025-11-17', supplier_name: 'X', invoice_number: null, invoice_id: null, description: '' },
      { id: 11, cost_type: 'other', amount: 200, vat_amount: 0, currency: 'EUR', exchange_rate_eur: null, amount_eur: 200, vat_amount_eur: 0, date: '2025-11-18', supplier_name: 'Y', invoice_number: null, invoice_id: null, description: '' },
    ],
  })
  renderTab()
  await screen.findByText('Transport')
  // The row shows both: the original RON invoice figure (prominent) and its EUR
  // equivalent (smaller), plus the BNR curs used for the conversion.
  expect(screen.getByText(/5\.000,00/)).toBeInTheDocument()   // original RON net
  expect(screen.getByText(/1\.000,00/)).toBeInTheDocument()   // EUR equivalent (small)
  expect(screen.getByText(/curs 5,0000/)).toBeInTheDocument() // the exchange rate shown
  // The subtotal is EUR (Σ net = 1000 + 200 = 1200), NOT the raw mixed sum 5200.
  expect(screen.getAllByText(/1\.200,00/).length).toBeGreaterThan(0)
  expect(screen.queryByText(/5\.200,00/)).toBeNull()
})

test('Adaugă cost is a single-step add calling createCost with cost_type + amount', async () => {
  renderTab()
  await screen.findByText('Achiziție')
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Adaugă cost/i })) })
  // Amount is the first number input in the dialog; no cost-line step required.
  const amount = screen.getAllByRole('spinbutton')[0]
  await act(async () => { fireEvent.change(amount, { target: { value: '250' } }) })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /^Înregistrează$/i })) })

  expect(carparkApi.createCost).toHaveBeenCalledTimes(1)
  const [vid, payload] = vi.mocked(carparkApi.createCost).mock.calls[0] as [number, Record<string, unknown>]
  expect(vid).toBe(1)
  expect(payload.cost_type).toBeTruthy()  // a Tip is sent → backend files the line
  expect(payload.amount).toBe(250)
})

test('editing a cost does not overwrite its stored currency', async () => {
  renderTab()
  await screen.findByText('Achiziție')
  // Open the first row's edit dialog (cost #1 carries its own stored currency).
  await act(async () => { fireEvent.click(screen.getAllByRole('button', { name: /Editează cost/i })[0]) })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Actualizează/i })) })

  expect(carparkApi.updateCost).toHaveBeenCalledTimes(1)
  const [, payload] = vi.mocked(carparkApi.updateCost).mock.calls[0] as [number, Record<string, unknown>]
  // currency is a create-time attribute (it seeds the cost line); an edit must
  // NOT send it, or it would clobber the cost's stored currency with the
  // vehicle's price_currency.
  expect('currency' in payload).toBe(false)
})
