import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getMyVisits = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: { getMyVisits: (...a: unknown[]) => getMyVisits(...a) },
}))

import FieldSalesCalendar from './FieldSalesCalendar'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const pad = (n: number) => String(n).padStart(2, '0')

describe('FieldSalesCalendar', () => {
  // usePersistedState('hub-fs-cal-view') is backed by localStorage; clear it
  // between tests so the persisted view doesn't leak (the week/day switch
  // test would otherwise leave 'day' and start the next test off-default).
  beforeEach(() => localStorage.clear())

  it('shows a day indicator, lists that day\'s visits on selection, and opens on click', async () => {
    // A day guaranteed to fall inside the current month's grid, computed
    // relative to "today" so the test stays valid regardless of when it runs.
    const now = new Date()
    const dateKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-15`
    const visits = [
      { id: 101, kam_id: 1, client_id: 1, planned_date: dateKey, planned_time: '09:00', visit_type: 'general', status: 'planned', client_name: 'Client A', kam_name: 'X' },
      { id: 102, kam_id: 1, client_id: 2, planned_date: dateKey, planned_time: '11:00', visit_type: 'general', status: 'completed', client_name: 'Client B', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: dateKey, date_to: dateKey })

    const onOpen = vi.fn()
    wrap(<FieldSalesCalendar onOpen={onOpen} onAdd={vi.fn()} />)

    const dayCell = await screen.findByTestId(`day-${dateKey}`)
    await waitFor(() => expect(dayCell.querySelectorAll('[data-testid="day-dot"]').length).toBe(2))

    fireEvent.click(dayCell)

    expect(await screen.findByText('Client A')).toBeInTheDocument()
    expect(screen.getByText('Client B')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Client A'))
    expect(onOpen).toHaveBeenCalledWith(101)
  })

  it('shows the empty state and no indicator when there are no visits', async () => {
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: '', date_to: '' })
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)
    expect(await screen.findByText(/nicio vizita/i)).toBeInTheDocument()
    expect(screen.queryByTestId('day-dot')).not.toBeInTheDocument()
  })

  it('renders the Lună/Săptămână/Zi view switcher', async () => {
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: '', date_to: '' })
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByText(/nicio vizita/i)
    expect(screen.getByRole('button', { name: 'Lună' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Săptămână' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zi' })).toBeInTheDocument()
  })

  it('calls onAdd with the selected day\'s date when "+ Adaugă vizită" is clicked', async () => {
    const now = new Date()
    const dateKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-15`
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: '', date_to: '' })
    const onAdd = vi.fn()
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={onAdd} />)

    const dayCell = await screen.findByTestId(`day-${dateKey}`)
    fireEvent.click(dayCell)

    fireEvent.click(await screen.findByRole('button', { name: /adaug[aă] vizit[aă]/i }))
    expect(onAdd).toHaveBeenCalledWith(dateKey)
  })

  it('selects a day via keyboard (Enter) on its cell', async () => {
    const now = new Date()
    const dateKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-15`
    const visits = [
      { id: 201, kam_id: 1, client_id: 1, planned_date: dateKey, planned_time: '10:00', visit_type: 'general', status: 'planned', client_name: 'Kbd Client', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: dateKey, date_to: dateKey })
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)

    const dayCell = await screen.findByTestId(`day-${dateKey}`)
    fireEvent.keyDown(dayCell, { key: 'Enter' })
    expect(await screen.findByText('Kbd Client')).toBeInTheDocument()
  })

  it('calls onAdd with a cell\'s date when its hover "+" affordance is clicked, without selecting the day', async () => {
    const now = new Date()
    const dateKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-15`
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: '', date_to: '' })
    const onAdd = vi.fn()
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={onAdd} />)

    const dayCell = await screen.findByTestId(`day-${dateKey}`)
    const addAffordance = dayCell.querySelector('[data-testid="day-add"]') as HTMLElement
    expect(addAffordance).toBeTruthy()
    fireEvent.click(addAffordance)

    expect(onAdd).toHaveBeenCalledWith(dateKey)
    // Selecting via the cell's own "+" must not also select the day (no
    // duplicate call and no visit-list re-render triggered by setPicked).
    expect(onAdd).toHaveBeenCalledTimes(1)
  })

  it('renders a Săptămână/Zi time-grid (hour gutter) instead of a placeholder', async () => {
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: '', date_to: '' })
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByText(/nicio vizita/i)

    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))
    expect(await screen.findByText('07:00')).toBeInTheDocument()
    expect(screen.queryByText(/în curând/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Zi' }))
    expect(await screen.findByText('07:00')).toBeInTheDocument()
  })

  it('renders a timed visit block on the week grid, opens it on click, and adds a visit on an empty-slot click', async () => {
    // "Today" is always inside the week-view's 7-day window (week is
    // computed from the current anchor, which defaults to now), so no
    // startOfWeek duplication is needed here.
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const visits = [
      { id: 301, kam_id: 1, client_id: 1, planned_date: todayKey, planned_time: '09:00', planned_end_time: '10:30', visit_type: 'general', status: 'planned', client_name: 'Grid Client', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: todayKey, date_to: todayKey })

    const onOpen = vi.fn()
    const onAdd = vi.fn()
    wrap(<FieldSalesCalendar onOpen={onOpen} onAdd={onAdd} />)

    // Sanity: month view (the default) already has the data loaded.
    await screen.findByText('Grid Client')

    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    // top = minToY(540) = 96px, height = minToY(630) - 96 = 72px (1.5h block).
    const block = await screen.findByTestId('fs-block-301')
    expect(block).toHaveStyle({ top: '96px', height: '72px' })

    fireEvent.click(block)
    expect(onOpen).toHaveBeenCalledWith(301)
    expect(onAdd).not.toHaveBeenCalled()

    // Empty-slot click: jsdom never lays elements out, so the column's
    // getBoundingClientRect is mocked to a known `top` and the click's
    // `clientY` is set to `top + offsetY` — the component reads
    // `e.clientY - rect.top` as the click offset within the column. An
    // offsetY of 192px = minToY(660) = 11:00, snapped exactly.
    const col = screen.getByTestId(`fs-col-${todayKey}`)
    vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
      top: 100, bottom: 500, height: 400, left: 0, right: 300, width: 300, x: 0, y: 100, toJSON: () => {},
    } as DOMRect)
    fireEvent.click(col, { clientY: 100 + 192 })
    expect(onAdd).toHaveBeenCalledWith(todayKey, '11:00', '12:00')
    expect(onAdd).toHaveBeenCalledTimes(1)
  })
})
