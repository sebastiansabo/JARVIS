import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const { cancel } = vi.hoisted(() => ({ cancel: vi.fn() }))
vi.mock('@/api/td', () => ({ tdApi: { cancel } }))

import TdCancel from './TdCancel'
import { ApiError } from '@/api/client'

function wrap(initialPath = '/td/cancel?token=abc') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <TdCancel />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TdCancel', () => {
  beforeEach(() => {
    cancel.mockReset()
  })

  it('renders idle state with a button and does not call the API on mount', async () => {
    wrap()
    expect(screen.getByText('Anulează programarea')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Anulează test drive' })).toBeInTheDocument()
    // Give any accidental effect a tick to fire, then assert it never did.
    await new Promise((r) => setTimeout(r, 0))
    expect(cancel).not.toHaveBeenCalled()
  })

  it('clicking the button calls cancel with the token and renders the success state', async () => {
    cancel.mockResolvedValue({ status: 'cancelled' })
    wrap()

    fireEvent.click(screen.getByRole('button', { name: 'Anulează test drive' }))

    await waitFor(() => expect(cancel).toHaveBeenCalledWith('abc'))
    expect(await screen.findByText('Programare anulată.')).toBeInTheDocument()
  })

  it('renders the gone state on a 410 ApiError', async () => {
    cancel.mockRejectedValue(new ApiError(410, { error: 'expired' }))
    wrap()

    fireEvent.click(screen.getByRole('button', { name: 'Anulează test drive' }))

    expect(await screen.findByText('Linkul a expirat.')).toBeInTheDocument()
  })

  it('renders the generic error state on other failures', async () => {
    cancel.mockRejectedValue(new ApiError(500, { error: 'boom' }))
    wrap()

    fireEvent.click(screen.getByRole('button', { name: 'Anulează test drive' }))

    expect(await screen.findByText('A apărut o eroare.')).toBeInTheDocument()
  })

  it('disables the button when no token is present', () => {
    wrap('/td/cancel')
    expect(screen.getByRole('button', { name: 'Anulează test drive' })).toBeDisabled()
  })
})
