import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { listPages, createPage, listBookings, listCars, listWindows, updatePage } = vi.hoisted(() => ({
  listPages: vi.fn(),
  createPage: vi.fn(),
  listBookings: vi.fn().mockResolvedValue({ bookings: [] }),
  listCars: vi.fn().mockResolvedValue({ cars: [] }),
  listWindows: vi.fn().mockResolvedValue({ windows: [] }),
  updatePage: vi.fn().mockResolvedValue({}),
}))
vi.mock('@/api/tdAdmin', () => ({
  tdAdminApi: {
    listPages, createPage, listBookings, listCars, listWindows, updatePage,
    setStatus: vi.fn(), materialize: vi.fn(),
    addCar: vi.fn(), removeCar: vi.fn(), addWindow: vi.fn(), deleteWindow: vi.fn(), reassignAdvisor: vi.fn(),
  },
}))
vi.mock('@/api/foiParcurs', () => ({
  foiParcursApi: {
    getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 7, company: 'Autoworld' }] }),
    getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  },
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
    localStorage.clear() // selection/tab are now persisted — isolate each test
    listPages.mockReset()
    createPage.mockReset()
    updatePage.mockReset()
    updatePage.mockResolvedValue({})
  })

  it('renders an empty state when there are no pages', async () => {
    listPages.mockResolvedValueOnce({ pages: [] })
    wrap(<TdBookingAdmin companyId={0} />)
    expect(await screen.findByText('Nicio pagină de programare')).toBeInTheDocument()
  })

  it('drills into a page with Rezervări as the default tab and Setări in the toolbar', async () => {
    listPages.mockResolvedValueOnce({
      pages: [{ id: 1, company_id: 7, slug: 'bmw-td', title: 'BMW Test Drive', status: 'draft', created_at: '2026-09-20T10:00:00Z' }],
    })
    wrap(<TdBookingAdmin companyId={7} />)
    fireEvent.click(await screen.findByText('bmw-td'))
    // Drilled-in detail exposes both tabs, Rezervări selected by default.
    const rezervari = await screen.findByRole('tab', { name: 'Rezervări' })
    expect(rezervari).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Detalii eveniment' })).toBeInTheDocument()
    // Setări (event config) is reachable from the toolbar regardless of the tab.
    expect(screen.getByRole('button', { name: /Setări/ })).toBeInTheDocument()
    // The bookings panel (default tab) renders its Rezervări heading.
    expect(await screen.findByRole('heading', { name: 'Rezervări' })).toBeInTheDocument()
  })

  it('drills back to the list with "Toate paginile" and filters the list by search', async () => {
    listPages.mockResolvedValue({
      pages: [
        { id: 1, company_id: 7, slug: 'bmw-td', title: 'BMW Test Drive', status: 'draft', created_at: '2026-09-20T10:00:00Z' },
        { id: 2, company_id: 7, slug: 'audi-td', title: 'Audi Test Drive', status: 'open', created_at: '2026-09-21T10:00:00Z' },
      ],
    })
    wrap(<TdBookingAdmin companyId={7} />)
    fireEvent.click(await screen.findByText('bmw-td'))
    // Back link returns to the list.
    fireEvent.click(await screen.findByRole('button', { name: /Toate paginile/ }))
    expect(await screen.findByText('audi-td')).toBeInTheDocument()
    // Search narrows the list to the matching slug.
    fireEvent.change(screen.getByPlaceholderText(/Caută după slug/), { target: { value: 'audi' } })
    expect(screen.getByText('audi-td')).toBeInTheDocument()
    expect(screen.queryByText('bmw-td')).not.toBeInTheDocument()
  })

  it('remembers the selected event across a remount (refresh persistence)', async () => {
    listPages.mockResolvedValue({
      pages: [{ id: 1, company_id: 7, slug: 'bmw-td', title: 'BMW Test Drive', status: 'draft', created_at: '2026-09-20T10:00:00Z' }],
    })
    const { unmount } = wrap(<TdBookingAdmin companyId={7} />)
    fireEvent.click(await screen.findByText('bmw-td'))
    await screen.findByRole('tab', { name: 'Rezervări' }) // drilled in
    unmount()
    // Remount = a page refresh: it restores the drilled-in event, not the list.
    wrap(<TdBookingAdmin companyId={7} />)
    expect(await screen.findByRole('button', { name: /Toate paginile/ })).toBeInTheDocument()
  })

  it('creates a page with the Driving Hub header company preselected', async () => {
    listPages.mockResolvedValue({ pages: [] })
    createPage.mockResolvedValueOnce({ id: 5, company_id: 7, slug: 'audi-td', status: 'draft', created_at: '2026-09-22T00:00:00Z' })
    wrap(<TdBookingAdmin companyId={7} />)

    fireEvent.click(await screen.findByText('Pagină nouă'))
    fireEvent.change(screen.getByPlaceholderText('ex: bmw-x5-td'), { target: { value: 'audi-td' } })
    fireEvent.click(screen.getByRole('button', { name: 'Creează' }))

    await waitFor(() =>
      expect(createPage).toHaveBeenCalledWith({ company_id: 7, slug: 'audi-td', title: undefined, event_id: undefined, logo_url: undefined }),
    )
  })

  it('reads an uploaded logo into a base64 data URL and includes it in the create payload', async () => {
    listPages.mockResolvedValue({ pages: [] })
    createPage.mockResolvedValueOnce({ id: 6, company_id: 7, slug: 'logo-td', status: 'draft', created_at: '2026-09-22T00:00:00Z' })
    wrap(<TdBookingAdmin companyId={7} />)

    fireEvent.click(await screen.findByText('Pagină nouă'))
    fireEvent.change(screen.getByPlaceholderText('ex: bmw-x5-td'), { target: { value: 'logo-td' } })

    const file = new File(['fake-image-bytes'], 'logo.png', { type: 'image/png' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })

    // Preview swaps the "Încarcă" label for "Schimbă" once the data URL is read.
    await screen.findByText('Schimbă')

    fireEvent.click(screen.getByRole('button', { name: 'Creează' }))

    await waitFor(() => expect(createPage).toHaveBeenCalled())
    const payload = createPage.mock.calls[0][0]
    expect(payload.logo_url).toMatch(/^data:image\/png;base64,/)
  })

  it('rejects an oversized logo file with a toast and does not set the preview', async () => {
    listPages.mockResolvedValue({ pages: [] })
    wrap(<TdBookingAdmin companyId={7} />)

    fireEvent.click(await screen.findByText('Pagină nouă'))

    const big = new File([new Uint8Array(1.6 * 1024 * 1024)], 'big.png', { type: 'image/png' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [big] } })

    // Stays on the "Încarcă" (upload) label — the oversized file was rejected, not previewed.
    await waitFor(() => expect(screen.queryByText('Schimbă')).not.toBeInTheDocument())
    expect(screen.getByText('Încarcă')).toBeInTheDocument()
  })

  it('saves the Condiții de test drive text from the Setări dialog', async () => {
    listPages.mockResolvedValue({
      pages: [{ id: 1, company_id: 7, slug: 'bmw-td', title: 'BMW Test Drive', status: 'draft', created_at: '2026-09-20T10:00:00Z' }],
    })
    wrap(<TdBookingAdmin companyId={7} />)

    fireEvent.click(await screen.findByText('bmw-td'))
    fireEvent.click(await screen.findByRole('button', { name: /Setări/ }))

    const textarea = await screen.findByPlaceholderText(/Textul afișat/)
    fireEvent.change(textarea, { target: { value: 'Clauze de test drive.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvează' }))

    await waitFor(() => expect(updatePage).toHaveBeenCalledTimes(1))
    expect(updatePage).toHaveBeenCalledWith(1, expect.objectContaining({ conditions_text: 'Clauze de test drive.' }))
  })
})
