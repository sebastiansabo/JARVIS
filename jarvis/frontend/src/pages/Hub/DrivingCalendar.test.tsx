import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const pad = (n: number) => String(n).padStart(2, '0')
const now = new Date()
const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
const todayIso = `${todayKey}T10:00`

const { getContracts, getVehicles, rescheduleTestDrive } = vi.hoisted(() => ({ getContracts: vi.fn(), getVehicles: vi.fn(), rescheduleTestDrive: vi.fn() }))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getContracts, getVehicles, rescheduleTestDrive } }))

// jsdom (v26) doesn't implement the PointerEvent constructor — build the event
// on MouseEvent and attach pointerId manually (mirrors FieldSalesCalendar.test).
function firePointer(el: Element, type: 'pointerdown' | 'pointermove' | 'pointerup', clientY: number, pointerId = 1) {
  const event = new MouseEvent(type, { clientY, bubbles: true, cancelable: true })
  Object.defineProperty(event, 'pointerId', { value: pointerId, configurable: true })
  fireEvent(el, event)
}
function mockCol(col: HTMLElement, top = 100) {
  vi.spyOn(col, 'getBoundingClientRect').mockReturnValue({
    top, bottom: top + 400, height: 400, left: 0, right: 300, width: 300, x: 0, y: top, toJSON: () => {},
  } as DOMRect)
  col.setPointerCapture = vi.fn()
  col.releasePointerCapture = vi.fn()
}

import DrivingCalendar from './DrivingCalendar'

getContracts.mockResolvedValue({
  contracts: [
    { id: 11, status: 'FILLED', td_status: 'driving', vin: 'VF1', client_name: 'Ion Pop', departure_datetime: todayIso, km_start: 100 },
    { id: 12, status: 'PLANNED', vin: 'VF1', client_name: 'Plan Client', departure_datetime: `${todayKey}T09:00`, return_datetime: `${todayKey}T10:00` },
  ], total: 2, page: 1, per_page: 1000,
})
getVehicles.mockResolvedValue({ vehicles: [{ vin: 'VF1', mark: 'Volvo', model: 'XC40' }] })

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DrivingCalendar', () => {
  beforeEach(() => localStorage.clear()) // view is persisted now — avoid leaks

  it('offers Day/Week/Month views and shows today’s session as a time-grid block in the default Week view', async () => {
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Zi' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Săptămână' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Lună' })).toBeInTheDocument()
    // 10:00 session → a spanning bar in today's column, labelled with its time.
    const block = await screen.findByTestId('tg-block-11')
    expect(block).toHaveTextContent('Ion Pop')
    expect(block).toHaveTextContent('10:00')
  })

  it('switches to Month view (weekday grid)', async () => {
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByTestId('tg-block-11')
    fireEvent.click(screen.getByRole('button', { name: 'Lună' }))
    expect(screen.getByText('Lu')).toBeInTheDocument()   // Monday-first weekday header
  })

  it('tapping a driving session block opens the return overlay via onReturn', async () => {
    const onReturn = vi.fn()
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={onReturn} onAdd={vi.fn()} />)
    fireEvent.click(await screen.findByTestId('tg-block-11'))
    expect(onReturn).toHaveBeenCalledWith(11)
  })

  it('drag-moves a PLANNED session block and reschedules it via the API', async () => {
    rescheduleTestDrive.mockResolvedValue({ success: true, contract: {} })
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByTestId('tg-block-12')
    // Drag-to-move lives in the Day-view hour grid (Week renders bars).
    fireEvent.click(screen.getByRole('button', { name: 'Zi' }))
    const block = await screen.findByTestId('tg-block-12') // PLANNED, 09:00–10:00, draggable
    block.setPointerCapture = vi.fn(); block.releasePointerCapture = vi.fn()
    // Drag down 48px (1h): 09:00→10:00, end 10:00→11:00.
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointermove', 248)
    firePointer(block, 'pointerup', 248)
    await waitFor(() => expect(rescheduleTestDrive).toHaveBeenCalledWith(12, { departure_datetime: `${todayKey}T10:00`, return_datetime: `${todayKey}T11:00` }))
  })

  it('reschedules a PLANNED session dropped onto another day in Month view', async () => {
    rescheduleTestDrive.mockClear(); rescheduleTestDrive.mockResolvedValue({ success: true, contract: {} })
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByTestId('tg-block-12')
    fireEvent.click(screen.getByRole('button', { name: 'Lună' }))
    // A different in-month day than the session's (today) — same month so its cell exists.
    const t = new Date(); const tgt = new Date(t); tgt.setDate(t.getDate() + (t.getDate() > 15 ? -1 : 1))
    const targetKey = `${tgt.getFullYear()}-${pad(tgt.getMonth() + 1)}-${pad(tgt.getDate())}`
    const cell = await screen.findByTestId(`dc-day-${targetKey}`)
    fireEvent.drop(cell, { dataTransfer: { getData: () => '12', setData: () => {}, effectAllowed: '', dropEffect: '' } })
    // Session 12 was 09:00–10:00; day changes, time preserved.
    await waitFor(() => expect(rescheduleTestDrive).toHaveBeenCalledWith(12, { departure_datetime: `${targetKey}T09:00`, return_datetime: `${targetKey}T10:00` }))
  })

  it('creates a multi-day session by dragging across days in Month view', async () => {
    const onAdd = vi.fn()
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={onAdd} />)
    await screen.findByTestId('tg-block-12')
    fireEvent.click(screen.getByRole('button', { name: 'Lună' }))
    const y = now.getFullYear(), m = pad(now.getMonth() + 1)
    const aKey = `${y}-${m}-10`, cKey = `${y}-${m}-12`
    fireEvent.pointerDown(await screen.findByTestId(`dc-day-${aKey}`))
    fireEvent.pointerEnter(screen.getByTestId(`dc-day-${cKey}`))
    fireEvent.pointerUp(screen.getByTestId(`dc-day-${cKey}`))
    expect(onAdd).toHaveBeenCalledWith(`${aKey}T09:00`, `${cKey}T18:00`)
  })

  it('does not allow dragging a non-planned (driving) session', async () => {
    rescheduleTestDrive.mockClear()
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={vi.fn()} />)
    const block = await screen.findByTestId('tg-block-11') // driving, not draggable
    block.setPointerCapture = vi.fn(); block.releasePointerCapture = vi.fn()
    firePointer(block, 'pointerdown', 200)
    firePointer(block, 'pointermove', 260)
    firePointer(block, 'pointerup', 260)
    expect(rescheduleTestDrive).not.toHaveBeenCalled()
  })

  it('proposes a new session via a drag on empty grid space in Day view (onAdd with the slot’s date/time)', async () => {
    const onAdd = vi.fn()
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={onAdd} />)
    await screen.findByTestId('tg-block-11')
    // Drag-to-create lives in the Day-view hour grid (Week adds via a day-cell click).
    fireEvent.click(screen.getByRole('button', { name: 'Zi' }))
    const col = screen.getByTestId(`tg-col-${todayKey}`)
    mockCol(col)
    // 09:00 offset 96px → 10:30 offset 168px.
    firePointer(col, 'pointerdown', 100 + 96)
    firePointer(col, 'pointermove', 100 + 168)
    firePointer(col, 'pointerup', 100 + 168)
    expect(onAdd).toHaveBeenCalledWith(`${todayKey}T09:00`, `${todayKey}T10:30`)
  })

  it('proposes a new session by clicking a Week day cell (onAdd with that day at 09:00–10:00)', async () => {
    const onAdd = vi.fn()
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={onAdd} />)
    await screen.findByTestId('tg-block-11') // default Week view
    fireEvent.click(screen.getByTestId(`tg-col-${todayKey}`)) // weekend-tinted day-background cell
    expect(onAdd).toHaveBeenCalledWith(`${todayKey}T09:00`, `${todayKey}T10:00`)
  })
})
