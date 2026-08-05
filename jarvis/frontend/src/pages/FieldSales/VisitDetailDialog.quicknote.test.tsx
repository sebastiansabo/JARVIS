import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'

const getVisit = vi.fn()
const addQuickNote = vi.fn()
vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: {
  getVisit: (...a: unknown[]) => getVisit(...a),
  getVisitTasks: vi.fn().mockResolvedValue({ success: true, tasks: [] }),
  updateVisit: vi.fn(),
  addQuickNote: (...a: unknown[]) => addQuickNote(...a),
} }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
import { VisitDetailDialog } from './VisitDetailDialog'

const visitResp = (status: string) => ({ success: true, visit: {
  id: 9, kam_id: 3, client_id: 760, planned_date: '2026-08-04', visit_type: 'general', status,
  client_name: 'ACME SRL', kam_name: 'George Pop', notes: [],
} })

function wrap(ui: React.ReactNode, qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('VisitDetailDialog quick note', () => {
  beforeEach(() => {
    getVisit.mockReset(); addQuickNote.mockReset()
    addQuickNote.mockResolvedValue({ success: true, note: { id: 1, raw_note: 'x', created_at: '' } })
  })

  afterEach(() => {
    useAuthStore.setState({ user: null })
  })

  it('shows the composer when the visit is in_progress and the current user owns it', async () => {
    useAuthStore.setState({ user: { id: 3 } as never })
    getVisit.mockResolvedValue(visitResp('in_progress'))
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />)
    expect(await screen.findByPlaceholderText(/noteaz/i)).toBeInTheDocument()
  })

  it('hides the composer for an in_progress visit owned by another KAM (manager viewing)', async () => {
    useAuthStore.setState({ user: { id: 99 } as never })
    getVisit.mockResolvedValue(visitResp('in_progress'))
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />)
    await screen.findByRole('button', { name: /editeaza/i })
    expect(screen.queryByPlaceholderText(/noteaz/i)).not.toBeInTheDocument()
  })

  it('hides the composer for a planned visit', async () => {
    useAuthStore.setState({ user: { id: 3 } as never })
    getVisit.mockResolvedValue(visitResp('planned'))
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />)
    // "Editeaza" renders once the visit has loaded, independent of status.
    await screen.findByRole('button', { name: /editeaza/i })
    expect(screen.queryByPlaceholderText(/noteaz/i)).not.toBeInTheDocument()
  })

  it('hides the composer for a completed visit', async () => {
    useAuthStore.setState({ user: { id: 3 } as never })
    getVisit.mockResolvedValue(visitResp('completed'))
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />)
    await screen.findByRole('button', { name: /editeaza/i })
    expect(screen.queryByPlaceholderText(/noteaz/i)).not.toBeInTheDocument()
  })

  it('disables add until text is entered, then calls addQuickNote(9, text), clears, and invalidates related queries', async () => {
    useAuthStore.setState({ user: { id: 3 } as never })
    getVisit.mockResolvedValue(visitResp('in_progress'))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} />, qc)
    const box = await screen.findByPlaceholderText(/noteaz/i) as HTMLTextAreaElement
    const btn = screen.getByRole('button', { name: /adaug[aă] not[aă]/i })
    expect(btn).toBeDisabled()
    fireEvent.change(box, { target: { value: 'client vrea X5' } })
    expect(btn).not.toBeDisabled()
    fireEvent.click(btn)
    await waitFor(() => expect(addQuickNote).toHaveBeenCalledWith(9, 'client vrea X5'))
    await waitFor(() => expect(box.value).toBe(''))
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['fs-visit-detail', 9] }))
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['field-sales-visits'] }))
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['field-sales-mine'] }))
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['field-sales-cal'] }))
  })
})
