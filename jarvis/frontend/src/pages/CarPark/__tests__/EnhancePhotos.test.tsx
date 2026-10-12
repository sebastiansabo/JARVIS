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
    enhance: vi.fn(() => Promise.resolve({ success: true, created: 1, errors: [] })),
    setPublished: vi.fn(() => Promise.resolve({ success: true, published: true })),
    deleteEnhanced: vi.fn(() => Promise.resolve({ success: true })),
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
})

describe('PhotoGridOverlay — studio enhance', () => {
  it('enhances the selected photos', async () => {
    const photos = [photo({ id: 5, url: 'k5.jpg' }), photo({ id: 6, url: 'k6.jpg', sort_order: 1 })]
    renderOverlay(photos)

    // Enter select mode (mirrors the existing bulk-delete flow).
    fireEvent.click(screen.getByRole('button', { name: 'Selectează' }))
    fireEvent.click(screen.getByLabelText(/selectează poza 5/i))
    fireEvent.click(screen.getByRole('button', { name: /generează studio/i }))

    await waitFor(() => expect(carbackgroundApi.enhance).toHaveBeenCalledWith(9, [5]))
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
