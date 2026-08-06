import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getEventParticipants = vi.fn()
vi.mock('@/api/marketing', () => ({
  marketingApi: { getEventParticipants: (...a: unknown[]) => getEventParticipants(...a) },
}))

const createBonus = vi.fn()
const updateBonus = vi.fn()
const deleteBonus = vi.fn()
const searchEmployees = vi.fn()
const getBonusTypes = vi.fn()
vi.mock('@/api/hr', () => ({
  hrApi: {
    createBonus: (...a: unknown[]) => createBonus(...a),
    updateBonus: (...a: unknown[]) => updateBonus(...a),
    deleteBonus: (...a: unknown[]) => deleteBonus(...a),
    searchEmployees: (...a: unknown[]) => searchEmployees(...a),
    getBonusTypes: (...a: unknown[]) => getBonusTypes(...a),
  },
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import ManageParticipantsDialog from './ManageParticipantsDialog'
import type { HrEvent } from '@/types/hr'

const EVENT: HrEvent = {
  id: 42, name: 'Autoworld Plus @ WFF', start_date: '2026-07-31', end_date: '2026-08-02',
  company: 'Autoworld PLUS S.R.L.', brand: null, description: null,
} as HrEvent

const PARTICIPANT = {
  id: 100, user_id: 7, user_name: 'Doja Paul-Sebastian', year: 2026, month: 8,
  participation_start: '2026-08-02', participation_end: '2026-08-02',
  bonus_days: 1, hours_free: 6, bonus_net: 150, details: null,
  allocation_month: null, bonus_type_name: null,
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

function renderDialog(props: Partial<React.ComponentProps<typeof ManageParticipantsDialog>> = {}) {
  return wrap(
    <ManageParticipantsDialog
      open
      eventId={42}
      event={EVENT}
      canAddBonus
      canDeleteBonus
      canViewAmounts
      onClose={vi.fn()}
      {...props}
    />,
  )
}

describe('ManageParticipantsDialog', () => {
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
    window.HTMLElement.prototype.releasePointerCapture = vi.fn()
  })

  beforeEach(() => {
    getEventParticipants.mockReset().mockResolvedValue({ participants: [PARTICIPANT] })
    getBonusTypes.mockReset().mockResolvedValue([
      { id: 5, name: 'Standard', amount: 150, days_per_amount: 1, description: null, is_active: true, restricted_to_user_id: null, restricted_to_user_name: null },
    ])
    createBonus.mockReset().mockResolvedValue({ success: true, id: 999 })
    updateBonus.mockReset().mockResolvedValue({ success: true })
    deleteBonus.mockReset().mockResolvedValue({ success: true })
    searchEmployees.mockReset().mockResolvedValue([])
  })

  it('renders each participant as an editable row', async () => {
    renderDialog()
    expect(await screen.findByText('Doja Paul-Sebastian')).toBeInTheDocument()
    // days input pre-filled with the stored value
    expect(await screen.findByDisplayValue('1')).toBeInTheDocument()
  })

  it('hides the Add-participant control when canAddBonus is false', async () => {
    renderDialog({ canAddBonus: false })
    await screen.findByText('Doja Paul-Sebastian')
    expect(screen.queryByRole('button', { name: /add participant/i })).not.toBeInTheDocument()
  })

  it('hides row remove controls when canDeleteBonus is false', async () => {
    renderDialog({ canDeleteBonus: false })
    await screen.findByText('Doja Paul-Sebastian')
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
  })

  it('hides the bonus amount when canViewAmounts is false', async () => {
    renderDialog({ canViewAmounts: false })
    await screen.findByText('Doja Paul-Sebastian')
    expect(screen.queryByDisplayValue('150')).not.toBeInTheDocument()
  })

  it('updates a changed participant on Save', async () => {
    const onClose = vi.fn()
    renderDialog({ onClose })
    const daysInput = await screen.findByDisplayValue('1')
    fireEvent.change(daysInput, { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(updateBonus).toHaveBeenCalledTimes(1))
    expect(updateBonus).toHaveBeenCalledWith(100, expect.objectContaining({ bonus_days: 2, event_id: 42, year: 2026, month: 8 }))
    expect(createBonus).not.toHaveBeenCalled()
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('deletes a removed participant on Save', async () => {
    renderDialog()
    await screen.findByText('Doja Paul-Sebastian')
    fireEvent.click(screen.getByRole('button', { name: /remove/i }))
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(deleteBonus).toHaveBeenCalledWith(100))
    expect(updateBonus).not.toHaveBeenCalled()
  })

  it('makes no API writes when nothing changed', async () => {
    const onClose = vi.fn()
    renderDialog({ onClose })
    await screen.findByText('Doja Paul-Sebastian')
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(updateBonus).not.toHaveBeenCalled()
    expect(createBonus).not.toHaveBeenCalled()
    expect(deleteBonus).not.toHaveBeenCalled()
  })
})
