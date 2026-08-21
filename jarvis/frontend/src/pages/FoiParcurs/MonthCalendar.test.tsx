import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import MonthCalendar from './MonthCalendar'

// A same-day driving session and a multi-day planned one, in August 2026.
const sameDay = {
  id: 1, client_name: 'Ion Pop', advisor_name: 'Adv', vin: 'VF1', status: 'FILLED', td_status: 'driving',
  departure_datetime: '2026-08-04T09:00', return_datetime: '2026-08-04T17:00', is_internal: false,
}
const multiDay = {
  id: 2, client_name: 'Multi Client', vin: 'VF2', status: 'PLANNED',
  departure_datetime: '2026-08-11T13:29', return_datetime: '2026-08-21T14:06', is_internal: false,
}
// Still out — no return set yet (e.g. an ongoing drive).
const ongoing = {
  id: 3, client_name: 'Vaju Stefan', vin: 'VF1', status: 'FILLED', td_status: 'driving',
  departure_datetime: '2026-08-04T19:45', return_datetime: null, is_internal: false,
}
const byDay = new Map<string, any[]>([
  ['2026-08-04', [sameDay, ongoing]],
  ['2026-08-11', [multiDay]],
])
const vinVehicle = new Map<string, any>([
  ['VF1', { vin: 'VF1', mark: 'Audi', model: 'Q8' }],
  ['VF2', { vin: 'VF2', mark: 'VW', model: 'Caravelle' }],
])

function renderMc(overrides: Record<string, unknown> = {}) {
  const props = {
    monthDate: new Date(2026, 7, 15),
    byDay,
    vinVehicle,
    onOpenDetail: vi.fn(),
    onAdd: vi.fn(),
    onRescheduleToDay: vi.fn(),
    dayTestIdPrefix: 'mc-day',
    ...overrides,
  }
  render(<MonthCalendar {...(props as never)} />)
  return props
}

describe('MonthCalendar', () => {
  it('shows each session’s full period — times for a same-day drive, dates for a multi-day one', () => {
    renderMc()
    expect(screen.getByText('09:00 → 17:00')).toBeInTheDocument()
    expect(screen.getByText(/13:29 → .*14:06/)).toBeInTheDocument()
  })

  it('renders an open interval (with the departure date) for a still-out session', () => {
    renderMc()
    // No return set → "4 aug. 19:45 → —", so an ongoing drive still reads as a range.
    expect(screen.getByText(/19:45 → —/)).toBeInTheDocument()
  })

  it('lists the whole month by default and narrows to a clicked day', () => {
    renderMc()
    // Toată luna (default) → both days listed.
    expect(screen.getByText('Ion Pop')).toBeInTheDocument()
    expect(screen.getByText('Multi Client')).toBeInTheDocument()
    // Clicking a day cell narrows the list to that day.
    fireEvent.click(screen.getByTestId('mc-day-2026-08-04'))
    expect(screen.getByText('Ion Pop')).toBeInTheDocument()
    expect(screen.queryByText('Multi Client')).not.toBeInTheDocument()
  })

  it('highlights a session’s day span when its row is clicked', () => {
    renderMc()
    expect(screen.getByTestId('mc-day-2026-08-04').className).not.toContain('ring-blue-500')
    fireEvent.click(screen.getByText('Ion Pop'))
    expect(screen.getByTestId('mc-day-2026-08-04').className).toContain('ring-blue-500')
  })

  it('opens the detail modal via the row’s detail button (not the row-body click)', () => {
    const props = renderMc()
    fireEvent.click(screen.getAllByLabelText('Detalii sesiune')[0]) // first listed day = 04 Aug
    expect(props.onOpenDetail).toHaveBeenCalledWith(sameDay)
  })
})
