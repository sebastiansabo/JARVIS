import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

const { getPage, submitBooking } = vi.hoisted(() => ({
  getPage: vi.fn(),
  submitBooking: vi.fn(),
}))
vi.mock('@/api/td', () => ({ tdApi: { getPage, submitBooking } }))

import PublicTdBooking from './PublicTdBooking'

const PAGE = {
  page: { title: 'Test Drive Vara', company_name: 'Autoworld', gdpr_text: 'Îți prelucrăm datele conform...' },
  cars: [{ id: 10, vin: 'VIN1', label: 'MG ZS', plate: 'B-100-XYZ' }],
  slots: [
    { id: 100, car_id: 10, vin: 'VIN1', starts_at: '2099-10-01T10:00:00', ends_at: '2099-10-01T11:00:00' },
    { id: 101, car_id: 10, vin: 'VIN1', starts_at: '2099-10-01T11:00:00', ends_at: '2099-10-01T12:00:00' },
  ],
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/td/vara']}>
        <Routes>
          <Route path="/td/:slug" element={<PublicTdBooking />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function fill(label: string | RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

describe('PublicTdBooking', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getPage.mockResolvedValue(PAGE)
    submitBooking.mockResolvedValue({ booking_id: 1, status: 'pending_confirm' })
  })

  it('renders the car label + plate + slot times', async () => {
    renderPage()
    expect(await screen.findByText('MG ZS')).toBeInTheDocument()
    expect(screen.getByText('B-100-XYZ')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '10:00' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '11:00' })).toBeInTheDocument()
  })

  it('keeps the CTA disabled until slot + details + both consents are provided', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    const cta = screen.getByRole('button', { name: 'Trimite programarea' })
    expect(cta).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: '10:00' }))
    fill('Nume complet', 'Andrei Popescu')
    fill('Telefon', '0721234567')
    fill('Email', 'andrei@exemplu.ro')
    fill('Serie și număr permis', 'AB 123456')
    // Still disabled — consents not yet checked.
    expect(cta).toBeDisabled()

    const [gdpr, conditions] = screen.getAllByRole('checkbox')
    fireEvent.click(gdpr)
    expect(cta).toBeDisabled()
    fireEvent.click(conditions)
    expect(cta).toBeEnabled()
  })

  it('submits with the licence + both consents in the body', async () => {
    renderPage()
    await screen.findByText('MG ZS')

    fireEvent.click(screen.getByRole('button', { name: '10:00' }))
    fill('Nume complet', 'Andrei Popescu')
    fill('Telefon', '0721234567')
    fill('Email', 'andrei@exemplu.ro')
    fill('Serie și număr permis', 'AB 123456')
    const [gdpr, conditions] = screen.getAllByRole('checkbox')
    fireEvent.click(gdpr)
    fireEvent.click(conditions)

    fireEvent.click(screen.getByRole('button', { name: 'Trimite programarea' }))

    await waitFor(() => expect(submitBooking).toHaveBeenCalledTimes(1))
    expect(submitBooking).toHaveBeenCalledWith('vara', {
      slot_id: 100,
      name: 'Andrei Popescu',
      phone: '+40721234567',
      email: 'andrei@exemplu.ro',
      license: 'AB 123456',
      gdpr_consent: true,
      conditions_accepted: true,
    })
    // Success state after submit.
    expect(await screen.findByText('Verifică emailul')).toBeInTheDocument()
  })

  it('reveals the GDPR text behind a "Detalii" toggle', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    expect(screen.queryByText(/Îți prelucrăm datele/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Detalii' }))
    expect(screen.getByText(/Îți prelucrăm datele/)).toBeInTheDocument()
  })

  it('shows a not-available message when the page fails to load', async () => {
    getPage.mockRejectedValue(new Error('boom'))
    renderPage()
    expect(await screen.findByText('Această pagină nu este disponibilă.')).toBeInTheDocument()
  })

  it('renders the logo + intro in the full-width header when set, and skips the image when absent', async () => {
    getPage.mockResolvedValueOnce({
      ...PAGE,
      page: { ...PAGE.page, logo_url: 'data:image/png;base64,AAAA', intro: 'Vino să testezi noul model.' },
    })
    renderPage()
    const logo = await screen.findByRole('img', { name: /Sigla Test Drive Vara/ })
    expect(logo).toHaveAttribute('src', 'data:image/png;base64,AAAA')
    expect(screen.getByText('Vino să testezi noul model.')).toBeInTheDocument()
  })

  it('renders no logo image when the page has no logo_url', async () => {
    renderPage()
    await screen.findByText('Test Drive Vara')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
