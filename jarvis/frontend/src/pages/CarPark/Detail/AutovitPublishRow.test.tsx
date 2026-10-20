import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { autovitApi } from '@/api/autovit'
import { AutovitPublishRow } from './AutovitPublishRow'

vi.mock('@/api/autovit', () => ({
  autovitApi: {
    getAccounts: vi.fn(() => Promise.resolve([])),
    getVehicleStatus: vi.fn(() =>
      Promise.resolve([
        {
          id: 1,
          vehicle_id: 1,
          account_id: 5,
          external_advert_id: 'abc123',
          external_url: 'https://autovit.ro/anunt/abc123',
          status: 'unpaid',
          last_sync: '2026-10-19T10:00:00Z',
          last_error: null,
          freshness: 'draft',
        },
      ]),
    ),
    publish: vi.fn(),
    verifyStatus: vi.fn(() => Promise.resolve({ success: true, refreshed: 1, listings: [] })),
    unpublish: vi.fn(() => Promise.resolve({ success: true })),
    deleteAdvert: vi.fn(() => Promise.resolve({ success: true })),
  },
}))

vi.mock('@/api/carpark', () => ({
  carparkApi: {
    getListingSchedule: vi.fn(() => Promise.resolve({ schedule: null })),
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

function renderRow(canEdit = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AutovitPublishRow vehicleId={1} canEdit={canEdit} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AutovitPublishRow', () => {
  it('renders "Draft (neplătit)" for an unpaid listing with freshness=draft', async () => {
    renderRow()
    expect(await screen.findByText('Draft (neplătit)')).toBeInTheDocument()
  })

  it('shows "Șterge definitiv" in the ⋯ menu when canEdit', async () => {
    renderRow(true)
    await screen.findByText('Draft (neplătit)')
    openMenu()
    expect(screen.getByText('Șterge definitiv')).toBeInTheDocument()
  })

  it('hides "Șterge definitiv" AND "Dezactivează anunțul" for a never-published vehicle', async () => {
    // No listings → listing is null → freshness 'not_published'. There is no
    // live advert (no account_id), so neither destructive action may appear —
    // otherwise clicking would POST to /accounts/NaN/{unpublish,delete-advert}.
    vi.mocked(autovitApi.getVehicleStatus).mockResolvedValueOnce([])
    renderRow(true)
    expect(await screen.findByText('Nepublicat')).toBeInTheDocument()
    openMenu()
    expect(screen.queryByText('Șterge definitiv')).not.toBeInTheDocument()
    expect(screen.queryByText('Dezactivează anunțul')).not.toBeInTheDocument()
    // Read-only verify stays available regardless.
    expect(screen.getByText('Verifică status acum')).toBeInTheDocument()
  })
})
