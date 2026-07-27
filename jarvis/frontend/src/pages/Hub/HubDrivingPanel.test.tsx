import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 11, company: 'PREMIUM' }] }),
  getBrands: vi.fn().mockResolvedValue({ brands: [] }),
} }))
vi.mock('@/pages/FoiParcurs/index', () => ({
  SessionsTab: ({ companyId }: { companyId: number }) => <div>sessions:{companyId}</div>,
}))
vi.mock('@/pages/FoiParcurs/CalendarTab', () => ({
  CalendarTab: ({ companyId }: { companyId: number }) => <div>calendar:{companyId}</div>,
}))
vi.mock('@/pages/FoiParcurs/TestDriveForm', () => ({ default: ({ onCancel }: { onCancel: () => void }) => <div>form<button onClick={onCancel}>x</button></div> }))
vi.mock('@/pages/FoiParcurs/TestDriveReturn', () => ({ default: () => <div>return</div> }))

import HubDrivingPanel from './HubDrivingPanel'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('HubDrivingPanel', () => {
  it('renders the Sessions tab by default and can open the New overlay', async () => {
    wrap(<HubDrivingPanel />)
    expect(await screen.findByText(/sessions:11/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /driving session nou/i }))
    expect(screen.getByText('form')).toBeInTheDocument()
  })

  it('switches to the Calendar tab', async () => {
    wrap(<HubDrivingPanel />)
    // Radix Tabs' trigger selects on `mousedown` (not `click`) — see
    // @radix-ui/react-tabs's Trigger, which wires selection to onMouseDown/
    // onFocus/onKeyDown, never onClick. fireEvent.click alone never fires
    // any of those, so the tab wouldn't switch; mousedown is the real
    // interaction that drives it (no @testing-library/user-event dependency
    // in this project to fall back on).
    fireEvent.mouseDown(await screen.findByRole('tab', { name: /calendar/i }))
    expect(await screen.findByText(/calendar:11/)).toBeInTheDocument()
  })
})
