import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const { getTaxonomy, syncTaxonomy, saveTaxonomyMap, getAccounts } = vi.hoisted(() => ({
  getTaxonomy: vi.fn(),
  syncTaxonomy: vi.fn(),
  saveTaxonomyMap: vi.fn(),
  getAccounts: vi.fn(),
}))
vi.mock('@/api/autovit', () => ({
  autovitApi: { getTaxonomy, syncTaxonomy, saveTaxonomyMap, getAccounts },
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import AutovitTaxonomy from './AutovitTaxonomy'

const TAXONOMY_DATA = {
  success: true,
  cache: [
    { dimension: 'fuel_type', code: 'diesel', ro_label: 'Diesel', param_type: 'enum', make: null, options: null },
    { dimension: 'fuel_type', code: 'petrol', ro_label: 'Petrol', param_type: 'enum', make: null, options: null },
    { dimension: 'make', code: 'audi', ro_label: 'Audi', param_type: null, make: null, options: null },
    { dimension: 'model', code: 'a4', ro_label: 'A4', param_type: null, make: 'audi', options: null },
  ],
  map: [],
  dimensions: {
    make: { kind: 'param', param: 'make', required: true },
    model: { kind: 'param', param: 'model', required: true },
    fuel_type: { kind: 'param', param: 'fuel_type', required: true },
    body_type: { kind: 'param', param: 'body_type', required: true },
    color: { kind: 'param', param: 'color', required: true },
    gearbox: { kind: 'param', param: 'gearbox', required: false },
    drive: { kind: 'param', param: 'transmission', required: false },
    pollution_standard: { kind: 'param', param: 'pollution_standard', required: false },
    equipment: { kind: 'flag', param: null, required: false },
  },
  sources: {
    make: [
      { source_value: 'Audi', target_code: 'audi', target_label: 'Audi', suggestions: [{ target_code: 'audi', target_label: 'Audi', score: 1 }] },
    ],
    model: [
      { source_value: 'A4', make: 'Audi', resolved_make_code: 'audi', target_code: null, target_label: null, suggestions: [{ target_code: 'a4', target_label: 'A4', score: 1 }] },
    ],
    fuel_type: [
      {
        source_value: 'Diesel',
        target_code: null,
        target_label: null,
        suggestions: [{ target_code: 'diesel', target_label: 'Diesel', score: 1 }],
      },
    ],
    body_type: [],
    color: [],
    gearbox: [],
    drive: [],
    pollution_standard: [],
    equipment: [],
  },
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <AutovitTaxonomy />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('AutovitTaxonomy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    getTaxonomy.mockResolvedValue(TAXONOMY_DATA)
    getAccounts.mockResolvedValue([])
    saveTaxonomyMap.mockResolvedValue({ success: true })
    syncTaxonomy.mockResolvedValue({ success: true, synced: 10, by_dimension: {} })
  })

  it('renders dimensions and flags unmapped', async () => {
    wrap()

    // The unmapped fuel_type value shows up with the "Nemapat" flag.
    expect(await screen.findByText('Diesel')).toBeInTheDocument()
    expect(screen.getAllByText('Nemapat').length).toBeGreaterThan(0)

    // The already-mapped make value renders too (brand label + model group header).
    expect((await screen.findAllByText('Audi')).length).toBeGreaterThan(0)

    // Selecting the top suggestion for the unmapped fuel_type row saves it
    // (scoped to its own table row — the model table has an unmapped row too).
    const dieselRow = (await screen.findByText('Diesel')).closest('tr')!
    fireEvent.click(within(dieselRow).getByText('Selectează cod Autovit...'))
    fireEvent.click(await screen.findByText('Diesel (diesel)'))

    await waitFor(() =>
      expect(saveTaxonomyMap).toHaveBeenCalledWith({
        dimension: 'fuel_type',
        source_value: 'Diesel',
        make: null,
        target_code: 'diesel',
        target_label: 'Diesel',
      }),
    )
  })

  it('groups model rows by make and resolves the scoped make code', async () => {
    wrap()
    expect(await screen.findByText('A4')).toBeInTheDocument()
    // The make-group header renders the CarPark brand label.
    expect(screen.getAllByText('Audi').length).toBeGreaterThan(0)
  })

  it('syncs the selected account via syncTaxonomy', async () => {
    getAccounts.mockResolvedValue([
      { id: 7, name: 'x', email: 'dealer@autoworld.ro', environment: 'production', client_id: 'c', status: 'connected', last_sync: null, last_error: null, credential_fields: { client_secret: '', password: '' } },
    ])
    wrap()

    fireEvent.click(await screen.findByText('Alege cont Autovit...'))
    fireEvent.click(await screen.findByText('dealer@autoworld.ro'))
    fireEvent.click(screen.getByText('Sincronizează taxonomia'))

    await waitFor(() => expect(syncTaxonomy).toHaveBeenCalledWith(7))
  })
})
