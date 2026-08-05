import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fieldSalesApi } from '@/api/fieldSales'

const addNote = vi.fn()
vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: { addNote: (...a: unknown[]) => addNote(...a) } }))
import NoteCaptureModal from './NoteCaptureModal'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('NoteCaptureModal', () => {
  beforeEach(() => addNote.mockClear())
  afterEach(() => {
    vi.restoreAllMocks()
    // The reject-path test swaps in a fresh rejecting vi.fn() on
    // fieldSalesApi.addNote; re-wire it back to the shared `addNote` mock so a
    // future appended test can't inherit that rejecting stub (no ordering dep).
    ;(fieldSalesApi as { addNote: (...a: unknown[]) => unknown }).addNote = (...a) => addNote(...a)
  })

  it('submits the raw note and renders the AI summary', async () => {
    addNote.mockResolvedValue({ success: true, note: { id: 1, raw_note: 'x', created_at: '' }, structured_note: {
      visit_summary: 'Rezumat AI', contact_person: null, vehicles_discussed: [], commitments_made: [],
      next_steps: [], opportunity_value_eur: null, decision_timeline: null, follow_up_date: null, objections: [], risk_flags: [],
    } })
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'discutie buna' } })
    fireEvent.click(screen.getByRole('button', { name: /proceseaz|finalizeaz|salveaz/i }))
    expect(await screen.findByText('Rezumat AI')).toBeInTheDocument()
    expect(addNote).toHaveBeenCalledWith(9, { raw_note: 'discutie buna' })
  })

  it('renders structured sections (vehicles, next steps, opportunity, risk flags) and saving invalidates queries + calls onDone', async () => {
    addNote.mockResolvedValue({
      success: true,
      note: { id: 1, raw_note: 'x', created_at: '' },
      structured_note: {
        visit_summary: 'Discutie despre reinnoire flota',
        contact_person: 'Ion Popescu',
        vehicles_discussed: [{ action: 'replace', current_vehicle: 'BMW X3 2019', interested_in: 'BMW X5', budget_eur: 60000 }],
        commitments_made: ['Trimite oferta pana vineri'],
        next_steps: [{ action: 'Programeaza test drive', owner: 'KAM', deadline: '2026-08-10' }],
        opportunity_value_eur: 60000,
        decision_timeline: '30 zile',
        follow_up_date: '2026-08-10',
        objections: ['Pret ridicat'],
        risk_flags: ['Client compara cu concurenta'],
      },
    })
    const onDone = vi.fn()
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={onDone} onCancel={() => {}} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'discutie buna' } })
    fireEvent.click(screen.getByRole('button', { name: /proceseaz/i }))

    expect(await screen.findByText('Discutie despre reinnoire flota')).toBeInTheDocument()
    expect(screen.getByText(/Ion Popescu/)).toBeInTheDocument()
    expect(screen.getByText(/BMW X5/)).toBeInTheDocument()
    expect(screen.getByText('Trimite oferta pana vineri')).toBeInTheDocument()
    expect(screen.getByText('Programeaza test drive')).toBeInTheDocument()
    expect(screen.getByText('Pret ridicat')).toBeInTheDocument()
    expect(screen.getByText('Client compara cu concurenta')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /salveaz/i }))
    // RTL's waitFor wraps polling in act(), so the invalidateQueries + onDone
    // chain triggered from handleSave settles under act() -> no act() warning.
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('partial structured_note (array fields missing) renders the review without crashing', async () => {
    // Regression: the AI can return a partial/differently-shaped object where
    // the array fields (vehicles_discussed/commitments_made/next_steps/objections/
    // risk_flags) are undefined. The review step must guard `.length` and not throw
    // "Cannot read properties of undefined (reading 'length')".
    addNote.mockResolvedValue({
      success: true,
      note: { id: 1, raw_note: 'x', created_at: '' },
      // deliberately only a summary + a couple scalars; arrays omitted (undefined)
      structured_note: { visit_summary: 'Rezumat partial', sentiment: 'positive' } as unknown,
    })
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ceva' } })
    fireEvent.click(screen.getByRole('button', { name: /proceseaz/i }))
    // If the crash regressed, this findByText would never resolve (render throws).
    expect(await screen.findByText('Rezumat partial')).toBeInTheDocument()
    // A working finalize control is still present.
    expect(screen.getByRole('button', { name: /salveaz|finaliz/i })).toBeInTheDocument()
  })

  it('null structured_note: shows the saved-without-summary text + a working finalize control that calls onDone', async () => {
    // AI structuring can fail even though the note saved AND the backend
    // already completed the visit (structured_note: null). The user must still
    // have an exit that fires the invalidations + onDone so the Hub list
    // refreshes and the visit shows as finalized.
    addNote.mockResolvedValue({ success: true, note: { id: 1, raw_note: 'x', created_at: '' }, structured_note: null })
    const onDone = vi.fn()
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={onDone} onCancel={() => {}} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'discutie buna' } })
    fireEvent.click(screen.getByRole('button', { name: /proceseaz/i }))

    expect(await screen.findByText(/nu s-a putut genera un rezumat AI/i)).toBeInTheDocument()
    const finalize = screen.getByRole('button', { name: /finalizeaz/i })
    fireEvent.click(finalize)
    // RTL's waitFor wraps polling in act(), so the invalidateQueries + onDone
    // chain triggered from handleSave settles under act() -> no act() warning.
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('falls back to input step and shows an inline error when addNote fails', async () => {
    // Reassign a fresh mock directly on the mocked module (rather than the
    // shared `addNote` wrapper used above) -- matches the convention already
    // used for the reject-path case in HubFieldSalesPanel.test.tsx, and
    // avoids a false-positive "unhandled rejection" flagged by Vitest when a
    // rejecting mock shares a mutation-backed wrapper with prior resolving
    // tests in this suite. afterEach re-wires the wrapper so this doesn't leak.
    ;(fieldSalesApi.addNote as ReturnType<typeof vi.fn>) = vi.fn().mockRejectedValue({ data: { error: 'Nota nu a putut fi procesata' } })
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'discutie buna' } })
    fireEvent.click(screen.getByRole('button', { name: /proceseaz/i }))
    await waitFor(() => expect(screen.getByText('Nota nu a putut fi procesata')).toBeInTheDocument())
    // back on the input step -> textarea is present again
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('calls onCancel when Anuleaza is clicked', () => {
    const onCancel = vi.fn()
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={() => {}} onCancel={onCancel} />)
    fireEvent.click(screen.getByRole('button', { name: /anuleaz/i }))
    expect(onCancel).toHaveBeenCalled()
  })
})
