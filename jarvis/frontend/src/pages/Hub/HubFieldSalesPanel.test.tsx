import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getTodayVisits = vi.fn()
const getMyVisits = vi.fn()
const getFieldSalesCompanies = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: {
    getTodayVisits: (...a: unknown[]) => getTodayVisits(...a),
    getMyVisits: (...a: unknown[]) => getMyVisits(...a),
    getFieldSalesCompanies: (...a: unknown[]) => getFieldSalesCompanies(...a),
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

const ONE_COMPANY = { success: true, companies: [{ id: 5, company: 'AUTOWORLD S.R.L.' }], default_company_id: 5 }
const TWO_COMPANIES = {
  success: true,
  companies: [{ id: 5, company: 'AUTOWORLD S.R.L.' }, { id: 7, company: 'PREMIUM S.R.L.' }],
  default_company_id: 7,
}

describe('HubFieldSalesPanel', () => {
  // Radix Select (used by the multi-company selector) needs a couple of DOM
  // APIs jsdom doesn't implement — opening the listbox / selecting an item
  // would otherwise throw. Stubbed once for this file only.
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
    window.HTMLElement.prototype.releasePointerCapture = vi.fn()
  })

  beforeEach(() => {
    getTodayVisits.mockReset()
    getMyVisits.mockReset()
    getFieldSalesCompanies.mockReset()
    getMyVisits.mockResolvedValue({ success: true, visits: [], date_from: '', date_to: '' })
    // Default: single allowed company -> every pre-existing test below (none
    // of which cares about the selector) exercises the locked-label path.
    getFieldSalesCompanies.mockResolvedValue(ONE_COMPANY)
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
    // Setting a start time with no explicit end should default the end to
    // start+1h (Sfarsit field left untouched by the user).
    fireEvent.change(screen.getByLabelText(/Or[aă]/i), { target: { value: '09:00' } })
    fireEvent.click(screen.getByRole('button', { name: /salveaza vizita/i }))
    // Use RTL's waitFor (not vi.waitFor): it wraps its polling in act(), so the
    // mutation's onSuccess chain (invalidateQueries → getTodayVisits refetch +
    // setOverlay(null)) settles under act() → no act() warning, pristine output.
    // createVisit is wired as `mutationFn: fieldSalesApi.createVisit` directly
    // (not wrapped in a lambda), so TanStack Query v5 invokes it with a second
    // internal mutationFnContext arg — assert that too rather than weakening
    // the match to a single positional arg.
    await waitFor(() => expect(mod.fieldSalesApi.createVisit).toHaveBeenCalledWith(
      expect.objectContaining({ planned_time: '09:00', planned_end_time: '10:00' }),
      expect.anything(),
    ))
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

  describe('company selector', () => {
    it('renders a locked label (no dropdown) when only one company is allowed', async () => {
      getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
      wrap(<HubFieldSalesPanel />)
      expect(await screen.findByText('AUTOWORLD S.R.L.')).toBeInTheDocument()
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    })

    it('shows both companies and defaults the value to default_company_id when more than one is allowed', async () => {
      getFieldSalesCompanies.mockResolvedValue(TWO_COMPANIES)
      getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
      wrap(<HubFieldSalesPanel />)

      const trigger = await screen.findByRole('combobox')
      // default_company_id is 7 -> "PREMIUM S.R.L." must be the selected value.
      expect(await within(trigger).findByText('PREMIUM S.R.L.')).toBeInTheDocument()

      // getTodayVisits is refetched once the effect resolves companyId=0 ->
      // 7 (the default), so its LAST call must carry the default company.
      // The date arg is whatever todayStr() returns at test-run time, so only
      // the company_id (2nd positional arg) is pinned down here.
      await waitFor(() => expect(getTodayVisits).toHaveBeenLastCalledWith(expect.any(String), 7))
    })

    it('refetches visits with the newly selected company_id when the user switches company', async () => {
      getFieldSalesCompanies.mockResolvedValue(TWO_COMPANIES)
      getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
      wrap(<HubFieldSalesPanel />)

      const trigger = await screen.findByRole('combobox')
      await waitFor(() => expect(getTodayVisits).toHaveBeenLastCalledWith(expect.any(String), 7))

      fireEvent.click(trigger)
      fireEvent.click(await screen.findByRole('option', { name: 'AUTOWORLD S.R.L.' }))

      await waitFor(() => expect(getTodayVisits).toHaveBeenLastCalledWith(expect.any(String), 5))
      await waitFor(() => expect(getMyVisits).toHaveBeenLastCalledWith(expect.any(String), expect.any(String), 5))
    })

    it('shows a no-company state and blocks the add flow when the user has no company assigned', async () => {
      // A user who can reach Field Sales (can_access_field_sales) but has no
      // company (users.company_id NULL + no company_responsables) -> companyId
      // stays 0. The add entry point + the (unscoped, cross-tenant) client
      // search must be unreachable, and the panel must say so explicitly
      // rather than showing the generic "add a visit to start" empty state.
      getFieldSalesCompanies.mockResolvedValue({ success: true, companies: [], default_company_id: null })
      getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
      wrap(<HubFieldSalesPanel />)

      // (a) the no-company message renders (locked chip + in place of the
      //     generic empty state — hence >= 1, not exactly 1).
      await waitFor(() => expect(screen.getAllByText(/nu aveți nicio companie alocată/i).length).toBeGreaterThanOrEqual(1))
      // …and NOT the generic "add a visit to start planning" empty state.
      expect(screen.queryByText(/nicio vizita planificata/i)).not.toBeInTheDocument()

      // (b) the "Adaugă" entry point is gone -> the add flow can't start.
      expect(screen.queryByRole('button', { name: /adauga/i })).not.toBeInTheDocument()

      // (c) no add form is mounted, so its (unscoped) client search input never
      //     exists and no search can fire.
      expect(screen.queryByPlaceholderText(/cauta client/i)).not.toBeInTheDocument()

      // The company-scoped visit queries stay disabled (companyId 0) so nothing
      // is fetched unscoped either.
      expect(getTodayVisits).not.toHaveBeenCalled()
    })

    it('ignores a stale persisted company id when the user no longer has any allowed company', async () => {
      // A user who previously had company 5 (persisted in localStorage) loses
      // all company access -> the companies query resolves empty, so 5 is no
      // longer a confirmed-allowed company (companyReady is false). Crucially
      // the today query must NOT fire even transiently for company 5 on first
      // mount (the persisted 5 reads > 0), and the no-company state + hidden
      // Adaugă button must agree — no off-tenant fetch, no dead add flow.
      localStorage.setItem('hub-fs-company', '5')
      getFieldSalesCompanies.mockResolvedValue({ success: true, companies: [], default_company_id: null })
      getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
      wrap(<HubFieldSalesPanel />)

      await waitFor(() => expect(screen.getAllByText(/nu aveți nicio companie alocată/i).length).toBeGreaterThanOrEqual(1))
      expect(screen.queryByRole('button', { name: /adauga/i })).not.toBeInTheDocument()
      // companyReady is false for the stale/disallowed id -> the today query
      // never fires for company 5, not even on the first render.
      expect(getTodayVisits).not.toHaveBeenCalled()
    })
  })
})
