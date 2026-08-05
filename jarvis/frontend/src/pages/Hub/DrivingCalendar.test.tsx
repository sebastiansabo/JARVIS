import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const pad = (n: number) => String(n).padStart(2, '0')
const now = new Date()
const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
const todayIso = `${todayKey}T10:00`

const { getContracts, getVehicles } = vi.hoisted(() => ({ getContracts: vi.fn(), getVehicles: vi.fn() }))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getContracts, getVehicles } }))

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
  ], total: 1, page: 1, per_page: 1000,
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
    // 10:00 session → a positioned block at minToY(600)=144px in today's column.
    const block = await screen.findByTestId('tg-block-11')
    expect(block).toHaveTextContent('Ion Pop')
    expect(block).toHaveStyle({ top: '144px' })
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

  it('proposes a new session via a drag on empty grid space (onAdd with the slot’s date/time)', async () => {
    const onAdd = vi.fn()
    wrap(<DrivingCalendar companyId={11} brand="" onActivate={vi.fn()} onReturn={vi.fn()} onAdd={onAdd} />)
    await screen.findByTestId('tg-block-11')
    const col = screen.getByTestId(`tg-col-${todayKey}`)
    mockCol(col)
    // 09:00 offset 96px → 10:30 offset 168px.
    firePointer(col, 'pointerdown', 100 + 96)
    firePointer(col, 'pointermove', 100 + 168)
    firePointer(col, 'pointerup', 100 + 168)
    expect(onAdd).toHaveBeenCalledWith(todayKey, '09:00', '10:30')
  })
})
