import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { listBookings, editBooking, deleteBooking, listOpenSlots, reassignAdvisor } = vi.hoisted(() => ({
  listBookings: vi.fn(), editBooking: vi.fn(), deleteBooking: vi.fn(),
  listOpenSlots: vi.fn(), reassignAdvisor: vi.fn(),
}))
vi.mock('@/api/tdAdmin', () => ({
  tdAdminApi: { listBookings, editBooking, deleteBooking, listOpenSlots, reassignAdvisor },
}))

import TdBookingsPanel from './TdBookingsPanel'

const BOOKING = {
  id: 5, page_id: 1, slot_id: 100, car_id: 10, customer_name: 'Roxana Biris',
  customer_phone_e164: '+40738764546', customer_email: 'roxana@ex.com', crm_client_id: 9,
  foi_de_parcurs_id: 77, advisor_user_id: null, status: 'pending_confirm',
  expires_at: '2099-01-01T00:00:00Z', confirmed_at: null, cancelled_at: null,
  created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z',
}
const USERS = [{ id: 3, name: 'Ion Pop', role_id: 1, role_name: 'staff', is_active: true }] as never

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <TdBookingsPanel pageId={1} users={USERS} />
    </QueryClientProvider>,
  )
}

describe('TdBookingsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listBookings.mockResolvedValue({ bookings: [BOOKING] })
    listOpenSlots.mockResolvedValue({ slots: [
      { id: 200, car_id: 20, vin: 'VF1', starts_at: '2026-10-01T14:00:00', ends_at: '2026-10-01T14:30:00', mark: 'Audi', model: 'Q8' },
    ] })
    editBooking.mockResolvedValue({ ok: true, booking: BOOKING })
    deleteBooking.mockResolvedValue({ ok: true })
  })

  it('sends only the changed fields via editBooking (untouched ones omitted)', async () => {
    wrap()
    fireEvent.click(await screen.findByLabelText('Editează rezervarea'))
    // Prefilled from the booking; change only the name + email.
    const nameInput = await screen.findByLabelText('Nume client')
    expect(nameInput).toHaveValue('Roxana Biris')
    fireEvent.change(nameInput, { target: { value: 'Roxana Maria Biris' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@ex.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvează' }))
    await waitFor(() => expect(editBooking).toHaveBeenCalledTimes(1))
    // Phone was left untouched → not in the payload.
    expect(editBooking).toHaveBeenCalledWith(5, { name: 'Roxana Maria Biris', email: 'new@ex.com' })
  })

  it('deletes a reservation after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    wrap()
    fireEvent.click(await screen.findByLabelText('Șterge rezervarea'))
    await waitFor(() => expect(deleteBooking).toHaveBeenCalledWith(5))
  })

  it('does not delete when the confirm is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    wrap()
    fireEvent.click(await screen.findByLabelText('Șterge rezervarea'))
    expect(deleteBooking).not.toHaveBeenCalled()
  })
})
