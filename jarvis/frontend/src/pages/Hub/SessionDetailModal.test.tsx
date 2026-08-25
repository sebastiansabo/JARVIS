import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { correctSession, extendReturn, discardTestDrive, deleteContract } = vi.hoisted(() => ({
  correctSession: vi.fn(), extendReturn: vi.fn(), discardTestDrive: vi.fn(), deleteContract: vi.fn(),
}))
vi.mock('@/api/foiParcurs', () => ({
  foiParcursApi: { correctSession, extendReturn, discardTestDrive, deleteContract, getContractPdfUrl: (id: number) => `/pdf/${id}` },
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
const internalWithComment = {
  ...base, client_name: null, status: 'FILLED', td_status: 'driving',
  is_internal: true, itinerary: 'Deplasare SNN – pregatiri livrare',
}

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

  it('shows a Comentariu row for an internal session that has a comment', () => {
    wrap(<SessionDetailModal session={internalWithComment as never} onClose={vi.fn()} onActivate={vi.fn()} onReturn={vi.fn()} />)
    expect(screen.getByText('Comentariu')).toBeInTheDocument()
    expect(screen.getByText('Deplasare SNN – pregatiri livrare')).toBeInTheDocument()
  })

  it('does not show a Comentariu row for a regular test drive', () => {
    wrap(<SessionDetailModal session={driving as never} onClose={vi.fn()} onActivate={vi.fn()} onReturn={vi.fn()} />)
    expect(screen.queryByText('Comentariu')).not.toBeInTheDocument()
  })

  it('shows Șterge on an internal session and deletes on confirm (any user)', async () => {
    auth.role = 'user'
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    wrap(<SessionDetailModal session={internalWithComment as never} onClose={vi.fn()} onActivate={vi.fn()} onReturn={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Șterge/ }))
    expect(confirmSpy).toHaveBeenCalled()
    await waitFor(() => expect(deleteContract).toHaveBeenCalledWith(internalWithComment.id))
    confirmSpy.mockRestore()
  })

  it('does not delete when the confirm is dismissed', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    wrap(<SessionDetailModal session={internalWithComment as never} onClose={vi.fn()} onActivate={vi.fn()} onReturn={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Șterge/ }))
    expect(deleteContract).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('hides Șterge on a regular (non-internal) test drive', () => {
    wrap(<SessionDetailModal session={driving as never} onClose={vi.fn()} onActivate={vi.fn()} onReturn={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Șterge/ })).not.toBeInTheDocument()
  })
})
