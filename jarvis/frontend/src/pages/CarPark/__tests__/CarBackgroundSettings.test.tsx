// CarBackground admin settings: API key (write-only), a multi-select list of
// PREFERRED studio backdrops with one starred as the default, a credit badge,
// and the Salvează mutation.
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { carbackgroundApi } from '@/api/carbackground'
import { CarBackgroundSettings } from '../CarBackgroundSettings'

vi.mock('@/api/carbackground', () => ({
  carbackgroundApi: {
    getConfig: vi.fn(() =>
      Promise.resolve({
        success: true,
        configured: true,
        connector: {
          id: 1, status: 'connected', has_api_key: true,
          background_id: 'studio-white',
          preferred_background_ids: ['studio-white'],
          api_base_url: '', last_error: null,
        },
      }),
    ),
    listBackgrounds: vi.fn(() =>
      Promise.resolve({
        success: true,
        backgrounds: [
          { id: 'studio-white', name: 'Studio White' },
          { id: 'grey-concrete', name: 'Grey Concrete' },
        ],
      }),
    ),
    credits: vi.fn(() => Promise.resolve({ success: true, balance: 5 })),
    saveConfig: vi.fn(() =>
      Promise.resolve({
        success: true,
        connector: {
          id: 1, status: 'connected', has_api_key: true,
          background_id: 'grey-concrete',
          preferred_background_ids: ['studio-white', 'grey-concrete'],
          api_base_url: '', last_error: null,
        },
      }),
    ),
  },
}))

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <CarBackgroundSettings />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CarBackgroundSettings', () => {
  it('initializes preferred checkboxes and the default radio from the saved connector', async () => {
    renderPanel()
    const studioCheck = (await screen.findByLabelText(/Preferă Studio White/i)) as HTMLInputElement
    const greyCheck = screen.getByLabelText(/Preferă Grey Concrete/i) as HTMLInputElement
    const studioDefault = screen.getByLabelText(/Implicit: Studio White/i)

    expect(studioCheck.checked).toBe(true)   // in preferred_background_ids
    expect(greyCheck.checked).toBe(false)    // not preferred
    expect(studioDefault).toHaveAttribute('aria-checked', 'true') // == background_id
  })

  it('adds a checked background to preferred and saves the list', async () => {
    renderPanel()
    await screen.findByLabelText(/Preferă Studio White/i)

    fireEvent.click(screen.getByLabelText(/Preferă Grey Concrete/i))
    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    await waitFor(() => expect(carbackgroundApi.saveConfig).toHaveBeenCalled())
    const payload = (carbackgroundApi.saveConfig as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(payload.preferred_background_ids).toEqual(
      expect.arrayContaining(['studio-white', 'grey-concrete']),
    )
    expect(payload.background_id).toBe('studio-white')
  })

  it('starring a background as default auto-adds it to preferred and sends it', async () => {
    renderPanel()
    await screen.findByLabelText(/Preferă Studio White/i)

    // Grey Concrete starts unpreferred; making it default must pull it in.
    fireEvent.click(screen.getByLabelText(/Implicit: Grey Concrete/i))
    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    await waitFor(() => expect(carbackgroundApi.saveConfig).toHaveBeenCalled())
    const payload = (carbackgroundApi.saveConfig as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(payload.background_id).toBe('grey-concrete')
    expect(payload.preferred_background_ids).toContain('grey-concrete')
  })

  it('never sends api_key when the field is left blank', async () => {
    renderPanel()
    await screen.findByLabelText(/Preferă Studio White/i)

    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    await waitFor(() => expect(carbackgroundApi.saveConfig).toHaveBeenCalled())
    const payload = (carbackgroundApi.saveConfig as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(payload).not.toHaveProperty('api_key')
  })

  it('sends the typed api_key when provided', async () => {
    renderPanel()
    await screen.findByLabelText(/Preferă Studio White/i)

    fireEvent.change(screen.getByPlaceholderText(/leave blank to keep/i), { target: { value: 'new-secret' } })
    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    await waitFor(() =>
      expect(carbackgroundApi.saveConfig).toHaveBeenCalledWith(
        expect.objectContaining({ api_key: 'new-secret' }),
      ),
    )
  })

  it('shows the configured indicator and credit balance, never pre-fills the key input', async () => {
    renderPanel()
    await screen.findByLabelText(/Preferă Studio White/i)

    expect(screen.getByText(/configured/i)).toBeInTheDocument()
    await screen.findByText('5')

    const keyInput = screen.getByPlaceholderText(/leave blank to keep/i) as HTMLInputElement
    expect(keyInput.type).toBe('password')
    expect(keyInput.value).toBe('')
  })
})
