import { describe, it, expect, vi } from 'vitest'
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

  it('switching to week/day shows a placeholder note', async () => {
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: '', date_to: '' })
    wrap(<FieldSalesCalendar onOpen={vi.fn()} onAdd={vi.fn()} />)
    await screen.findByText(/nicio vizita/i)

    fireEvent.click(screen.getByRole('button', { name: 'Săptămână' }))
    expect(await screen.findByText(/în curând/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Zi' }))
    expect(await screen.findByText(/în curând/i)).toBeInTheDocument()
  })
})
