import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 11, company: 'PREMIUM' }] }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  getTestDrive: vi.fn(), getGeneralConditions: vi.fn().mockResolvedValue({ text: '', brand: '' }),
  // 'service' is a rental type → the form shows the rental ("Predă mașina") UI.
  getDocumentTypes: vi.fn().mockResolvedValue({ types: [
    { key: 'sales', label: 'Vânzări', is_rental: false, is_default: true, is_active: true },
    { key: 'service', label: 'Mașini de curtoazie', is_rental: true, is_default: false, is_active: true },
  ] }),
} }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { name: 'Test Advisor' } }) }))
// SignatureCanvas is a lazy canvas widget backed by signature_pad, which
// throws in jsdom (no real canvas context) — stub it like TestDriveReturn.test.tsx does.
vi.mock('@/components/shared/SignatureCanvas', () => ({
  default: ({ onSave }: { onSave: (s: string) => void }) => (
    <button onClick={() => onSave('data:sig')}>sign</button>
  ),
}))

import TestDriveForm from './TestDriveForm'
import { foiParcursApi } from '@/api/foiParcurs'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('TestDriveForm embedded mode', () => {
  it('renders a Cancel affordance wired to onCancel when embedded', async () => {
    const onCancel = vi.fn()
    wrap(<TestDriveForm embedded onCancel={onCancel} onDone={vi.fn()} />)
    // In embedded mode the "back to Driving Hub" nav is replaced by an onCancel-driven control.
    const cancel = await screen.findByRole('button', { name: /închide|anulează|înapoi/i })
    cancel.click()
    expect(onCancel).toHaveBeenCalled()
  })

  it('default (no-props) mode still renders without calling onDone/onCancel', async () => {
    wrap(<TestDriveForm />)
    expect(await screen.findByText('Test Drive Nou')).toBeInTheDocument()
  })

  it('seeds the departure datetime from initialDeparture (e.g. a calendar slot)', async () => {
    wrap(<TestDriveForm embedded initialDeparture="2026-08-05T11:00" onCancel={vi.fn()} onDone={vi.fn()} />)
    expect(await screen.findByTestId('td-departure')).toHaveValue('2026-08-05T11:00')
  })

  it('planning (Planifică) flags only the minimal fields, not the activation-only ones', async () => {
    wrap(<TestDriveForm embedded onCancel={vi.fn()} onDone={vi.fn()} />)
    // Attempt to plan with nothing filled → only car/client/dates should red-flag.
    fireEvent.click(await screen.findByRole('button', { name: /planific/i }))
    // Client (plan-relevant, missing) gets the destructive ring we add…
    // (`ring-2 ring-destructive`, distinct from the Input's base
    // `aria-invalid:ring-destructive/20` variant).
    expect(screen.getByPlaceholderText(/caut[aă] client/i).className).toContain('ring-2 ring-destructive')
    // …but KM estimat (activation-only) does NOT when only planning.
    expect(screen.getByPlaceholderText(/km estima/i).className).not.toContain('ring-2 ring-destructive')
  })

  it('runs in Service context via initialDocumentType (no URL ?context=, e.g. Hub overlay)', async () => {
    vi.mocked(foiParcursApi.getVehicles).mockClear()
    wrap(<TestDriveForm embedded initialCompanyId={11} initialDocumentType="service" onCancel={vi.fn()} onDone={vi.fn()} />)
    // Service heading confirms the whole doc-type flows from the prop, not the URL.
    // (is_rental resolves from the company's document types → rental UI.)
    expect(await screen.findByText(/predare mașină de curtoazie/i)).toBeInTheDocument()
    // …and the vehicle pool query is scoped to service.
    expect(foiParcursApi.getVehicles).toHaveBeenCalledWith(false, 'service')
  })

  it('seeds the departure datetime from a ?departure= search param (desktop calendar route)', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/app/foi-parcurs/test-drive?departure=2026-08-05T14:30']}>
          <TestDriveForm />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByTestId('td-departure')).toHaveValue('2026-08-05T14:30')
  })
})
