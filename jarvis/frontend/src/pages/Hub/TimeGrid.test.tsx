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

    // 09:00 → top minToY(540)=96px; 10:30 → height minToY(630)-96 = 72px.
    const block = screen.getByTestId('tg-block-42')
    expect(block).toHaveStyle({ top: '96px', height: '72px' })

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
    expect(onSlotAdd).toHaveBeenCalledWith(todayKey, '11:00', '12:00')
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
    expect(onSlotAdd).toHaveBeenCalledWith(todayKey, '09:00', '10:30')
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

  it('draws red working-hours lines at 08:00 and 18:00', () => {
    render(<TimeGrid dayCols={[today]} events={[]} onEventClick={vi.fn()} />)
    // 08:00 = minToY(480) = 48px; 18:00 = minToY(1080) = 528px.
    expect(screen.getByTestId('tg-workline-start')).toHaveStyle({ top: '48px' })
    expect(screen.getByTestId('tg-workline-end')).toHaveStyle({ top: '528px' })
  })
})
