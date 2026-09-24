import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// A public test-drive fișă is self-contained: identity + licence live on the row
// itself. When staff hit "Începe sesiunea" (activate), the form must PREFILL the
// licence photo/number/expiry the customer already provided, instead of showing
// an empty *mandatory* upload that forces re-capture.
const { PHOTO } = vi.hoisted(() => ({ PHOTO: 'data:image/png;base64,PREFILLED' }))

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 11, company: 'PREMIUM' }] }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  getGeneralConditions: vi.fn().mockResolvedValue({ text: '', brand: '' }),
  getDocumentTypes: vi.fn().mockResolvedValue({ types: [
    { key: 'sales', label: 'Vânzări', is_rental: false, is_default: true, is_active: true },
  ] }),
  getTestDrive: vi.fn().mockResolvedValue({
    success: true,
    inspection: null,
    contract: {
      id: 5, status: 'PLANNED', route_type: 'TD', company_id: 11, vin: 'VIN1',
      client_id: 999, client_name: 'Roxana Biris', client_phone: '+40738764546',
      client_email: 'roxana@example.com',
      driver_license_photo: PHOTO, driver_license_number: 'AB123456',
      driver_license_expiry: '2030-01-01',
      departure_datetime: '2026-09-30T08:00', return_datetime: '2026-09-30T08:30',
      km_start: 0, distance_km: 0, fuel_gauge_start_level: 'full',
    },
  }),
} }))
vi.mock('@/api/crm', () => ({ crmApi: {
  getClient: vi.fn().mockResolvedValue({ id: 999, display_name: 'Roxana Biris', client_type: 'person', phone: '+40738764546', email: 'roxana@example.com' }),
  listClientContacts: vi.fn().mockResolvedValue({ contacts: [] }),
} }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { name: 'Test Advisor' } }) }))
vi.mock('@/components/shared/SignatureCanvas', () => ({
  default: ({ onSave }: { onSave: (s: string) => void }) => (<button onClick={() => onSave('data:sig')}>sign</button>),
}))

import TestDriveForm from './TestDriveForm'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('TestDriveForm activate prefill', () => {
  it('prefills the licence photo from the planned fișă', async () => {
    wrap(<TestDriveForm activateId={5} />)
    const img = await screen.findByAltText('Permis de conducere')
    expect(img).toHaveAttribute('src', PHOTO)
  })
})
