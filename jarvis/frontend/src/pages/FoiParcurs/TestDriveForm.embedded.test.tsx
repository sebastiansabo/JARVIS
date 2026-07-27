import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 11, company: 'PREMIUM' }] }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  getTestDrive: vi.fn(), getGeneralConditions: vi.fn().mockResolvedValue({ text: '', brand: '' }),
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
})
