import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import TimeGrid, { type TimeGridEvent } from './TimeGrid'

const pad = (n: number) => String(n).padStart(2, '0')
const keyOf = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

// jsdom (v26) doesn't implement the PointerEvent constructor, so
// fireEvent.pointerDown drops clientY/pointerId. Build the event on MouseEvent
// (which carries clientY) and attach pointerId manually — React copies both
// off the native event by name. Mirrors FieldSalesCalendar.test.tsx.
function firePointer(el: Element, type: 'pointerdown' | 'pointermove' | 'pointerup', clientY: number, pointerId = 1) {
  const event = new MouseEvent(type, { clientY, bubbles: true, cancelable: true })
  Object.defineProperty(event, 'pointerId', { value: pointerId, configurable: true })
  fireEvent(el, event)
}

// jsdom never lays elements out, so a column's getBoundingClientRect is mocked
// to a known top and the (unimplemented) pointer-capture methods are stubbed.
function mockCol(col: HTMLElement, top = 100) {
  vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
    top, bottom: top + 400, height: 400, left: 0, right: 300, width: 300, x: 0, y: top, toJSON: () => {},
  } as DOMRect)
  col.setPointerCapture = vi.fn()
  col.releasePointerCapture = vi.fn()
}

const today = new Date()
const todayKey = keyOf(today)
const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1)

describe('TimeGrid', () => {
  it('renders an hour gutter (07:00) and one column per day', () => {
    render(<TimeGrid dayCols={[today]} events={[]} onEventClick={vi.fn()} />)
    expect(screen.getByText('07:00')).toBeInTheDocument()
    expect(screen.getByTestId(`tg-col-${todayKey}`)).toBeInTheDocument()
  })

  it('positions a timed block by start/duration and opens it on click', () => {
    const ev: TimeGridEvent = { id: 42, dayKey: todayKey, startMin: 540, endMin: 630, color: 'bg-blue-100 text-blue-700', title: 'Ion Pop' }
    const onEventClick = vi.fn()
    const onSlotAdd = vi.fn()
    render(<TimeGrid dayCols={[today]} events={[ev]} onEventClick={onEventClick} onSlotAdd={onSlotAdd} />)

    // 09:00 → top minToY(540)=96px; 10:30 → height minToY(630)-96 = 72px, less
    // the 2px inter-block gap = 70px.
    const block = screen.getByTestId('tg-block-42')
    expect(block).toHaveStyle({ top: '96px', height: '70px' })

    fireEvent.click(block)
    expect(onEventClick).toHaveBeenCalledWith(42)
    expect(onSlotAdd).not.toHaveBeenCalled()
  })

  it('proposes a 1h slot on an empty-column click (no drag)', () => {
    const onSlotAdd = vi.fn()
    render(<TimeGrid dayCols={[today]} events={[]} onEventClick={vi.fn()} onSlotAdd={onSlotAdd} />)
    const col = screen.getByTestId(`tg-col-${todayKey}`)
    mockCol(col)
    // offset 192px → minToY(660) = 11:00, snapped.
    firePointer(col, 'pointerdown', 100 + 192)
    firePointer(col, 'pointerup', 100 + 192)
    expect(onSlotAdd).toHaveBeenCalledWith(`${todayKey}T11:00`, `${todayKey}T12:00`)
    expect(onSlotAdd).toHaveBeenCalledTimes(1)
  })

  it('proposes the dragged range (snapped to 30 min) on a drag-to-create', () => {
    const onSlotAdd = vi.fn()
    render(<TimeGrid dayCols={[today]} events={[]} onEventClick={vi.fn()} onSlotAdd={onSlotAdd} />)
    const col = screen.getByTestId(`tg-col-${todayKey}`)
    mockCol(col)
    // 09:00 offset 96px → 10:30 offset 168px.
    firePointer(col, 'pointerdown', 100 + 96)
    firePointer(col, 'pointermove', 100 + 168)
    firePointer(col, 'pointerup', 100 + 168)
    expect(onSlotAdd).toHaveBeenCalledWith(`${todayKey}T09:00`, `${todayKey}T10:30`)
  })

  it('renders an untimed event in the shared "Fără oră" band and opens it on click', () => {
    const ev: TimeGridEvent = { id: 7, dayKey: todayKey, startMin: null, endMin: null, color: 'bg-indigo-100 text-indigo-700', title: 'Fără oră client' }
    const onEventClick = vi.fn()
    render(<TimeGrid dayCols={[today]} events={[ev]} onEventClick={onEventClick} onSlotAdd={vi.fn()} />)

    const band = screen.getByTestId('tg-allday-band')
    expect(within(band).getByText('Fără oră client')).toBeInTheDocument()
    // Not inside the hour-grid.
    expect(within(screen.getByTestId('tg-hourgrid')).queryByText('Fără oră client')).toBeNull()

    fireEvent.click(within(band).getByTestId('tg-block-7'))
    expect(onEventClick).toHaveBeenCalledWith(7)
  })

  it('does NOT create a slot when a pointer press starts on a block (block events must not reach the column)', () => {
    // Regression: a block sits inside the column, so its pointerdown/up bubble
    // to the column's create-drag handlers — in a real browser that fires
    // onSlotAdd on top of opening the block. fireEvent.click never dispatches
    // pointer events, so this slipped past the earlier click test.
    const ev: TimeGridEvent = { id: 5, dayKey: todayKey, startMin: 540, endMin: 600, color: 'bg-blue-100 text-blue-700', title: 'X' }
    const onSlotAdd = vi.fn()
    render(<TimeGrid dayCols={[today]} events={[ev]} onEventClick={vi.fn()} onSlotAdd={onSlotAdd} />)
    const col = screen.getByTestId(`tg-col-${todayKey}`)
    mockCol(col) // stub the column's capture methods in case bubbling reaches it
    const block = screen.getByTestId('tg-block-5')
    block.setPointerCapture = vi.fn(); block.releasePointerCapture = vi.fn()
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointerup', 200)
    expect(onSlotAdd).not.toHaveBeenCalled()
  })

  it('clusters overlapping timed events into one block that opens a list of sessions', () => {
    const evs: TimeGridEvent[] = [
      { id: 1, dayKey: todayKey, startMin: 705, endMin: 765, color: 'bg-indigo-100 text-indigo-700', title: 'QATAR INFLUENCE', subtitle: 'Audi A5' }, // 11:45–12:45
      { id: 2, dayKey: todayKey, startMin: 720, endMin: 780, color: 'bg-blue-100 text-blue-700', title: 'DEMO SRL', subtitle: 'VW Golf' },       // 12:00–13:00 (overlaps)
    ]
    const onEventClick = vi.fn()
    render(<TimeGrid dayCols={[today]} events={evs} onEventClick={onEventClick} onSlotAdd={vi.fn()} />)

    // The two overlapping events collapse into ONE cluster block (keyed on the
    // earliest event's id) with a count badge; no standalone blocks remain.
    const cluster = screen.getByTestId('tg-cluster-1')
    expect(within(cluster).getByTestId('tg-cluster-count')).toHaveTextContent('2')
    expect(screen.queryByTestId('tg-block-1')).toBeNull()
    expect(screen.queryByTestId('tg-block-2')).toBeNull()

    // Tapping the cluster opens a list of both sessions…
    fireEvent.click(cluster)
    const list = screen.getByTestId('tg-cluster-list')
    expect(within(list).getByText('QATAR INFLUENCE')).toBeInTheDocument()
    expect(within(list).getByText('DEMO SRL')).toBeInTheDocument()

    // …and a row taps through to that session, closing the list.
    fireEvent.click(within(list).getByTestId('tg-clusteritem-2'))
    expect(onEventClick).toHaveBeenCalledWith(2)
    expect(screen.queryByTestId('tg-cluster-list')).toBeNull()
  })

  it('keeps non-overlapping timed events as separate blocks (no cluster)', () => {
    const evs: TimeGridEvent[] = [
      { id: 1, dayKey: todayKey, startMin: 540, endMin: 600, color: 'bg-blue-100 text-blue-700', title: 'A' },   // 09:00–10:00
      { id: 2, dayKey: todayKey, startMin: 660, endMin: 720, color: 'bg-blue-100 text-blue-700', title: 'B' },   // 11:00–12:00
    ]
    render(<TimeGrid dayCols={[today]} events={evs} onEventClick={vi.fn()} onSlotAdd={vi.fn()} />)
    expect(screen.getByTestId('tg-block-1')).toBeInTheDocument()
    expect(screen.getByTestId('tg-block-2')).toBeInTheDocument()
    expect(screen.queryByTestId('tg-cluster-1')).toBeNull()
  })

  // NOTE: Week view no longer has an hour grid to drag in — sessions render as
  // spanning bars and new sessions are created by clicking a day cell (see the
  // DrivingCalendar/CalendarTab "click a Week day cell" tests). The old
  // Week-grid drag-create + edge-auto-advance behaviour was removed with it.

  it('drag-moves a draggable block to a new time (duration preserved) via onMove', () => {
    const ev: TimeGridEvent = { id: 9, dayKey: todayKey, startMin: 540, endMin: 600, color: 'bg-indigo-100 text-indigo-700', title: 'P', draggable: true } // 09:00–10:00
    const onMove = vi.fn(); const onEventClick = vi.fn()
    render(<TimeGrid dayCols={[today]} events={[ev]} onEventClick={onEventClick} onSlotAdd={vi.fn()} onMove={onMove} />)
    const block = screen.getByTestId('tg-block-9')
    block.setPointerCapture = vi.fn(); block.releasePointerCapture = vi.fn()
    // Drag down 48px (1h): 09:00→10:00, 1h duration → end 11:00. Only the delta matters.
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointermove', 248)
    firePointer(block, 'pointerup', 248)
    expect(onMove).toHaveBeenCalledWith(9, todayKey, '10:00', '11:00')
    expect(onEventClick).not.toHaveBeenCalled()
  })

  it('treats a sub-threshold press on a draggable block as a click (opens, no move)', () => {
    const ev: TimeGridEvent = { id: 9, dayKey: todayKey, startMin: 540, endMin: 600, color: 'x', title: 'P', draggable: true }
    const onMove = vi.fn(); const onEventClick = vi.fn()
    render(<TimeGrid dayCols={[today]} events={[ev]} onEventClick={onEventClick} onSlotAdd={vi.fn()} onMove={onMove} />)
    const block = screen.getByTestId('tg-block-9')
    block.setPointerCapture = vi.fn(); block.releasePointerCapture = vi.fn()
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointerup', 202) // 2px < 4px threshold
    expect(onMove).not.toHaveBeenCalled()
    expect(onEventClick).toHaveBeenCalledWith(9)
  })

  it('does not drag a non-draggable block', () => {
    const ev: TimeGridEvent = { id: 9, dayKey: todayKey, startMin: 540, endMin: 600, color: 'x', title: 'P' } // draggable falsy
    const onMove = vi.fn()
    render(<TimeGrid dayCols={[today]} events={[ev]} onEventClick={vi.fn()} onSlotAdd={vi.fn()} onMove={onMove} />)
    const block = screen.getByTestId('tg-block-9')
    block.setPointerCapture = vi.fn(); block.releasePointerCapture = vi.fn()
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointermove', 260)
    firePointer(block, 'pointerup', 260)
    expect(onMove).not.toHaveBeenCalled()
  })

  it('renders a multi-day session as one spanning bar in the top band (event-calendar style)', () => {
    const dayAfter = new Date(today); dayAfter.setDate(today.getDate() + 2)
    const dayAfterKey = keyOf(dayAfter)
    const ev: TimeGridEvent = { id: 50, dayKey: todayKey, endDayKey: dayAfterKey, startMin: 540, endMin: 660, color: 'bg-blue-100 text-blue-700', title: 'Multi' }
    render(<TimeGrid dayCols={[today, tomorrow, dayAfter]} events={[ev]} onEventClick={vi.fn()} onSlotAdd={vi.fn()} />)
    // One bar, spanning grid columns 1→3 (lines 1..4), in the top band. Week
    // view has no hour grid, so the session only ever exists as this bar.
    const bar = screen.getByTestId('tg-block-50')
    expect(bar).toHaveStyle({ gridColumnStart: '1', gridColumnEnd: '4' })
    expect(within(screen.getByTestId('tg-allday-band')).getByTestId('tg-block-50')).toBeInTheDocument()
    expect(screen.queryByTestId('tg-hourgrid')).toBeNull()
  })

  it('labels a multi-day bar with its date range + a multi-zi tag (not a same-day slot)', () => {
    const dayAfter = new Date(today); dayAfter.setDate(today.getDate() + 2)
    const ev: TimeGridEvent = { id: 51, dayKey: todayKey, endDayKey: keyOf(dayAfter), startMin: 690, endMin: 870, color: 'x', title: 'QATAR' }
    render(<TimeGrid dayCols={[today, tomorrow, dayAfter]} events={[ev]} onEventClick={vi.fn()} />)
    const bar = screen.getByTestId('tg-block-51')
    expect(screen.getByTestId('tg-multiday-51')).toBeInTheDocument() // "multi-zi" tag
    expect(bar).toHaveTextContent('→')     // date-range arrow, not the same-day "–"
    expect(bar).toHaveTextContent('11:30') // departure time
    expect(bar).toHaveTextContent('14:30') // return time (on a later day)
  })

  it('marks interlaced (same-car, time-overlapping) sessions with a hachured overlap track', () => {
    const evs: TimeGridEvent[] = [
      { id: 1, dayKey: todayKey, startMin: 600, endMin: 690, color: 'x', title: 'A', groupKey: 'VIN1' }, // 10:00–11:30
      { id: 2, dayKey: todayKey, startMin: 630, endMin: 720, color: 'x', title: 'B', groupKey: 'VIN1' }, // 10:30–12:00 (overlaps 1)
      { id: 3, dayKey: todayKey, startMin: 800, endMin: 860, color: 'x', title: 'C', groupKey: 'VIN1' }, // same car, no time overlap
      { id: 4, dayKey: todayKey, startMin: 600, endMin: 690, color: 'x', title: 'D', groupKey: 'VIN2' }, // different car, same time
    ]
    render(<TimeGrid dayCols={[today, tomorrow]} events={evs} onEventClick={vi.fn()} />) // Week view → bars
    expect(screen.getByTestId('tg-conflict-1')).toBeInTheDocument()
    expect(screen.getByTestId('tg-conflict-2')).toBeInTheDocument()
    expect(screen.queryByTestId('tg-conflict-3')).toBeNull() // same car but disjoint in time
    expect(screen.queryByTestId('tg-conflict-4')).toBeNull() // overlaps in time but a different car
  })

  it('codes same-car daily sessions S1..Sx (by start) and labels overlaps "Suprapus cu Sx"', () => {
    const evs: TimeGridEvent[] = [
      { id: 1, dayKey: todayKey, startMin: 600, endMin: 690, color: 'x', title: 'A', groupKey: 'VIN1' }, // 10:00–11:30 → S1
      { id: 2, dayKey: todayKey, startMin: 630, endMin: 720, color: 'x', title: 'B', groupKey: 'VIN1' }, // 10:30–12:00 → S2 (overlaps S1)
      { id: 3, dayKey: todayKey, startMin: 800, endMin: 860, color: 'x', title: 'C', groupKey: 'VIN1' }, // later → S3 (no overlap)
      { id: 9, dayKey: todayKey, startMin: 600, endMin: 660, color: 'x', title: 'Solo', groupKey: 'VIN9' }, // lone car → no code
    ]
    render(<TimeGrid dayCols={[today, tomorrow]} events={evs} onEventClick={vi.fn()} />)
    expect(screen.getByTestId('tg-code-1')).toHaveTextContent('S1')
    expect(screen.getByTestId('tg-code-2')).toHaveTextContent('S2')
    expect(screen.getByTestId('tg-code-3')).toHaveTextContent('S3')
    expect(screen.queryByTestId('tg-code-9')).toBeNull() // only one session for that car → no code
    // Overlap cross-references by code.
    expect(screen.getByTestId('tg-overlap-1')).toHaveTextContent('Suprapus cu S2')
    expect(screen.getByTestId('tg-overlap-2')).toHaveTextContent('Suprapus cu S1')
    expect(screen.queryByTestId('tg-overlap-3')).toBeNull() // S3 doesn't overlap anything
  })

  it('orders bars chronologically by start time within a day (not by input/creation order)', () => {
    // Week view renders every session as a bar; given out-of-order input (by
    // creation), same-day bars must stack top→bottom by departure time.
    const evs: TimeGridEvent[] = [
      { id: 1, dayKey: todayKey, startMin: 660, endMin: 720, color: 'x', title: 'eleven' }, // 11:00
      { id: 2, dayKey: todayKey, startMin: 540, endMin: 600, color: 'x', title: 'nine' },   // 09:00
      { id: 3, dayKey: todayKey, startMin: 600, endMin: 660, color: 'x', title: 'ten' },     // 10:00
    ]
    render(<TimeGrid dayCols={[today, tomorrow]} events={evs} onEventClick={vi.fn()} />) // Week view → bars
    const band = screen.getByTestId('tg-allday-band')
    const order = within(band).getAllByTestId(/tg-block-\d+/).map((el) => el.getAttribute('data-testid'))
    expect(order).toEqual(['tg-block-2', 'tg-block-3', 'tg-block-1']) // 09:00, 10:00, 11:00
  })

  it('draws red working-hours lines at 08:00 and 18:00', () => {
    render(<TimeGrid dayCols={[today]} events={[]} onEventClick={vi.fn()} />)
    // 08:00 = minToY(480) = 48px; 18:00 = minToY(1080) = 528px.
    expect(screen.getByTestId('tg-workline-start')).toHaveStyle({ top: '48px' })
    expect(screen.getByTestId('tg-workline-end')).toHaveStyle({ top: '528px' })
  })
})
