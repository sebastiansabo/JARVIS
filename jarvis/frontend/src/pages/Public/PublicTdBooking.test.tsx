import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

const { getPage, submitBooking } = vi.hoisted(() => ({
  getPage: vi.fn(),
  submitBooking: vi.fn(),
}))
vi.mock('@/api/td', () => ({ tdApi: { getPage, submitBooking } }))

import PublicTdBooking from './PublicTdBooking'
import { ApiError } from '@/api/client'

const PAGE = {
  page: { title: 'Programează un test drive BMW', intro: 'Alege un interval liber.', thank_you: 'Verifică-ți inboxul pentru confirmare.' },
  cars: [{ id: 1, vin: 'WBA1234567890' }],
  slots: [
    { id: 101, car_id: 1, vin: 'WBA1234567890', starts_at: '2026-10-01T09:00:00Z', ends_at: '2026-10-01T10:00:00Z' },
    { id: 102, car_id: 1, vin: 'WBA1234567890', starts_at: '2026-10-01T11:00:00Z', ends_at: '2026-10-01T12:00:00Z' },
  ],
}

// PublicTdBooking always calls useParams() for the :slug route param, so it
// needs a Router with a matching Route ancestor — mirror the production
// mount at /td/:slug.
function wrap(initialPath = '/td/bmw-test-drive') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/td/:slug" element={<PublicTdBooking />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PublicTdBooking', () => {
  beforeEach(() => {
    getPage.mockReset()
    submitBooking.mockReset()
  })

  it('renders slots for the fetched page, grouped by car', async () => {
    getPage.mockResolvedValue(PAGE)
    wrap()
    expect(await screen.findByText('Programează un test drive BMW')).toBeInTheDocument()
    expect(screen.getByText('WBA1234567890')).toBeInTheDocument()
    expect(getPage).toHaveBeenCalledWith('bmw-test-drive')
    // Two slots rendered as pick buttons.
    expect(screen.getAllByRole('button', { name: /2026/ })).toHaveLength(2)
  })

  it('picking a slot + filling name/phone/email enables submit and fires the booking', async () => {
    getPage.mockResolvedValue(PAGE)
    submitBooking.mockResolvedValue({ booking_id: 55, status: 'pending' })
    wrap()

    const slotButtons = await screen.findAllByRole('button', { name: /2026/ })
    const submitBtn = () => screen.getByRole('button', { name: /alege un interval|trimite programarea/i })

    // Submit stays disabled until a slot + valid contact details are supplied.
    expect(submitBtn()).toBeDisabled()

    fireEvent.click(slotButtons[0])
    fireEvent.change(screen.getByPlaceholderText('Nume complet'), { target: { value: 'Ana Popescu' } })
    fireEvent.change(screen.getByPlaceholderText('Telefon'), { target: { value: '0721234567' } })
    fireEvent.change(screen.getByPlaceholderText('Email'), { target: { value: 'ana@example.com' } })

    await waitFor(() => expect(submitBtn()).not.toBeDisabled())
    fireEvent.click(submitBtn())

    await waitFor(() => expect(submitBooking).toHaveBeenCalledWith('bmw-test-drive', {
      slot_id: 101, name: 'Ana Popescu', phone: '+40721234567', email: 'ana@example.com',
    }))

    // Success → "check your email" state.
    expect(await screen.findByText('Verifică emailul')).toBeInTheDocument()
    expect(screen.getByText('Verifică-ți inboxul pentru confirmare.')).toBeInTheDocument()
  })

  it('shows the "not available" state when the page fails to load', async () => {
    getPage.mockRejectedValue(new ApiError(404, { error: 'not found' }))
    wrap()
    expect(await screen.findByText('Pagina nu este disponibilă')).toBeInTheDocument()
  })

  it('on a 409 (slot taken) clears the selection and refetches slots', async () => {
    getPage.mockResolvedValue(PAGE)
    submitBooking.mockRejectedValue(new ApiError(409, { error: 'slot taken' }))
    wrap()

    const slotButtons = await screen.findAllByRole('button', { name: /2026/ })
    fireEvent.click(slotButtons[0])
    fireEvent.change(screen.getByPlaceholderText('Nume complet'), { target: { value: 'Ana Popescu' } })
    fireEvent.change(screen.getByPlaceholderText('Telefon'), { target: { value: '0721234567' } })
    fireEvent.change(screen.getByPlaceholderText('Email'), { target: { value: 'ana@example.com' } })

    const submitBtn = () => screen.getByRole('button', { name: /trimite programarea/i })
    await waitFor(() => expect(submitBtn()).not.toBeDisabled())
    fireEvent.click(submitBtn())

    expect(await screen.findByText('Intervalul tocmai a fost ocupat. Alege altul.')).toBeInTheDocument()
    // Selection cleared → button reverts to the "pick a slot" label and refetch ran again.
    expect(screen.getByRole('button', { name: /alege un interval/i })).toBeInTheDocument()
    await waitFor(() => expect(getPage).toHaveBeenCalledTimes(2))
  })
})
