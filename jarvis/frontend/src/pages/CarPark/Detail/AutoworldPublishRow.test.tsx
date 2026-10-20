import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { carparkApi } from '@/api/carpark'
import { AutoworldPublishRow } from './AutoworldPublishRow'

vi.mock('@/api/shopify', () => ({
  shopifyApi: {
    vehicleStatus: vi.fn(() =>
      Promise.resolve({
        success: true,
        listing: {
          status: 'published',
          external_url: 'https://autoworld.ro/products/x',
          last_sync: '2026-10-19T10:00:00Z',
        },
        freshness: 'up_to_date',
      }),
    ),
    previewVehicle: vi.fn(() => Promise.resolve({ success: true, eligible: true, warnings: [] })),
    publishVehicle: vi.fn(() => Promise.resolve({ success: true })),
    verifyStatus: vi.fn(() => Promise.resolve({ success: true, deleted_on_shopify: false, freshness: 'up_to_date' })),
    unpublishVehicle: vi.fn(() => Promise.resolve({ success: true })),
  },
}))

vi.mock('@/api/carpark', () => ({
  carparkApi: {
    getListingSchedule: vi.fn(() =>
      Promise.resolve({ schedule: { cadence: '1h', enabled: true, next_run_at: null } }),
    ),
    setListingSchedule: vi.fn(() =>
      Promise.resolve({ schedule: { cadence: 'manual', enabled: false, next_run_at: null } }),
    ),
  },
}))

// Radix's DropdownMenuTrigger opens on `pointerdown` (mirrors PlatformPublishRow.test.tsx).
function openMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /mai multe|opțiuni/i }), {
    button: 0,
    ctrlKey: false,
  })
}

function renderRow() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AutoworldPublishRow vehicleId={1} canEdit />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AutoworldPublishRow', () => {
  it('renders "La zi" when status returns freshness=up_to_date', async () => {
    renderRow()
    expect(await screen.findByText('La zi')).toBeInTheDocument()
  })

  it('toggling Auto off calls setListingSchedule with platform=shopify, cadence=manual, enabled=false', async () => {
    renderRow()
    await screen.findByText('La zi')
    openMenu()
    const switchEl = await screen.findByRole('switch')
    await waitFor(() => expect(switchEl).toHaveAttribute('aria-checked', 'true'))
    fireEvent.click(switchEl)
    await waitFor(() =>
      expect(carparkApi.setListingSchedule).toHaveBeenCalledWith(1, {
        platform: 'shopify',
        cadence: 'manual',
        enabled: false,
      }),
    )
  })
})
