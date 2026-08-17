import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Company (persoană juridică) parity with the mobile client form: a toggle that
// reveals Denumire firmă + CUI and sends is_company/company_name/cui to the
// shared /crm-clients endpoint (backend sets client_type='company').
const { createCrmClient } = vi.hoisted(() => ({
  createCrmClient: vi.fn().mockResolvedValue({ success: true, client: { id: 42, display_name: 'ACME SRL', phone: '0712345678' } }),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { createCrmClient } }))

import { CreateClientPanel } from './CreateClientPanel'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('CreateClientPanel company toggle', () => {
  beforeEach(() => createCrmClient.mockClear())

  it('hides company fields by default and reveals them when toggled', () => {
    wrap(<CreateClientPanel prefill={null} onCancel={() => {}} onCreated={() => {}} />)
    expect(screen.queryByPlaceholderText('Denumire firmă')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByPlaceholderText('Denumire firmă')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('CUI / CIF')).toBeInTheDocument()
  })

  it('sends is_company + company_name + cui when creating a company client', async () => {
    wrap(<CreateClientPanel prefill={null} onCancel={() => {}} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.change(screen.getByPlaceholderText('Nume și prenume'), { target: { value: 'Ion Pop' } })
    fireEvent.change(screen.getByPlaceholderText('0721 234 567'), { target: { value: '0712345678' } })
    fireEvent.change(screen.getByPlaceholderText('Denumire firmă'), { target: { value: 'ACME SRL' } })
    fireEvent.change(screen.getByPlaceholderText('CUI / CIF'), { target: { value: 'RO12345' } })
    fireEvent.click(screen.getByRole('button', { name: /creează client/i }))
    await waitFor(() => expect(createCrmClient).toHaveBeenCalled())
    // Default +40 dial code is applied and the trunk 0 is stripped → E.164.
    expect(createCrmClient).toHaveBeenCalledWith(expect.objectContaining({
      display_name: 'Ion Pop', phone: '+40712345678',
      is_company: true, company_name: 'ACME SRL', cui: 'RO12345',
    }))
  })

  it('omits company fields when the toggle stays off', async () => {
    wrap(<CreateClientPanel prefill={null} onCancel={() => {}} onCreated={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('Nume și prenume'), { target: { value: 'Ana' } })
    fireEvent.change(screen.getByPlaceholderText('0721 234 567'), { target: { value: '0712345678' } })
    fireEvent.click(screen.getByRole('button', { name: /creează client/i }))
    await waitFor(() => expect(createCrmClient).toHaveBeenCalled())
    const arg = createCrmClient.mock.calls[0][0]
    expect(arg.is_company).toBeUndefined()
    expect(arg.company_name).toBeUndefined()
    expect(arg.cui).toBeUndefined()
  })
})
