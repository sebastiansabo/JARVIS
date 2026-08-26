import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { getUsers } = vi.hoisted(() => ({ getUsers: vi.fn() }))
vi.mock('@/api/users', () => ({ usersApi: { getUsers } }))

import CorrectSessionDialog from './CorrectSessionDialog'

const base = {
  id: 1, vin: 'VF1', client_name: 'Client X', advisor_name: 'Pop Marius',
  company_name: 'AW', km_start: 100, km_end: null as number | null,
  departure_datetime: '2026-08-26T10:00', return_datetime: null, created_at: '2026-08-26T09:00',
}
const inProgress = { ...base, status: 'FILLED', td_status: 'driving' }
const finalized = { ...base, status: 'COMPLETED', td_status: 'complete' }

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('CorrectSessionDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getUsers.mockResolvedValue([{ name: 'Pop Marius', phone: '07', is_active: true, company: 'AW' }])
  })

  it('in-progress: KM final is optional — saves without it, forwarding advisor + null km_end', () => {
    const onSubmit = vi.fn()
    wrap(<CorrectSessionDialog session={inProgress as never} onClose={vi.fn()} onSubmit={onSubmit} submitting={false} />)
    expect(screen.getByText('(opțional)')).toBeInTheDocument()
    const save = screen.getByRole('button', { name: /salvează/i })
    expect(save).not.toBeDisabled()
    fireEvent.click(save)
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ advisor_name: 'Pop Marius', km_end: null }))
  })

  it('finalized: KM final stays required — save is blocked while it is blank', () => {
    wrap(<CorrectSessionDialog session={finalized as never} onClose={vi.fn()} onSubmit={vi.fn()} submitting={false} />)
    expect(screen.queryByText('(opțional)')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /salvează/i })).toBeDisabled()
  })

  it('renders the consilier value in a picker (not a free-text field)', () => {
    wrap(<CorrectSessionDialog session={inProgress as never} onClose={vi.fn()} onSubmit={vi.fn()} submitting={false} />)
    expect(screen.getByText('Consilier')).toBeInTheDocument()
    // the current advisor shows as the selected value in the Select trigger
    expect(screen.getByText('Pop Marius')).toBeInTheDocument()
  })
})
