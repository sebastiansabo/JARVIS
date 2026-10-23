import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

const { updateRecord, exportPdf } = vi.hoisted(() => ({
  updateRecord: vi.fn(() => Promise.resolve({ success: true, record: {} })),
  exportPdf: vi.fn(() => Promise.resolve()),
}))

vi.mock('@/api/buyback', () => ({
  buybackApi: {
    getRecord: vi.fn(() =>
      Promise.resolve({
        record: {
          id: 5,
          record_code: 'BB-Y',
          brand: 'Audi',
          model: 'A4',
          // A valid 17-char VIN (no I/O/Q) so the inline editor's Save enables.
          vin: 'WAUZZZ8V9KA000111',
          status: 'INITIAL_OFFER',
          seller_name: 'Dan',
          client_asking_price_eur: 12000,
          market_price_eur: 9000,
        },
        offers: [{ id: 1, offer_type: 'initial', amount_eur: 11000, client_decision: 'pending', created_at: '2026-09-24' }],
        photos: [],
        events: [{ id: 1, action: 'created', created_at: '2026-09-24', details: {} }],
      })
    ),
    updateRecord,
    exportPdf,
    // ActionPanel mounts unconditionally and fires this on render regardless of status.
    getLookupOptions: vi.fn(() => Promise.resolve({})),
    getVinHistory: vi.fn(() =>
      Promise.resolve({
        history: [
          {
            id: 99,
            record_code: 'BB-OLD',
            company_id: 10,
            company_name: 'Autoworld International',
            advisor_name: 'Arthur',
            status: 'FINAL_OFFER',
            created_at: '2026-10-14',
            client_asking_price_eur: 10000,
            market_price_eur: 9500,
            purchase_price_eur: null,
            last_offer_eur: 8500,
            last_offer_type: 'final',
            last_offer_vat: 'no_vat',
            last_offer_at: '2026-10-14',
          },
        ],
      })
    ),
  },
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { role_name: 'admin', permissions: {} }, isLoading: false }),
}))

import BuyBackDetail from './BuyBackDetail'

function wrap(entry: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/app/buyback/:id" element={<BuyBackDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('BuyBackDetail', () => {
  it('shows the vehicle, status badge, and event timeline', async () => {
    wrap('/app/buyback/5')
    expect(await screen.findByText('Audi A4')).toBeInTheDocument()
    expect(screen.getByText('Ofertă')).toBeInTheDocument()
    expect(screen.getByText('BB-Y')).toBeInTheDocument()
  })

  it('shows Preț Piață and a prior-VIN history panel when the car was evaluated before', async () => {
    wrap('/app/buyback/5')
    await screen.findByText('Audi A4')
    // Preț Piață field (market_price_eur = 9000)
    expect(screen.getByText('Preț Piață')).toBeInTheDocument()
    expect(screen.getByText((9000).toLocaleString('ro-RO') + ' €')).toBeInTheDocument()
    // History panel from the prior evaluation at International
    expect(await screen.findByText('Istoric BuyBack (același VIN)')).toBeInTheDocument()
    expect(screen.getByText('Autoworld International')).toBeInTheDocument()
    expect(screen.getByText((8500).toLocaleString('ro-RO') + ' €')).toBeInTheDocument()
  })

  it('inline-edits the Vehicul card and PUTs the record (even at a non-PENDING status)', async () => {
    updateRecord.mockClear()
    wrap('/app/buyback/5')
    await screen.findByText('Audi A4')

    // Two "Editează" buttons (Vehicul + Vânzător); the first is the Vehicul card.
    fireEvent.click(screen.getAllByText('Editează')[0])
    // Editor open: the VIN input is now rendered.
    expect(await screen.findByPlaceholderText(/17 caractere/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Salvează'))
    await waitFor(() => expect(updateRecord).toHaveBeenCalledTimes(1))
    const [id, payload] = updateRecord.mock.calls[0] as unknown as [number, Record<string, unknown>]
    expect(id).toBe(5)
    expect(payload).toMatchObject({ brand: 'Audi', model: 'A4', vin: 'WAUZZZ8V9KA000111' })
  })

  it('exports the record to PDF from the header button', async () => {
    exportPdf.mockClear()
    wrap('/app/buyback/5')
    await screen.findByText('Audi A4')
    fireEvent.click(screen.getByText('Export PDF'))
    await waitFor(() => expect(exportPdf).toHaveBeenCalledWith(5))
  })
})
