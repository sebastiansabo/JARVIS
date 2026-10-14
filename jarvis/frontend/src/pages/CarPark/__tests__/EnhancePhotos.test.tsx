// Gallery studio-enhance: select mode → "Generează studio" → enhance mutation,
// plus the publish toggle + original↔studio preview switch on enhanced tiles.
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { carbackgroundApi } from '@/api/carbackground'
import { PhotoGridOverlay } from '../Detail'
import type { VehiclePhoto } from '@/types/carpark'

vi.mock('@/api/carbackground', () => ({
  carbackgroundApi: {
    enhance: vi.fn(() => Promise.resolve({ success: true, queued: 1, job_id: 1 })),
    enhanceStatus: vi.fn(() =>
      Promise.resolve({ success: true, running: false, total: 0, done: 0, created: 0, errors: [], background_id: null }),
    ),
    setPublished: vi.fn(() => Promise.resolve({ success: true, published: true })),
    deleteEnhanced: vi.fn(() => Promise.resolve({ success: true })),
    getConfig: vi.fn(() =>
      Promise.resolve({
        success: true,
        configured: true,
        connector: {
          id: 1, status: 'connected', has_api_key: true,
          background_id: 'studio-white',
          preferred_background_ids: ['studio-white', 'grey-concrete'],
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
  },
}))

function photo(overrides: Partial<VehiclePhoto>): VehiclePhoto {
  return {
    id: 1,
    vehicle_id: 9,
    url: 'k.jpg',
    thumbnail_url: null,
    sort_order: 0,
    is_primary: false,
    photo_type: 'gallery',
    caption: null,
    file_size: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderOverlay(photos: VehiclePhoto[], canEdit = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PhotoGridOverlay photos={photos} vehicleId={9} canEdit={canEdit} onClose={() => {}} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // clearAllMocks keeps implementations, so reset the status mock to idle each
  // test — otherwise a running-job override leaks into later tests and leaves
  // the "Generează studio" button disabled.
  vi.mocked(carbackgroundApi.enhanceStatus).mockResolvedValue({
    success: true, running: false, total: 0, done: 0, created: 0, errors: [], background_id: null,
  } as any)
})

describe('PhotoGridOverlay — studio enhance', () => {
  it('queues the selected photos for background enhancement', async () => {
    const photos = [photo({ id: 5, url: 'k5.jpg' }), photo({ id: 6, url: 'k6.jpg', sort_order: 1 })]
    renderOverlay(photos)

    // Enter select mode (mirrors the existing bulk-delete flow).
    fireEvent.click(screen.getByRole('button', { name: 'Selectează' }))
    fireEvent.click(screen.getByLabelText(/selectează poza 5/i))
    fireEvent.click(screen.getByRole('button', { name: /generează studio/i }))

    await waitFor(() => expect(carbackgroundApi.enhance).toHaveBeenCalled())
    const [vid, ids] = (carbackgroundApi.enhance as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(vid).toBe(9)
    expect(ids).toEqual([5])
  })

  it('shows a live progress count while a job is running', async () => {
    vi.mocked(carbackgroundApi.enhanceStatus).mockResolvedValue({
      success: true, running: true, total: 7, done: 3, created: 3, errors: [], background_id: null,
    } as any)
    renderOverlay([photo({ id: 5 })])
    // Resumes/shows progress straight from the server (survives reload).
    expect(await screen.findByText(/3\s*\/\s*7/)).toBeInTheDocument()
  })

  it('refetches the vehicle while a job runs so enhanced photos and their publish toggle appear without a manual refresh', async () => {
    vi.mocked(carbackgroundApi.enhanceStatus).mockResolvedValue({
      success: true, running: true, total: 3, done: 1, created: 1, errors: [], background_id: null,
    } as any)
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    const spy = vi.spyOn(qc, 'invalidateQueries')
    render(
      <QueryClientProvider client={qc}>
        <PhotoGridOverlay photos={[photo({ id: 5 })]} vehicleId={9} canEdit onClose={() => {}} />
      </QueryClientProvider>,
    )
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({ queryKey: ['carpark', 'vehicle', 9] }),
    )
  })

  it('passes the chosen preferred background to enhance', async () => {
    const photos = [photo({ id: 5, url: 'k5.jpg' })]
    renderOverlay(photos)

    fireEvent.click(screen.getByRole('button', { name: 'Selectează' }))
    fireEvent.click(screen.getByLabelText(/selectează poza 5/i))
    // Picker is populated from the preferred list; switch off the default.
    fireEvent.change(await screen.findByLabelText(/fundal studio/i), { target: { value: 'grey-concrete' } })
    fireEvent.click(screen.getByRole('button', { name: /generează studio/i }))

    await waitFor(() =>
      expect(carbackgroundApi.enhance).toHaveBeenCalledWith(9, [5], 'grey-concrete'),
    )
  })

  it('defaults the picker to the starred default background', async () => {
    const photos = [photo({ id: 5, url: 'k5.jpg' })]
    renderOverlay(photos)

    fireEvent.click(screen.getByRole('button', { name: 'Selectează' }))
    fireEvent.click(screen.getByLabelText(/selectează poza 5/i))
    const picker = (await screen.findByLabelText(/fundal studio/i)) as HTMLSelectElement
    expect(picker.value).toBe('studio-white') // connector.background_id
  })

  it('does not show the enhance action with nothing selected', () => {
    const photos = [photo({ id: 5 }), photo({ id: 6, sort_order: 1 })]
    renderOverlay(photos)
    fireEvent.click(screen.getByRole('button', { name: 'Selectează' }))
    expect(screen.queryByRole('button', { name: /generează studio/i })).toBeNull()
  })

  it('shows an Enhanced badge and toggles the publish switch for an enhanced photo', async () => {
    const photos = [
      photo({
        id: 5,
        enhanced_url: 'k5-studio.jpg',
        enhanced_thumbnail_url: 'k5-studio-thumb.jpg',
        enhanced_published: false,
      }),
    ]
    // A single photo renders the plain (non-sortable) grid branch, which is
    // the simplest to assert the enhanced controls against.
    renderOverlay(photos)

    expect(screen.getByText('Enhanced')).toBeInTheDocument()

    const publishSwitch = screen.getByLabelText(/publică varianta studio/i)
    fireEvent.click(publishSwitch)

    await waitFor(() => expect(carbackgroundApi.setPublished).toHaveBeenCalledWith(5, true))
  })

  it('toggles the original↔studio preview', () => {
    const photos = [
      photo({
        id: 5,
        enhanced_url: 'k5-studio.jpg',
      }),
    ]
    renderOverlay(photos)

    // Defaults to the studio label; clicking flips to the original.
    expect(screen.getByText('Studio')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Studio'))
    expect(screen.getByText('Original')).toBeInTheDocument()
  })
})
