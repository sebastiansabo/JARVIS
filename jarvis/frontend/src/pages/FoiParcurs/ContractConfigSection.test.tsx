import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { getDocumentTypes, addDocumentType } = vi.hoisted(() => ({
  getDocumentTypes: vi.fn().mockResolvedValue({ types: [
    { key: 'sales', label: 'Vânzări', title: null, body_template: null, general_conditions: null, is_rental: false, is_active: true, is_default: true, sort_order: 0, has_template: false },
    { key: 'service', label: 'Mașini de curtoazie', title: 'Contract', body_template: 'B', general_conditions: 'C', is_rental: true, is_active: true, is_default: false, sort_order: 1, has_template: true },
  ] }),
  addDocumentType: vi.fn().mockResolvedValue({ success: true, key: 'comodat' }),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getDocumentTypes, addDocumentType, putDocumentType: vi.fn() } }))

import ContractConfigSection from './ContractConfigSection'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ContractConfigSection — token cheat-sheet', () => {
  // The cheat-sheet must list every placeholder the backend renderer supports
  // (jarvis/foi_parcurs/services/contract_template.py PLACEHOLDERS) — it had
  // drifted to only the first 15 of 38.
  it('lists the full backend placeholder set, grouped', () => {
    wrap(<ContractConfigSection />)
    expect(screen.getByText('{client_cui}')).toBeInTheDocument()
    expect(screen.getByText('{vehicle_model}')).toBeInTheDocument()
    expect(screen.getByText('{company_iban}')).toBeInTheDocument()
    expect(screen.getByText('{dealer_phone}')).toBeInTheDocument()
    expect(screen.getByText('{svc_total_eur}')).toBeInTheDocument()
    expect(screen.getByText('{svc_garantie_eur}')).toBeInTheDocument()
    expect(screen.getByText('{client_name}')).toBeInTheDocument()
    expect(screen.getByText('{general_conditions}')).toBeInTheDocument()
  })
})

describe('ContractConfigSection — document types', () => {
  it('renders a collapsible card per type + an add control for the header company', async () => {
    wrap(<ContractConfigSection companyId={11} />)
    // one card per type (sales default + service)
    expect(await screen.findByText('Vânzări')).toBeInTheDocument()
    expect(screen.getByText('Mașini de curtoazie')).toBeInTheDocument()
    // rental badge on the rental type
    expect(screen.getByText('Închiriere')).toBeInTheDocument()
    // add control
    expect(screen.getByPlaceholderText(/comodat/i)).toBeInTheDocument()
  })

  it('sales is read-only when expanded (no template editor)', async () => {
    wrap(<ContractConfigSection companyId={11} />)
    fireEvent.click(await screen.findByText('Vânzări'))
    expect(screen.getByText(/folosește contractul legal standard/i)).toBeInTheDocument()
    // no body-template editor for sales
    expect(screen.queryByText(/Conținut contract/i)).not.toBeInTheDocument()
  })

  it('adds a new type from the label input (Enter)', async () => {
    wrap(<ContractConfigSection companyId={11} />)
    const input = await screen.findByPlaceholderText(/comodat/i)
    fireEvent.change(input, { target: { value: 'Comodat' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(addDocumentType).toHaveBeenCalledWith({ company_id: 11, label: 'Comodat' }))
  })
})
