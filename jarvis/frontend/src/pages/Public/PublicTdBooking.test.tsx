import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

const { getPage, submitBooking, submitWaitlist } = vi.hoisted(() => ({
  getPage: vi.fn(),
  submitBooking: vi.fn(),
  submitWaitlist: vi.fn(),
}))
vi.mock('@/api/td', () => ({ tdApi: { getPage, submitBooking, submitWaitlist } }))

// Licence photos are downscaled client-side (same util foi de parcurs uses) so
// the stored base64 stays small. Mocked here: jsdom has no real canvas/Image.
const { fileToCompressedDataUrl } = vi.hoisted(() => ({ fileToCompressedDataUrl: vi.fn() }))
vi.mock('@/lib/imageCompress', () => ({ fileToCompressedDataUrl }))

import PublicTdBooking from './PublicTdBooking'

const PAGE = {
  page: { title: 'Test Drive Vara', company_name: 'Autoworld', gdpr_text: 'Îți prelucrăm datele conform...' },
  cars: [{ id: 10, vin: 'VIN1', label: 'MG ZS', plate: 'B-100-XYZ' }],
  slots: [
    { id: 100, car_id: 10, vin: 'VIN1', starts_at: '2099-10-01T10:00:00', ends_at: '2099-10-01T11:00:00' },
    { id: 101, car_id: 10, vin: 'VIN1', starts_at: '2099-10-01T11:00:00', ends_at: '2099-10-01T12:00:00' },
  ],
}

// A two-day event: car A only free on day 1 (25 Sept), car B only on day 2 (26 Sept).
const MULTI_DAY_PAGE = {
  page: { title: 'Test Drive Toamnă', company_name: 'Autoworld' },
  cars: [
    { id: 10, vin: 'VIN1', label: 'MG ZS', plate: 'B-100-XYZ' },
    { id: 20, vin: 'VIN2', label: 'Dacia Duster', plate: 'B-200-ABC' },
  ],
  slots: [
    { id: 100, car_id: 10, vin: 'VIN1', starts_at: '2099-09-25T10:00:00', ends_at: '2099-09-25T11:00:00' },
    { id: 200, car_id: 20, vin: 'VIN2', starts_at: '2099-09-26T14:00:00', ends_at: '2099-09-26T15:00:00' },
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
    fileToCompressedDataUrl.mockResolvedValue('data:image/jpeg;base64,CMP')
    submitBooking.mockResolvedValue({
      group_id: 'g1', booked: [{ booking_id: 1, slot_id: 100, car_id: 10, starts_at: null, ends_at: null }],
      unavailable: [], booking_id: 1, status: 'pending_confirm',
    })
  })

  it('renders the car label + plate + slot times', async () => {
    renderPage()
    expect(await screen.findByText('MG ZS')).toBeInTheDocument()
    expect(screen.getByText('B-100-XYZ')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion
    expect(screen.getByRole('button', { name: '10:00' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '11:00' })).toBeInTheDocument()
  })

  it('keeps the CTA disabled until slot + details + both consents are provided', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)
    const cta = screen.getByRole('button', { name: 'Trimite programările' })
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
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)

    fireEvent.click(screen.getByRole('button', { name: '10:00' }))
    fill('Nume complet', 'Andrei Popescu')
    fill('Telefon', '0721234567')
    fill('Email', 'andrei@exemplu.ro')
    fill('Serie și număr permis', 'AB 123456')
    const [gdpr, conditions] = screen.getAllByRole('checkbox')
    fireEvent.click(gdpr)
    fireEvent.click(conditions)

    fireEvent.click(screen.getByRole('button', { name: 'Trimite programările' }))

    await waitFor(() => expect(submitBooking).toHaveBeenCalledTimes(1))
    expect(submitBooking).toHaveBeenCalledWith('vara', {
      slot_ids: [100],
      preferred: [],
      name: 'Andrei Popescu',
      phone: '+40721234567',
      email: 'andrei@exemplu.ro',
      license: 'AB 123456',
      license_photo: null,
      gdpr_consent: true,
      conditions_accepted: true,
    })
    // Success state after submit.
    expect(await screen.findByText('Verifică emailul')).toBeInTheDocument()
  })

  it('selects several intervals as a group, lists them, removes one, and submits slot_ids', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)

    // Pick both intervals -> both appear in the "Programările tale" summary.
    fireEvent.click(screen.getByRole('button', { name: '10:00' }))
    fireEvent.click(screen.getByRole('button', { name: '11:00' }))
    expect(await screen.findByText('Programările tale')).toBeInTheDocument()
    // Two removable summary entries.
    expect(screen.getAllByRole('button', { name: /^Elimină/ })).toHaveLength(2)

    // Remove the 2nd pick (labels are "Elimină <choice> — <car>", not by time).
    fireEvent.click(screen.getAllByRole('button', { name: /^Elimină/ })[1])
    expect(screen.getAllByRole('button', { name: /^Elimină/ })).toHaveLength(1)

    // Re-add it, fill details, submit -> both slot_ids in one group.
    fireEvent.click(screen.getByRole('button', { name: '11:00' }))
    fill('Nume complet', 'Andrei Popescu')
    fill('Telefon', '0721234567')
    fill('Email', 'andrei@exemplu.ro')
    fill('Serie și număr permis', 'AB 123456')
    const [gdpr, conditions] = screen.getAllByRole('checkbox')
    fireEvent.click(gdpr)
    fireEvent.click(conditions)

    fireEvent.click(screen.getByRole('button', { name: 'Trimite programările' }))
    await waitFor(() => expect(submitBooking).toHaveBeenCalledTimes(1))
    // Global ranking (Batch 1): only the 1st pick is booked (slot_ids); the rest
    // ride along as ranked preferences.
    expect(submitBooking).toHaveBeenCalledWith('vara', expect.objectContaining({
      slot_ids: [100],
      preferred: [expect.objectContaining({ car: 'MG ZS' })],
    }))
  })

  it('keeps the CTA enabled without a licence photo (it is optional)', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)

    fireEvent.click(screen.getByRole('button', { name: '10:00' }))
    fill('Nume complet', 'Andrei Popescu')
    fill('Telefon', '0721234567')
    fill('Email', 'andrei@exemplu.ro')
    fill('Serie și număr permis', 'AB 123456')
    const [gdpr, conditions] = screen.getAllByRole('checkbox')
    fireEvent.click(gdpr)
    fireEvent.click(conditions)

    // No photo ever uploaded -- CTA still enables and submit still succeeds.
    const cta = screen.getByRole('button', { name: 'Trimite programările' })
    expect(cta).toBeEnabled()
    fireEvent.click(cta)
    await waitFor(() => expect(submitBooking).toHaveBeenCalledTimes(1))
    expect(submitBooking).toHaveBeenCalledWith('vara', expect.objectContaining({ license_photo: null }))
  })

  it('compresses an uploaded licence photo, previews it, and includes it in the submit payload', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)

    const file = new File(['fake-image-bytes'], 'permis.png', { type: 'image/png' })
    const input = screen.getByLabelText('Poză permis (opțional)') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })

    // The raw file is downscaled via imageCompress before it is stored/sent.
    await waitFor(() => expect(fileToCompressedDataUrl).toHaveBeenCalledWith(file))
    // Preview swaps the upload control for the thumbnail + remove control.
    const remove = await screen.findByRole('button', { name: 'Șterge' })
    expect(screen.getByAltText('Poză permis')).toHaveAttribute('src', 'data:image/jpeg;base64,CMP')

    fireEvent.click(screen.getByRole('button', { name: '10:00' }))
    fill('Nume complet', 'Andrei Popescu')
    fill('Telefon', '0721234567')
    fill('Email', 'andrei@exemplu.ro')
    fill('Serie și număr permis', 'AB 123456')
    const [gdpr, conditions] = screen.getAllByRole('checkbox')
    fireEvent.click(gdpr)
    fireEvent.click(conditions)
    fireEvent.click(screen.getByRole('button', { name: 'Trimite programările' }))

    await waitFor(() => expect(submitBooking).toHaveBeenCalledTimes(1))
    const payload = submitBooking.mock.calls[0][1]
    expect(payload.license_photo).toBe('data:image/jpeg;base64,CMP')

    // Remove control clears the preview back to the upload control.
    fireEvent.click(remove)
    expect(screen.queryByRole('button', { name: 'Șterge' })).not.toBeInTheDocument()
  })

  it('offers a camera-capture option and compresses the captured photo', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ }))

    const cam = screen.getByLabelText('Fă o poză permisului (cameră)') as HTMLInputElement
    expect(cam).toHaveAttribute('capture', 'environment')

    const file = new File(['img'], 'permis.jpg', { type: 'image/jpeg' })
    fireEvent.change(cam, { target: { files: [file] } })

    await screen.findByRole('button', { name: 'Șterge' })
    expect(fileToCompressedDataUrl).toHaveBeenCalledWith(file)
    expect(screen.getByAltText('Poză permis')).toHaveAttribute('src', 'data:image/jpeg;base64,CMP')
  })

  it('rejects an oversized source file before compressing and does not set a preview', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)

    const big = new File([new Uint8Array(11 * 1024 * 1024)], 'big.png', { type: 'image/png' }) // > 10MB source cap
    const input = screen.getByLabelText('Poză permis (opțional)') as HTMLInputElement
    fireEvent.change(input, { target: { files: [big] } })

    // Rejected before it reaches the compressor; stays on the upload control, no preview.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Șterge' })).not.toBeInTheDocument())
    expect(fileToCompressedDataUrl).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Poză permis (opțional)')).toBeInTheDocument()
  })

  it('opens the GDPR text in a "Citește" popup (first consent link)', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)
    expect(screen.queryByText(/Îți prelucrăm datele/)).not.toBeInTheDocument()
    // Two "Citește" links (GDPR then Conditions); the first opens the GDPR popup.
    fireEvent.click(screen.getAllByRole('button', { name: 'Citește' })[0])
    expect(await screen.findByText(/Îți prelucrăm datele/)).toBeInTheDocument()
  })

  it('opens the conditions popup with the built-in default when the page has none', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)
    expect(screen.queryByText(/permis de conducere valid/)).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Citește' })[1])
    expect(await screen.findByText(/permis de conducere valid/)).toBeInTheDocument()
  })

  it('shows the page-provided conditions_text in the popup when set', async () => {
    getPage.mockResolvedValueOnce({
      ...PAGE,
      page: { ...PAGE.page, conditions_text: 'Reguli speciale pentru acest eveniment.' },
    })
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)
    fireEvent.click(screen.getAllByRole('button', { name: 'Citește' })[1])
    expect(await screen.findByText('Reguli speciale pentru acest eveniment.')).toBeInTheDocument()
  })

  it('shows a day selector for a multi-day event and persists picks across days', async () => {
    getPage.mockResolvedValueOnce(MULTI_DAY_PAGE)
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)

    // Two day pills in the day-selector group.
    const dayGroup = screen.getByRole('group', { name: 'Alege ziua' })
    const dayPills = within(dayGroup).getAllByRole('button')
    expect(dayPills).toHaveLength(2)

    // Default = first day: car A's 10:00 is shown; car B (day 2 only) has none here.
    expect(screen.getByRole('button', { name: '10:00' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '14:00' })).not.toBeInTheDocument()

    // Pick the day-1 slot -> it lands in the summary.
    fireEvent.click(screen.getByRole('button', { name: '10:00' }))
    expect(screen.getByRole('button', { name: /Elimină.*MG ZS/ })).toBeInTheDocument()

    // Switch to day 2: picker swaps to day-2 slots (expand car B to reveal them)...
    fireEvent.click(dayPills[1])
    fireEvent.click(screen.getByRole('button', { name: /Dacia Duster/ }))
    expect(screen.queryByRole('button', { name: '10:00' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '14:00' })).toBeInTheDocument()

    // ...but the day-1 pick PERSISTS in the summary across the switch.
    expect(screen.getByRole('button', { name: /Elimină.*MG ZS/ })).toBeInTheDocument()

    // Add a day-2 pick -> both cars/days stay selected as one group.
    fireEvent.click(screen.getByRole('button', { name: '14:00' }))
    expect(screen.getAllByRole('button', { name: /^Elimină/ })).toHaveLength(2)
  })

  it('shows no day selector for a single-day event', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)
    expect(screen.queryByRole('group', { name: 'Alege ziua' })).not.toBeInTheDocument()
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

  it('keeps the waitlist behind a trigger button (modal), not inline', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)
    // The waitlist form is NOT rendered until the trigger opens the modal.
    expect(screen.queryByLabelText('Mașina preferată (opțional)')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Nu găsești un interval potrivit/ }))
    expect(await screen.findByLabelText('Mașina preferată (opțional)')).toBeInTheDocument()
  })

  it('enables the waitlist trigger only when no slot is selected', async () => {
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)
    const trigger = screen.getByRole('button', { name: /Nu găsești un interval potrivit/ })
    expect(trigger).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: '10:00' })) // pick a slot (car already expanded above)
    expect(trigger).toBeDisabled()
  })

  it('shows a full thank-you screen after joining the waitlist (not back to the form)', async () => {
    submitWaitlist.mockResolvedValue({ ok: true, id: 7 })
    renderPage()
    await screen.findByText('MG ZS')
    fireEvent.click(screen.getByRole('button', { name: /MG ZS/ })) // expand the car accordion (slots hidden until then)
    fill('Nume complet', 'Andrei Popescu')
    fill('Telefon', '0721234567')
    fill('Email', 'andrei@exemplu.ro')
    const [gdpr] = screen.getAllByRole('checkbox')
    fireEvent.click(gdpr)
    fireEvent.click(screen.getByRole('button', { name: /Nu găsești un interval potrivit/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Înscrie-mă pe lista de așteptare/ }))
    // The whole form is replaced by a dedicated thank-you screen.
    expect(await screen.findByText('Ești pe lista de așteptare')).toBeInTheDocument()
    expect(screen.queryByText('Programările tale')).not.toBeInTheDocument()
  })
})
