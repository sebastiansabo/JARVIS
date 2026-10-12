// CarBackground admin settings: API key (write-only), house backdrop select,
// credit badge, and the Salvează mutation.
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
        connector: { id: 1, status: 'connected', has_api_key: true, background_id: 'studio-white', api_base_url: '', last_error: null },
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
    saveConfig: vi.fn(() => Promise.resolve({ success: true, connector: { id: 1, status: 'connected', has_api_key: true, background_id: 'grey-concrete', api_base_url: '', last_error: null } })),
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
  it('saves the chosen house backdrop', async () => {
    renderPanel()
    await screen.findByText(/Studio White/i)

    fireEvent.change(screen.getByLabelText(/fundal/i), { target: { value: 'grey-concrete' } })
    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    await waitFor(() =>
      expect(carbackgroundApi.saveConfig).toHaveBeenCalledWith(
        expect.objectContaining({ background_id: 'grey-concrete' }),
      ),
    )
  })

  it('reflects a changed selection away from the initialized saved value', async () => {
    renderPanel()
    await screen.findByText(/Studio White/i)

    const select = screen.getByLabelText(/fundal/i) as HTMLSelectElement
    // Initialized to the saved connector.background_id.
    expect(select.value).toBe('studio-white')

    // Switch to a DIFFERENT valid id — must stick (not snap back to saved).
    fireEvent.change(select, { target: { value: 'grey-concrete' } })
    expect(select.value).toBe('grey-concrete')

    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))
    await waitFor(() =>
      expect(carbackgroundApi.saveConfig).toHaveBeenCalledWith(
        expect.objectContaining({ background_id: 'grey-concrete' }),
      ),
    )
  })

  it('never sends api_key when the field is left blank', async () => {
    renderPanel()
    await screen.findByText(/Studio White/i)

    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    await waitFor(() => expect(carbackgroundApi.saveConfig).toHaveBeenCalled())
    const payload = (carbackgroundApi.saveConfig as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(payload).not.toHaveProperty('api_key')
  })

  it('shows the configured indicator and credit balance, never pre-fills the key input', async () => {
    renderPanel()
    await screen.findByText(/Studio White/i)

    expect(screen.getByText(/configured/i)).toBeInTheDocument()
    await screen.findByText('5')

    const keyInput = screen.getByPlaceholderText(/leave blank to keep/i) as HTMLInputElement
    expect(keyInput.type).toBe('password')
    expect(keyInput.value).toBe('')
  })

  it('sends the typed api_key when provided', async () => {
    renderPanel()
    await screen.findByText(/Studio White/i)

    const keyInput = screen.getByPlaceholderText(/leave blank to keep/i)
    fireEvent.change(keyInput, { target: { value: 'new-secret' } })
    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    await waitFor(() =>
      expect(carbackgroundApi.saveConfig).toHaveBeenCalledWith(
        expect.objectContaining({ api_key: 'new-secret' }),
      ),
    )
  })
})
