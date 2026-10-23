import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/buyback', () => ({
  buybackApi: {
    listRecords: vi.fn(() =>
      Promise.resolve({
        records: [
          {
            id: 1,
            record_code: 'BB-X',
            brand: 'BMW',
            model: '320d',
            vin: 'WBA...',
            status: 'BOUGHT',
            seller_name: 'Ion',
            advisor_name: 'Maria',
            client_asking_price_eur: 10000,
            market_price_eur: null,
            purchase_price_eur: 9500,
            is_repeat: false,
            created_at: '2026-09-24',
          },
          {
            id: 2,
            record_code: 'BB-Y',
            brand: 'Audi',
            model: 'A4',
            vin: 'WAU...',
            status: 'PENDING_EVALUATION',
            seller_name: 'Vlad',
            advisor_name: 'Ana',
            client_asking_price_eur: 8000,
            market_price_eur: 21500,
            purchase_price_eur: null,
            is_repeat: true,
            created_at: '2026-10-12',
          },
        ],
        total: 2,
        page: 1,
        per_page: 25,
      })
    ),
    getCompanies: vi.fn(() => Promise.resolve({ companies: [] })),
    getLookupOptions: vi.fn(() =>
      Promise.resolve({ hold_reasons: [{ value: 'Poze lipsă', label: 'Poze lipsă' }] })
    ),
    hold: vi.fn(() => Promise.resolve({ record: {} })),
    resume: vi.fn(() => Promise.resolve({ record: {} })),
  },
}))

// role + permissions read at render → mutate per test to exercise the gating
// matrix (admin/manager vs a plain hold-permission holder).
const auth = vi.hoisted(() => ({ role: 'Admin', permissions: {} as Record<string, boolean> }))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { role_name: auth.role, can_access_buyback: true, permissions: auth.permissions },
    isLoading: false,
  }),
}))

import BuyBack from './index'
import { buybackApi } from '@/api/buyback'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('BuyBack list page', () => {
  it('renders a record row with its status badge', async () => {
    auth.role = 'Admin'
    auth.permissions = {}
    wrap(<BuyBack />)
    // The record is BOUGHT (a resolved status), which lives under the Arhivă tab.
    fireEvent.click(await screen.findByRole('button', { name: /arhivă/i }))
    expect(await screen.findByText('BMW 320d')).toBeInTheDocument()
    expect(screen.getByText('Achiziționat')).toBeInTheDocument()
    // purchase_price_eur (9500) renders in the "Preț achiziție €" column, ro-RO formatted
    expect(screen.getByText((9500).toLocaleString('ro-RO'))).toBeInTheDocument()
  })

  it('flags a repeat-VIN record with a "Revenit" badge and shows its Preț Piață', async () => {
    auth.role = 'Admin'
    auth.permissions = {}
    wrap(<BuyBack />)
    // Audi A4 is PENDING_EVALUATION → Active tab (default); it carries is_repeat.
    expect(await screen.findByText('Audi A4')).toBeInTheDocument()
    expect(screen.getByText(/revenit/i)).toBeInTheDocument()
    // market_price_eur (21500) renders in the new "Preț Piață €" column.
    expect(screen.getByText((21500).toLocaleString('ro-RO'))).toBeInTheDocument()
  })

  it('a hold-only holder (no record.edit) gets "Suspendă" but NOT the status-change items', async () => {
    // Acquisition user: holds buyback.record.hold but NOT buyback.record.edit.
    // The active-status row must expose a Status menu with ONLY "Suspendă" — the
    // edit-gated "Redeschide"/"Schimbă status…" items must stay hidden.
    auth.role = 'Acquisition'
    auth.permissions = { 'buyback.record.hold': true }
    wrap(<BuyBack />)

    // Active tab is default; the PENDING_EVALUATION (Audi A4) row shows there.
    expect(await screen.findByText('Audi A4')).toBeInTheDocument()

    // Radix menu triggers open on pointerdown (button 0), not click. The
    // trigger's accessible name is exactly the status badge text (the row
    // itself is role=button too, so match the badge label exactly).
    fireEvent.pointerDown(screen.getByRole('button', { name: 'În evaluare' }), { button: 0 })

    expect(await screen.findByRole('menuitem', { name: /suspendă/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /schimbă status/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /redeschide/i })).not.toBeInTheDocument()
  })

  it('a non-admin holder of buyback.record.edit gets the "Schimbă status" item', async () => {
    // The status menu is matrix-driven now: any role granted buyback.record.edit
    // (not just admin/manager) can change status — assignable to whoever you want.
    auth.role = 'Acquisition'
    auth.permissions = { 'buyback.record.edit': true }
    wrap(<BuyBack />)

    expect(await screen.findByText('Audi A4')).toBeInTheDocument()
    fireEvent.pointerDown(screen.getByRole('button', { name: 'În evaluare' }), { button: 0 })
    expect(await screen.findByRole('menuitem', { name: /schimbă status/i })).toBeInTheDocument()
  })

  it('clicking a status count pill applies that status as the filter', async () => {
    auth.role = 'Admin'
    auth.permissions = {}
    wrap(<BuyBack />)
    // Active tab shows the PENDING_EVALUATION (Audi A4) record and its count pill.
    const pill = await screen.findByRole('button', { name: /1 în evaluare/i })
    fireEvent.click(pill)
    // Selecting a status collapses the per-status pills (only the total remains).
    expect(screen.queryByRole('button', { name: /1 în evaluare/i })).not.toBeInTheDocument()
    // The chosen status is pushed into the records query as the server filter.
    await waitFor(() =>
      expect(buybackApi.listRecords).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'PENDING_EVALUATION' })
      )
    )
  })

  it('clicking the total "solicitări" chip clears the status filter', async () => {
    auth.role = 'Admin'
    auth.permissions = {}
    wrap(<BuyBack />)
    fireEvent.click(await screen.findByRole('button', { name: /1 în evaluare/i }))
    // Reset back to all stări via the total chip — the per-status pills return.
    fireEvent.click(screen.getByRole('button', { name: /solicitări/i }))
    expect(await screen.findByRole('button', { name: /1 în evaluare/i })).toBeInTheDocument()
  })
})
