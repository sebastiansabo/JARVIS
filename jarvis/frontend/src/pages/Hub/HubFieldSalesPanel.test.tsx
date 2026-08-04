import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getTodayVisits = vi.fn()
const getMyVisits = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: {
    getTodayVisits: (...a: unknown[]) => getTodayVisits(...a),
    getMyVisits: (...a: unknown[]) => getMyVisits(...a),
    searchClients: vi.fn(), createVisit: vi.fn(),
    checkin: vi.fn(), checkout: vi.fn(), addNote: vi.fn(),
    getVisit: vi.fn(), getClient360: vi.fn(), refreshFiscal: vi.fn(),
  },
}))
// VisitDetailDialog is heavy; stub it for panel tests. A close button is
// exposed so tests can drive onOpenChange(false) the way the real dialog
// does after an in-dialog edit or an explicit close.
vi.mock('@/pages/FieldSales/VisitDetailDialog', () => ({
  VisitDetailDialog: ({ open, visitId, onOpenChange }: { open: boolean; visitId: number | null; onOpenChange: (o: boolean) => void }) =>
    open ? <div>detail:{visitId}<button onClick={() => onOpenChange(false)}>mock-close-detail</button></div> : null,
}))
// FieldSalesCalendar does its own data fetching/rendering (covered by its own
// test file); stub it here so the panel test stays focused on tab wiring.
vi.mock('@/pages/Hub/FieldSalesCalendar', () => ({
  default: () => <div>calendar-tab</div>,
}))

import HubFieldSalesPanel from './HubFieldSalesPanel'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

const VISIT = {
  id: 9, kam_id: 3, client_id: 760, planned_date: '2026-08-04', planned_time: '13:30',
  visit_type: 'renewal_discussion', status: 'planned', client_name: 'DEMO Construct Grup SRL',
  kam_name: 'George Pop', renewal_score: 70, goals: 'Reinnoire',
}

describe('HubFieldSalesPanel', () => {
  beforeEach(() => {
    getTodayVisits.mockReset()
    getMyVisits.mockReset()
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: '', date_to: '' })
    localStorage.clear()
  })

  it('lists today visits and shows the quick-stat counts', async () => {
    getTodayVisits.mockResolvedValue({ success: true, visits: [VISIT], date: '2026-08-04' })
    wrap(<HubFieldSalesPanel />)
    expect(await screen.findByText('DEMO Construct Grup SRL')).toBeInTheDocument()
    // one planned visit -> "1" appears in the Planificate stat tile
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
  })

  it('shows the empty state when there are no visits', async () => {
    getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
    wrap(<HubFieldSalesPanel />)
    expect(await screen.findByText(/nicio vizit/i)).toBeInTheDocument()
  })

  it('add-visit: submit is disabled until a client is selected, then calls createVisit', async () => {
    const { fireEvent } = await import('@testing-library/react')
    const mod = await import('@/api/fieldSales')
    getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
    ;(mod.fieldSalesApi.searchClients as ReturnType<typeof vi.fn>) = vi.fn().mockResolvedValue({ success: true, clients: [{ id: 760, display_name: 'ACME SRL', client_type: 'company' }], count: 1 })
    ;(mod.fieldSalesApi.createVisit as ReturnType<typeof vi.fn>) = vi.fn().mockResolvedValue({ success: true, visit: { id: 1 } })

    wrap(<HubFieldSalesPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /adauga/i }))
    const submit = await screen.findByRole('button', { name: /salveaza vizita/i })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText(/cauta client/i), { target: { value: 'ACME' } })
    fireEvent.click(await screen.findByText('ACME SRL'))
    expect(screen.getByRole('button', { name: /salveaza vizita/i })).not.toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /salveaza vizita/i }))
    // Use RTL's waitFor (not vi.waitFor): it wraps its polling in act(), so the
    // mutation's onSuccess chain (invalidateQueries → getTodayVisits refetch +
    // setOverlay(null)) settles under act() → no act() warning, pristine output.
    await waitFor(() => expect(mod.fieldSalesApi.createVisit).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('button', { name: /salveaza vizita/i })).not.toBeInTheDocument())
  })

  it('check-in fires the checkin mutation even when geolocation is unavailable', async () => {
    const { fireEvent } = await import('@testing-library/react')
    const mod = await import('@/api/fieldSales')
    getTodayVisits.mockResolvedValue({ success: true, visits: [VISIT], date: '2026-08-04' })
    ;(mod.fieldSalesApi.checkin as ReturnType<typeof vi.fn>) = vi.fn().mockResolvedValue({ success: true, visit: { ...VISIT, status: 'in_progress' } })
    // no navigator.geolocation in jsdom -> best-effort path calls checkin with {}
    wrap(<HubFieldSalesPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /check-in/i }))
    // RTL's waitFor (not vi.waitFor) wraps polling in act(), so the mutation's
    // onSuccess chain (invalidateQueries + setOverlay) settles under act() ->
    // no act() warning, pristine output. Await the settled end-state (detail
    // overlay open) before the test ends.
    await waitFor(() => expect(mod.fieldSalesApi.checkin).toHaveBeenCalledWith(9, {}))
    await waitFor(() => expect(screen.getByText('detail:9')).toBeInTheDocument())
  })

  it('guards against a double-submit when CHECK-IN is tapped twice before geolocation resolves', async () => {
    const { fireEvent } = await import('@testing-library/react')
    const mod = await import('@/api/fieldSales')
    getTodayVisits.mockResolvedValue({ success: true, visits: [VISIT], date: '2026-08-04' })
    ;(mod.fieldSalesApi.checkin as ReturnType<typeof vi.fn>) = vi.fn().mockResolvedValue({ success: true, visit: { ...VISIT, status: 'in_progress' } })
    wrap(<HubFieldSalesPanel />)
    const btn = await screen.findByRole('button', { name: /check-in/i })
    // Two rapid taps fired back-to-back, before the getCoords() promise (and
    // therefore checkinMut.mutate) has a chance to settle.
    fireEvent.click(btn)
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByText('detail:9')).toBeInTheDocument())
    expect(mod.fieldSalesApi.checkin).toHaveBeenCalledTimes(1)
  })

  it('surfaces an inline error when the check-in POST fails', async () => {
    const { fireEvent } = await import('@testing-library/react')
    const mod = await import('@/api/fieldSales')
    getTodayVisits.mockResolvedValue({ success: true, visits: [VISIT], date: '2026-08-04' })
    ;(mod.fieldSalesApi.checkin as ReturnType<typeof vi.fn>) = vi.fn().mockRejectedValue({ data: { error: 'Vizita nu mai este disponibila' } })
    wrap(<HubFieldSalesPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /check-in/i }))
    // RTL's waitFor wraps polling in act(), so the mutation's onError state
    // update settles under act() -> no act() warning, pristine output.
    await waitFor(() => expect(screen.getByText('Vizita nu mai este disponibila')).toBeInTheDocument())
    // detail overlay must NOT open on failure
    expect(screen.queryByText('detail:9')).not.toBeInTheDocument()
  })

  it('refreshes the Hub field-sales lists when the detail dialog closes (e.g. after an in-dialog edit)', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const spy = vi.spyOn(qc, 'invalidateQueries')
    getTodayVisits.mockResolvedValue({ success: true, visits: [VISIT], date: '2026-08-04' })

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><HubFieldSalesPanel /></MemoryRouter>
      </QueryClientProvider>
    )

    // Open the detail overlay (VisitDetailDialog is mocked above) by tapping
    // the card itself, then close it the way the real dialog does after an
    // in-dialog edit (updateMutation succeeds -> handleClose -> onOpenChange(false)).
    fireEvent.click(await screen.findByText('DEMO Construct Grup SRL'))
    expect(await screen.findByText('detail:9')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /mock-close-detail/i }))

    expect(screen.queryByText('detail:9')).not.toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: expect.arrayContaining(['field-sales-visits']) }))
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: expect.arrayContaining(['field-sales-mine']) }))
    expect(spy).toHaveBeenCalledWith({ queryKey: ['field-sales-cal'] })

    // Both today and upcoming queries are active (mounted) -> invalidateQueries
    // triggers an automatic refetch. Wait for it under RTL's act-wrapped
    // waitFor so the settling state updates don't leak past the test as
    // act() warnings.
    await waitFor(() => expect(getTodayVisits.mock.calls.length).toBeGreaterThan(1))
    await waitFor(() => expect(getMyVisits.mock.calls.length).toBeGreaterThan(1))
  })

  it('shows upcoming visits below the today list on the Azi tab', async () => {
    getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
    getMyVisits.mockResolvedValue({
      success: true,
      visits: [{ ...VISIT, id: 21, planned_date: '2026-08-10', client_name: 'Viitor Client SRL' }],
      date_from: '2026-08-05', date_to: '2026-09-03',
    })
    wrap(<HubFieldSalesPanel />)
    expect(await screen.findByText(/vizite viitoare/i)).toBeInTheDocument()
    expect(screen.getByText('Viitor Client SRL')).toBeInTheDocument()
  })

  it('switches to the Calendar tab', async () => {
    getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
    wrap(<HubFieldSalesPanel />)
    // Radix Tabs' trigger selects on `mousedown`, not `click` — see the same
    // note in HubDrivingPanel.test.tsx.
    fireEvent.mouseDown(await screen.findByRole('tab', { name: /calendar/i }))
    expect(await screen.findByText('calendar-tab')).toBeInTheDocument()
  })
})
