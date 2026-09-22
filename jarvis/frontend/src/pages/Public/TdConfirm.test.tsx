import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const { confirm } = vi.hoisted(() => ({ confirm: vi.fn() }))
vi.mock('@/api/td', () => ({ tdApi: { confirm } }))

import TdConfirm from './TdConfirm'
import { ApiError } from '@/api/client'

function wrap(initialPath = '/td/confirm?token=abc') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <TdConfirm />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TdConfirm', () => {
  beforeEach(() => {
    confirm.mockReset()
  })

  it('renders idle state with a button and does not call the API on mount', async () => {
    wrap()
    expect(screen.getByText('Confirmă programarea')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmă test drive' })).toBeInTheDocument()
    // Give any accidental effect a tick to fire, then assert it never did.
    await new Promise((r) => setTimeout(r, 0))
    expect(confirm).not.toHaveBeenCalled()
  })

  it('clicking the button calls confirm with the token and renders the success state', async () => {
    confirm.mockResolvedValue({ status: 'confirmed' })
    wrap()

    fireEvent.click(screen.getByRole('button', { name: 'Confirmă test drive' }))

    await waitFor(() => expect(confirm).toHaveBeenCalledWith('abc'))
    expect(await screen.findByText('Programare confirmată! Ne vedem la eveniment.')).toBeInTheDocument()
  })

  it('renders the gone state on a 410 ApiError', async () => {
    confirm.mockRejectedValue(new ApiError(410, { error: 'expired' }))
    wrap()

    fireEvent.click(screen.getByRole('button', { name: 'Confirmă test drive' }))

    expect(await screen.findByText('Linkul a expirat sau a fost deja folosit.')).toBeInTheDocument()
  })

  it('renders the conflict state on a 409 ApiError', async () => {
    confirm.mockRejectedValue(new ApiError(409, { error: 'slot taken' }))
    wrap()

    fireEvent.click(screen.getByRole('button', { name: 'Confirmă test drive' }))

    expect(await screen.findByText('Ne pare rău, mașina nu mai este disponibilă pentru acest interval.')).toBeInTheDocument()
  })

  it('renders the generic error state on other failures', async () => {
    confirm.mockRejectedValue(new ApiError(500, { error: 'boom' }))
    wrap()

    fireEvent.click(screen.getByRole('button', { name: 'Confirmă test drive' }))

    expect(await screen.findByText('A apărut o eroare. Încearcă din nou.')).toBeInTheDocument()
  })

  it('disables the button when no token is present', () => {
    wrap('/td/confirm')
    expect(screen.getByRole('button', { name: 'Confirmă test drive' })).toBeDisabled()
  })
})
