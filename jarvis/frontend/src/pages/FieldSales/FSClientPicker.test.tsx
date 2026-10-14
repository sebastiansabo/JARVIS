import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const searchClients = vi.fn()
const createClient = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: {
    searchClients: (...a: unknown[]) => searchClients(...a),
    createClient: (...a: unknown[]) => createClient(...a),
  },
}))
import FSClientPicker from './FSClientPicker'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('FSClientPicker', () => {
  beforeEach(() => { searchClients.mockReset(); createClient.mockReset() })

  it('searches and picks an existing client', async () => {
    searchClients.mockResolvedValue({ success: true, count: 1, clients: [{ id: 42, display_name: 'ACME SRL', client_type: 'company', city: 'Cluj' }] })
    const onPick = vi.fn()
    wrap(<FSClientPicker companyId={7} onPick={onPick} />)
    fireEvent.change(screen.getByPlaceholderText(/cauta client/i), { target: { value: 'acm' } })
    fireEvent.click(await screen.findByText('ACME SRL'))
    expect(onPick).toHaveBeenCalledWith({ id: 42, display_name: 'ACME SRL' })
  })

  it('does NOT search when companyId is 0 (tenant guard)', async () => {
    const onPick = vi.fn()
    wrap(<FSClientPicker companyId={0} onPick={onPick} />)
    fireEvent.change(screen.getByPlaceholderText(/cauta client/i), { target: { value: 'acme' } })
    await new Promise((r) => setTimeout(r, 20))
    expect(searchClients).not.toHaveBeenCalled()
  })

  it('creates a new client and picks it', async () => {
    createClient.mockResolvedValue({ success: true, client: { id: 99, display_name: 'Ion Pop', company_id: 7 } })
    const onPick = vi.fn()
    wrap(<FSClientPicker companyId={7} onPick={onPick} />)
    fireEvent.click(screen.getByRole('button', { name: /client nou/i }))
    fireEvent.change(screen.getByPlaceholderText(/nume client/i), { target: { value: 'Ion Pop' } })
    fireEvent.click(screen.getByRole('button', { name: /^creeaz/i }))
    await waitFor(() => expect(onPick).toHaveBeenCalledWith({ id: 99, display_name: 'Ion Pop' }))
    expect(createClient).toHaveBeenCalledWith({ display_name: 'Ion Pop', cui: undefined, phone: undefined, city: undefined, client_type: 'person', company_id: 7 })
  })

  it('shows the duplicate notice and picks the existing client only after confirm', async () => {
    createClient.mockResolvedValue({ success: true, duplicate: true, client: { id: 5, display_name: 'ACME SRL', company_id: 7 } })
    const onPick = vi.fn()
    wrap(<FSClientPicker companyId={7} onPick={onPick} />)
    fireEvent.click(screen.getByRole('button', { name: /client nou/i }))
    fireEvent.change(screen.getByPlaceholderText(/nume client/i), { target: { value: 'ACME SRL' } })
    fireEvent.click(screen.getByRole('button', { name: /^creeaz/i }))
    expect(await screen.findByText(/exist[ăa] deja un client cu acest nume/i)).toBeInTheDocument()
    expect(onPick).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /continu/i }))
    expect(onPick).toHaveBeenCalledWith({ id: 5, display_name: 'ACME SRL' })
  })

  it('returns to the editable create form from the duplicate notice via Inapoi without picking', async () => {
    createClient.mockResolvedValue({ success: true, duplicate: true, client: { id: 5, display_name: 'ACME SRL', company_id: 7 } })
    const onPick = vi.fn()
    wrap(<FSClientPicker companyId={7} onPick={onPick} />)
    fireEvent.click(screen.getByRole('button', { name: /client nou/i }))
    fireEvent.change(screen.getByPlaceholderText(/nume client/i), { target: { value: 'ACME SRL' } })
    fireEvent.click(screen.getByRole('button', { name: /^creeaz/i }))
    expect(await screen.findByText(/exist[ăa] deja un client cu acest nume/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /inapoi/i }))
    expect(screen.getByPlaceholderText(/nume client/i)).toBeInTheDocument()
    expect(onPick).not.toHaveBeenCalled()
  })
})
