import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { correctSession, extendReturn, discardTestDrive } = vi.hoisted(() => ({
  correctSession: vi.fn(), extendReturn: vi.fn(), discardTestDrive: vi.fn(),
}))
vi.mock('@/api/foiParcurs', () => ({
  foiParcursApi: { correctSession, extendReturn, discardTestDrive, getContractPdfUrl: (id: number) => `/pdf/${id}` },
}))

// role read at render → flip auth.role between tests to exercise the admin gate.
const auth = vi.hoisted(() => ({ role: 'user' }))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { role_name: auth.role } }),
}))

import SessionDetailModal from './SessionDetailModal'

const base = {
  id: 7, vin: 'VF1', client_name: 'Ion Pop', advisor_name: 'Ana', km_start: 100, km_end: 100,
  departure_datetime: '2026-08-17T10:00', return_datetime: '2026-08-17T12:00',
}
const planned = { ...base, status: 'PLANNED' }
const driving = { ...base, status: 'FILLED', td_status: 'driving' }

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('SessionDetailModal', () => {
  beforeEach(() => { auth.role = 'user'; vi.clearAllMocks() })

  it('planned session shows Începe + Renunță (no Retur) and Începe calls onActivate', () => {
    const onActivate = vi.fn()
    wrap(<SessionDetailModal session={planned as never} onClose={vi.fn()} onActivate={onActivate} onReturn={vi.fn()} />)
    expect(screen.getByText('Detalii sesiune')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Începe sesiunea/ }))
    expect(onActivate).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: /Renunță/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Retur/ })).not.toBeInTheDocument()
  })

  it('driving session shows Retur + Descarcă PDF + Prelungește (no Începe) and Retur calls onReturn', () => {
    const onReturn = vi.fn()
    wrap(<SessionDetailModal session={driving as never} onClose={vi.fn()} onActivate={vi.fn()} onReturn={onReturn} />)
    fireEvent.click(screen.getByRole('button', { name: /Retur/ }))
    expect(onReturn).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Descarcă PDF')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Prelungește/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Începe/ })).not.toBeInTheDocument()
  })

  it('hides Corectează for a non-admin', () => {
    auth.role = 'user'
    wrap(<SessionDetailModal session={driving as never} onClose={vi.fn()} onActivate={vi.fn()} onReturn={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Corectează/ })).not.toBeInTheDocument()
  })

  it('shows Corectează for an admin', () => {
    auth.role = 'admin'
    wrap(<SessionDetailModal session={driving as never} onClose={vi.fn()} onActivate={vi.fn()} onReturn={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Corectează/ })).toBeInTheDocument()
  })
})
