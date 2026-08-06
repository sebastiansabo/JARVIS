import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Force the phone layout: keep the real cn / usePersistedState, override only the
// breakpoint hook so HubDrivingPanel renders its bottom pill instead of the
// header-slot toolbar. (Isolated in its own file — the desktop-path suite in
// HubDrivingPanel.test.tsx must keep useIsMobile → false.)
vi.mock('@/lib/utils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/utils')>()
  return { ...actual, useIsMobile: () => true }
})
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 11, company: 'PREMIUM' }] }),
  getBrands: vi.fn().mockResolvedValue({ brands: [] }),
  getContracts: vi.fn().mockResolvedValue({ contracts: [], total: 0, page: 1, per_page: 1000 }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
} }))
vi.mock('@/pages/Hub/DrivingSessionsList', () => ({ default: ({ companyId }: { companyId: number }) => <div>sessions:{companyId}</div> }))
vi.mock('@/pages/Hub/DrivingCalendar', () => ({ default: ({ companyId }: { companyId: number }) => <div>calendar:{companyId}</div> }))
vi.mock('@/pages/Hub/DrivingParkList', () => ({ default: ({ companyId }: { companyId: number }) => <div>park:{companyId}</div> }))
vi.mock('@/pages/FoiParcurs/TestDriveForm', () => ({ default: ({ onCancel }: { onCancel: () => void }) => <div>form<button onClick={onCancel}>x</button></div> }))
vi.mock('@/pages/FoiParcurs/TestDriveReturn', () => ({ default: ({ id }: { id: number }) => <div>return-overlay:{id}</div> }))

import HubDrivingPanel from './HubDrivingPanel'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('HubDrivingPanel — mobile bottom bar', () => {
  beforeEach(() => localStorage.clear())

  it('Back calls onBack (return to Hub grid)', async () => {
    const onBack = vi.fn()
    wrap(<HubDrivingPanel onBack={onBack} />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: /înapoi/i }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('opens the New overlay from the bottom bar', async () => {
    wrap(<HubDrivingPanel onBack={vi.fn()} />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: /sesiune nouă/i }))
    expect(screen.getByText(/^form/)).toBeInTheDocument()
  })

  it('switches to the Calendar view from the bottom bar', async () => {
    wrap(<HubDrivingPanel onBack={vi.fn()} />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: 'Calendar' }))
    expect(await screen.findByText(/calendar:11/)).toBeInTheDocument()
  })

  it('switches to the read-only Parc (Driving Park) view from the bottom bar', async () => {
    wrap(<HubDrivingPanel onBack={vi.fn()} />)
    await screen.findByText(/sessions:11/)
    fireEvent.click(screen.getByRole('button', { name: 'Parc' }))
    expect(await screen.findByText(/park:11/)).toBeInTheDocument()
  })
})
