import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const navigate = vi.fn()
vi.mock('react-router-dom', async (orig) => ({ ...(await orig() as object), useNavigate: () => navigate }))

const { getContracts, getVehicles } = vi.hoisted(() => ({ getContracts: vi.fn(), getVehicles: vi.fn() }))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getContracts, getVehicles,
  discardTestDrive: vi.fn(),
  getContractPdfUrl: (id: number) => `/pdf/${id}`,
} }))

// jsdom (v26) doesn't implement the PointerEvent constructor — build on MouseEvent.
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

import { CalendarTab } from './CalendarTab'

const pad = (n: number) => String(n).padStart(2, '0')
const now = new Date()
const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`

getContracts.mockResolvedValue({
  contracts: [
    { id: 11, route_type: 'TD', status: 'FILLED', td_status: 'driving', vin: 'VF1XXXXXXXX', client_name: 'Ion Pop', departure_datetime: `${todayKey}T10:00`, return_datetime: `${todayKey}T11:30` },
  ], total: 1, page: 1, per_page: 2000,
})
getVehicles.mockResolvedValue({ vehicles: [{ vin: 'VF1XXXXXXXX', brand: 'Volvo', mark: 'Volvo', model: 'XC40', registration_number: 'B 01 ABC' }] })

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('CalendarTab (desktop foi-parcurs)', () => {
  // View is persisted in localStorage now — clear so each test starts at the
  // real default (Week) instead of leaking a prior test's selection.
  beforeEach(() => localStorage.clear())

  it('offers Day/Week/Month views with Week as the default', async () => {
    wrap(<CalendarTab companyId={11} brand="" />)
    expect(await screen.findByRole('button', { name: 'Zi' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Săptămână' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Lună' })).toBeInTheDocument()
    // Week is default → the session renders as a spanning bar (no hour grid).
    expect(await screen.findByTestId('tg-block-11')).toBeInTheDocument()
  })

  it('opens the details dialog when a Week-view block is clicked', async () => {
    wrap(<CalendarTab companyId={11} brand="" />)
    const block = await screen.findByTestId('tg-block-11') // Week spanning bar
    expect(block).toHaveTextContent('10:00')
    fireEvent.click(block)
    expect(await screen.findByText('Detalii sesiune')).toBeInTheDocument()
  })

  it('navigates to a prefilled new-session form when dragging an empty slot in Day view', async () => {
    wrap(<CalendarTab companyId={11} brand="" />)
    await screen.findByTestId('tg-block-11') // week loaded
    fireEvent.click(screen.getByRole('button', { name: 'Zi' })) // drag-create lives in Day view
    const col = await screen.findByTestId(`tg-col-${todayKey}`)
    mockCol(col)
    // pxPerHour=72 here → 09:00 offset 144px, 10:30 offset 252px.
    firePointer(col, 'pointerdown', 100 + 144)
    firePointer(col, 'pointermove', 100 + 252)
    firePointer(col, 'pointerup', 100 + 252)
    expect(navigate).toHaveBeenCalledWith(`/app/foi-parcurs/test-drive?departure=${todayKey}T09:00&return=${todayKey}T10:30`)
  })

  it('navigates to a prefilled new-session form when clicking a Week day cell', async () => {
    wrap(<CalendarTab companyId={11} brand="" />)
    await screen.findByTestId('tg-block-11') // default Week view
    fireEvent.click(screen.getByTestId(`tg-col-${todayKey}`)) // day-background cell
    expect(navigate).toHaveBeenCalledWith(`/app/foi-parcurs/test-drive?departure=${todayKey}T09:00&return=${todayKey}T10:00`)
  })

  it('creates a multi-day session by dragging across days in Month view', async () => {
    wrap(<CalendarTab companyId={11} brand="" />)
    await screen.findByTestId('tg-block-11')
    fireEvent.click(screen.getByRole('button', { name: 'Lună' }))
    const y = now.getFullYear(), m = pad(now.getMonth() + 1)
    const aKey = `${y}-${m}-10`, cKey = `${y}-${m}-12`
    fireEvent.pointerDown(await screen.findByTestId(`fp-day-${aKey}`))
    fireEvent.pointerEnter(screen.getByTestId(`fp-day-${cKey}`))
    fireEvent.pointerUp(screen.getByTestId(`fp-day-${cKey}`))
    expect(navigate).toHaveBeenCalledWith(`/app/foi-parcurs/test-drive?departure=${aKey}T09:00&return=${cKey}T18:00`)
  })

  it('switches to Month view showing the session chip', async () => {
    wrap(<CalendarTab companyId={11} brand="" />)
    await screen.findByTestId('tg-block-11')
    fireEvent.click(screen.getByRole('button', { name: 'Lună' }))
    expect(await screen.findByTitle(/Ion Pop/)).toBeInTheDocument()
  })
})
