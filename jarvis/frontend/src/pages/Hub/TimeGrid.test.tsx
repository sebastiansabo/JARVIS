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
})
