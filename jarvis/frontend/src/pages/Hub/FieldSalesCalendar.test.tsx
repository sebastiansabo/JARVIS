import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getMyVisits = vi.fn()
const updateVisit = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: {
    getMyVisits: (...a: unknown[]) => getMyVisits(...a),
    updateVisit: (...a: unknown[]) => updateVisit(...a),
  },
}))

import FieldSalesCalendar from './FieldSalesCalendar'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const pad = (n: number) => String(n).padStart(2, '0')
const keyOf = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
// Mirror the component's Monday-based week start + day arithmetic so alignment
// tests can put two visits on distinct days that are both inside the current
// week-view window (anchor defaults to now).
const startOfWeek = (d: Date) => { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x }
const addDaysDate = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }

// jsdom (as of v26) doesn't implement the PointerEvent constructor, so
// `fireEvent.pointerDown(el, { clientY, pointerId })` silently drops both
// properties — event-map.js falls back to the plain `Event` constructor,
// which ignores unrecognized init-dict members, leaving `e.clientY`/
// `e.pointerId` undefined inside the handler. Build the event on a
// `MouseEvent` instead (jsdom supports `clientY` there) and attach
// `pointerId` manually; React's synthetic pointer-event wrapper copies both
// properties off the native event by name, not by checking its constructor,
// so the component under test sees a normal PointerEvent-shaped object.
function firePointer(el: Element, type: 'pointerdown' | 'pointermove' | 'pointerup', clientY: number, pointerId = 1) {
  const event = new MouseEvent(type, { clientY, bubbles: true, cancelable: true })
  Object.defineProperty(event, 'pointerId', { value: pointerId, configurable: true })
  fireEvent(el, event)
}

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

    // Empty-slot click (no drag movement): jsdom never lays elements out, so
    // the column's getBoundingClientRect is mocked to a known `top`, and
    // setPointerCapture/releasePointerCapture (unimplemented in jsdom) are
    // stubbed so the pointerdown/pointerup handlers don't throw. `clientY` is
    // set to `top + offsetY` — the component reads `e.clientY - rect.top` as
    // the pointer offset within the column. An offsetY of 192px =
    // minToY(660) = 11:00, snapped exactly. A pointerdown+pointerup with no
    // intervening pointermove is treated as a plain click → 1h default.
    const col = screen.getByTestId(`fs-col-${todayKey}`)
    vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
      top: 100, bottom: 500, height: 400, left: 0, right: 300, width: 300, x: 0, y: 100, toJSON: () => {},
    } as DOMRect)
    col.setPointerCapture = vi.fn()
    col.releasePointerCapture = vi.fn()
    firePointer(col, 'pointerdown', 100 + 192)
    firePointer(col, 'pointerup', 100 + 192)
    expect(onAdd).toHaveBeenCalledWith(todayKey, '11:00', '12:00')
    expect(onAdd).toHaveBeenCalledTimes(1)
  })

  it('creates a visit via drag-to-create on the time-grid, snapped to 30 min', async () => {
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: todayKey, date_to: todayKey })

    const onAdd = vi.fn()
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={onAdd} />)

    await screen.findByRole('button', { name: /adaug[aă] vizit[aă]/i })
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    // Same rect mock as the empty-slot-click test. 09:00 = minToY(540) = 96px
    // offset; 10:30 = minToY(630) = 168px offset.
    const col = await screen.findByTestId(`fs-col-${todayKey}`)
    vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
      top: 100, bottom: 500, height: 400, left: 0, right: 300, width: 300, x: 0, y: 100, toJSON: () => {},
    } as DOMRect)
    col.setPointerCapture = vi.fn()
    col.releasePointerCapture = vi.fn()

    firePointer(col, 'pointerdown', 100 + 96)
    firePointer(col, 'pointermove', 100 + 168)
    firePointer(col, 'pointerup', 100 + 168)

    expect(onAdd).toHaveBeenCalledWith(todayKey, '09:00', '10:30')
    expect(onAdd).toHaveBeenCalledTimes(1)
  })

  it('creates a 1h visit via pointerdown+pointerup with no movement (click-equivalent) at 08:00', async () => {
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: todayKey, date_to: todayKey })

    const onAdd = vi.fn()
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={onAdd} />)

    await screen.findByRole('button', { name: /adaug[aă] vizit[aă]/i })
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    // 08:00 = minToY(480) = 48px offset.
    const col = await screen.findByTestId(`fs-col-${todayKey}`)
    vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
      top: 100, bottom: 500, height: 400, left: 0, right: 300, width: 300, x: 0, y: 100, toJSON: () => {},
    } as DOMRect)
    col.setPointerCapture = vi.fn()
    col.releasePointerCapture = vi.fn()

    firePointer(col, 'pointerdown', 100 + 48)
    firePointer(col, 'pointerup', 100 + 48)

    expect(onAdd).toHaveBeenCalledWith(todayKey, '08:00', '09:00')
    expect(onAdd).toHaveBeenCalledTimes(1)
  })

  it('clamps a drag that ends ABOVE the grid top to HOUR_START (07:00)', async () => {
    // A captured pointer keeps reporting coordinates after leaving the column,
    // so a drag whose endpoint is above the column top yields a negative
    // offset → a negative/pre-07:00 minute. It must clamp to 07:00, never
    // emit a malformed time like "-2:-30".
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: todayKey, date_to: todayKey })

    const onAdd = vi.fn()
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={onAdd} />)

    await screen.findByRole('button', { name: /adaug[aă] vizit[aă]/i })
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    const col = await screen.findByTestId(`fs-col-${todayKey}`)
    vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
      top: 100, bottom: 500, height: 400, left: 0, right: 300, width: 300, x: 0, y: 100, toJSON: () => {},
    } as DOMRect)
    col.setPointerCapture = vi.fn()
    col.releasePointerCapture = vi.fn()

    // pointerdown at 09:00 (offset 96px), pointermove/up 200px ABOVE the
    // column top (clientY 100 - 100 = 0 → offset -100). start clamps to 07:00.
    firePointer(col, 'pointerdown', 100 + 96)
    firePointer(col, 'pointermove', 100 - 100)
    firePointer(col, 'pointerup', 100 - 100)

    expect(onAdd).toHaveBeenCalledWith(todayKey, '07:00', '09:00')
    expect(onAdd).toHaveBeenCalledTimes(1)
  })

  it('clamps a drag that ends BELOW the grid bottom to HOUR_END (21:00)', async () => {
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: todayKey, date_to: todayKey })

    const onAdd = vi.fn()
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={onAdd} />)

    await screen.findByRole('button', { name: /adaug[aă] vizit[aă]/i })
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    const col = await screen.findByTestId(`fs-col-${todayKey}`)
    vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
      top: 100, bottom: 500, height: 400, left: 0, right: 300, width: 300, x: 0, y: 100, toJSON: () => {},
    } as DOMRect)
    col.setPointerCapture = vi.fn()
    col.releasePointerCapture = vi.fn()

    // pointerdown at 09:00 (offset 96px), pointermove/up far below the grid
    // (offset 2000px, well past 21:00). end clamps to 21:00.
    firePointer(col, 'pointerdown', 100 + 96)
    firePointer(col, 'pointermove', 100 + 2000)
    firePointer(col, 'pointerup', 100 + 2000)

    expect(onAdd).toHaveBeenCalledWith(todayKey, '09:00', '21:00')
    expect(onAdd).toHaveBeenCalledTimes(1)
  })

  it('renders an untimed visit in the shared "Fără oră" band and opens it on click', async () => {
    const now = new Date()
    const todayKey = keyOf(now)
    const visits = [
      // No planned_time → belongs in the all-day band, not the hour-grid.
      { id: 501, kam_id: 1, client_id: 1, planned_date: todayKey, visit_type: 'general', status: 'planned', client_name: 'Untimed Client', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: todayKey, date_to: todayKey })

    const onOpen = vi.fn()
    wrap(<FieldSalesCalendar onOpen={onOpen} onAdd={vi.fn()} />)

    // Wait for the (default) month view's query to settle before switching, so
    // the week-view render doesn't overlap an unflushed state update.
    await screen.findByRole('button', { name: /adaug[aă] vizit[aă]/i })
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    const block = await screen.findByTestId('fs-block-501')
    expect(screen.getByText(/f[aă]r[aă] or[aă]/i)).toBeInTheDocument()
    fireEvent.click(block)
    expect(onOpen).toHaveBeenCalledWith(501)
  })

  it('keeps untimed visits in the shared all-day band, out of every hour-grid column', async () => {
    // Two distinct days in the current week: day A carries an untimed visit,
    // day B a timed 09:00 one. The structural invariant the alignment fix
    // establishes is that untimed content lives in the shared all-day band
    // (a separate row ABOVE the hour-grid), never inside a day column's
    // hour-grid box — so it can never push a column's hour lines/blocks down.
    // This is deterministic in jsdom (no layout engine needed): if untimed
    // content were moved back inside a column, it would appear inside
    // fs-hourgrid and this test would fail.
    const weekStart = startOfWeek(new Date())
    const dayA = keyOf(weekStart)
    const dayB = keyOf(addDaysDate(weekStart, 1))
    const visits = [
      { id: 601, kam_id: 1, client_id: 1, planned_date: dayA, visit_type: 'general', status: 'planned', client_name: 'Untimed A', kam_name: 'X' },
      { id: 602, kam_id: 1, client_id: 2, planned_date: dayB, planned_time: '09:00', planned_end_time: '10:00', visit_type: 'general', status: 'planned', client_name: 'Timed B', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: dayA, date_to: dayB })

    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)

    await screen.findByRole('button', { name: /adaug[aă] vizit[aă]/i })
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    // 1) The untimed visit renders INSIDE the shared all-day band…
    const band = await screen.findByTestId('fs-allday-band')
    expect(within(band).getByText('Untimed A')).toBeInTheDocument()

    // 2) …and NOT anywhere inside the hour-grid, while the timed visit IS.
    const hourGrid = screen.getByTestId('fs-hourgrid')
    expect(within(hourGrid).queryByText('Untimed A')).toBeNull()
    expect(within(hourGrid).getByTestId('fs-block-602')).toBeInTheDocument()

    // Secondary check: the timed block's top still reflects its clock time.
    expect(screen.getByTestId('fs-block-602')).toHaveStyle({ top: '96px' })
  })

  it('drag-moves a timed block to a new start time (same day), persisting via updateVisit with optimistic cache update', async () => {
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const visits = [
      { id: 701, kam_id: 1, client_id: 1, planned_date: todayKey, planned_time: '09:00', planned_end_time: '10:00', visit_type: 'general', status: 'planned', client_name: 'Move Client', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: todayKey, date_to: todayKey })
    updateVisit.mockResolvedValue({ success: true, visit: visits[0] })
    const callsBefore = getMyVisits.mock.calls.length

    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByText('Move Client')
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    const block = await screen.findByTestId('fs-block-701')
    // Mocked for parity with the create-drag tests, even though the move
    // math itself is delta-based (see FieldSalesCalendar.tsx) and doesn't
    // need it — it IS consulted for the (untested here, dx===0) day-switch
    // heuristic, so a real width keeps that code path exercised too.
    const col = screen.getByTestId(`fs-col-${todayKey}`)
    vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
      top: 100, bottom: 500, height: 400, left: 0, right: 300, width: 300, x: 0, y: 100, toJSON: () => {},
    } as DOMRect)
    block.setPointerCapture = vi.fn()
    block.releasePointerCapture = vi.fn()

    // Move down exactly 1h worth of px (48px/hour) — 09:00 -> 10:00, the 1h
    // duration preserved -> end 10:00 -> 11:00. Only the CLIENTY DELTA
    // matters (see the component's move math), so absolute values are
    // arbitrary.
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointermove', 248)
    firePointer(block, 'pointerup', 248)

    await waitFor(() => expect(updateVisit).toHaveBeenCalledWith(701, { planned_date: todayKey, planned_time: '10:00', planned_end_time: '11:00' }))
    // Wait for onSettled's invalidation-triggered refetch of the (active)
    // field-sales-cal query so its resolution settles under RTL's act-
    // wrapped waitFor, not after the test ends (pristine, no act() warning).
    await waitFor(() => expect(getMyVisits.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('drag-resizes a timed block\'s end time via its bottom handle, persisting via updateVisit', async () => {
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const visits = [
      { id: 702, kam_id: 1, client_id: 1, planned_date: todayKey, planned_time: '09:00', planned_end_time: '10:00', visit_type: 'general', status: 'planned', client_name: 'Resize Client', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: todayKey, date_to: todayKey })
    updateVisit.mockResolvedValue({ success: true, visit: visits[0] })
    const callsBefore = getMyVisits.mock.calls.length

    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByText('Resize Client')
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    const handle = await screen.findByTestId('fs-resize-702')
    handle.setPointerCapture = vi.fn()
    handle.releasePointerCapture = vi.fn()

    // Move down 30 min worth of px (24px) -> end 10:00 -> 10:30. planned_date
    // / planned_time must NOT be part of the payload — resize only changes
    // the end time.
    firePointer(handle, 'pointerdown', 300)
    firePointer(handle, 'pointermove', 324)
    firePointer(handle, 'pointerup', 324)

    await waitFor(() => expect(updateVisit).toHaveBeenCalledWith(702, { planned_end_time: '10:30' }))
    await waitFor(() => expect(getMyVisits.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('treats a sub-threshold pointerdown/up on a block body as a click (opens it, does not call updateVisit)', async () => {
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const visits = [
      { id: 703, kam_id: 1, client_id: 1, planned_date: todayKey, planned_time: '09:00', planned_end_time: '10:00', visit_type: 'general', status: 'planned', client_name: 'Click Client', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: todayKey, date_to: todayKey })

    const onOpen = vi.fn()
    wrap(<FieldSalesCalendar onOpen={onOpen} onAdd={vi.fn()} />)
    await screen.findByText('Click Client')
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    const block = await screen.findByTestId('fs-block-703')
    block.setPointerCapture = vi.fn()
    block.releasePointerCapture = vi.fn()

    // 2px of jitter — under the 4px drag threshold — must still resolve as a
    // click (onOpen), not a persisted move.
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointerup', 202)

    expect(onOpen).toHaveBeenCalledWith(703)
    // updateVisit is a module-level mock shared with the move/resize tests
    // above (called there with OTHER visit ids) — assert it was never called
    // for THIS visit, not that it was never called at all.
    expect(updateVisit).not.toHaveBeenCalledWith(703, expect.anything())
  })

  it('rolls back the optimistic move and shows an inline error when updateVisit rejects', async () => {
    const now = new Date()
    const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const visits = [
      { id: 801, kam_id: 1, client_id: 1, planned_date: todayKey, planned_time: '09:00', planned_end_time: '10:00', visit_type: 'general', status: 'planned', client_name: 'Rollback Client', kam_name: 'X' },
    ]
    getMyVisits.mockResolvedValue({ success: true, visits, date_from: todayKey, date_to: todayKey })
    updateVisit.mockRejectedValueOnce({ data: { error: 'Nu s-a putut muta vizita' } })
    const callsBefore = getMyVisits.mock.calls.length

    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByText('Rollback Client')
    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))

    const block = await screen.findByTestId('fs-block-801')
    // 09:00 = minToY(540) = 96px is the block's original top.
    expect(block).toHaveStyle({ top: '96px' })
    block.setPointerCapture = vi.fn()
    block.releasePointerCapture = vi.fn()

    // Move down 1h (48px) — the optimistic onMutate writes 10:00 into the
    // cache (block would jump to top 144px), then updateVisit rejects →
    // onError rolls the cache back and surfaces err.data.error inline.
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointermove', 248)
    firePointer(block, 'pointerup', 248)

    // (a) inline error renders.
    await waitFor(() => expect(screen.getByText('Nu s-a putut muta vizita')).toBeInTheDocument())
    expect(updateVisit).toHaveBeenCalledWith(801, { planned_date: todayKey, planned_time: '10:00', planned_end_time: '11:00' })
    // (b) block is back at its original position (cache rolled back). Re-query
    // it — the optimistic write + rollback re-rendered the tree.
    expect(screen.getByTestId('fs-block-801')).toHaveStyle({ top: '96px' })
    // Let onSettled's invalidation-triggered refetch settle under waitFor so
    // it doesn't leak past the test as an act() warning.
    await waitFor(() => expect(getMyVisits.mock.calls.length).toBeGreaterThan(callsBefore))
  })
})
