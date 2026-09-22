import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { listPages, createPage, listBookings } = vi.hoisted(() => ({
  listPages: vi.fn(),
  createPage: vi.fn(),
  listBookings: vi.fn().mockResolvedValue({ bookings: [] }),
}))
vi.mock('@/api/tdAdmin', () => ({
  tdAdminApi: {
    listPages, createPage, listBookings,
    setStatus: vi.fn(), materialize: vi.fn(),
    addCar: vi.fn(), removeCar: vi.fn(), addWindow: vi.fn(), reassignAdvisor: vi.fn(),
  },
}))
vi.mock('@/api/foiParcurs', () => ({
  foiParcursApi: { getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 7, company: 'Autoworld' }] }) },
}))
vi.mock('@/api/hr', () => ({ hrApi: { getEvents: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/api/users', () => ({
  usersApi: { getUsers: vi.fn().mockResolvedValue([{ id: 3, name: 'Ion Pop', is_active: true }]) },
}))

import TdBookingAdmin from './TdBookingAdmin'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('TdBookingAdmin', () => {
  beforeEach(() => {
    listPages.mockReset()
    createPage.mockReset()
  })

  it('renders an empty state when there are no pages', async () => {
    listPages.mockResolvedValueOnce({ pages: [] })
    wrap(<TdBookingAdmin companyId={0} />)
    expect(await screen.findByText('Nicio pagină de programare')).toBeInTheDocument()
  })

  it('lists pages and shows the Cars/Windows/Bookings panels once a page is selected', async () => {
    listPages.mockResolvedValueOnce({
      pages: [{ id: 1, company_id: 7, slug: 'bmw-td', title: 'BMW Test Drive', status: 'draft', created_at: '2026-09-20T10:00:00Z' }],
    })
    wrap(<TdBookingAdmin companyId={7} />)
    fireEvent.click(await screen.findByText('bmw-td'))
    expect(await screen.findByText('Mașini')).toBeInTheDocument()
    expect(screen.getByText('Intervale disponibile')).toBeInTheDocument()
    // Bookings panel fetches its own list and shows a skeleton first.
    expect(await screen.findByText('Rezervări')).toBeInTheDocument()
  })

  it('creates a page with the Driving Hub header company preselected', async () => {
    listPages.mockResolvedValue({ pages: [] })
    createPage.mockResolvedValueOnce({ id: 5, company_id: 7, slug: 'audi-td', status: 'draft', created_at: '2026-09-22T00:00:00Z' })
    wrap(<TdBookingAdmin companyId={7} />)

    fireEvent.click(await screen.findByText('Pagină nouă'))
    fireEvent.change(screen.getByPlaceholderText('ex: bmw-x5-td'), { target: { value: 'audi-td' } })
    fireEvent.click(screen.getByRole('button', { name: 'Creează' }))

    await waitFor(() =>
      expect(createPage).toHaveBeenCalledWith({ company_id: 7, slug: 'audi-td', title: undefined, event_id: undefined }),
    )
  })
})
