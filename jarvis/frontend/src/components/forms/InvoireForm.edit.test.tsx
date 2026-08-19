import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi, it, expect } from 'vitest'
// vi.mock factories are hoisted above top-level `const` declarations, so the
// mocked fns must come from vi.hoisted() (matches the pattern used elsewhere
// in this codebase, e.g. CreateClientPanel.test.tsx) rather than a bare
// top-level const — otherwise vitest throws "Cannot access before initialization".
const { update } = vi.hoisted(() => ({
  update: vi.fn(() => Promise.resolve({ success: true, data: { submission_id: 42 } })),
}))
vi.mock('@/api/connecteam', () => ({ connecteamApi: {
  updateLeavePermit: update, submitLeavePermit: vi.fn(),
  getApprovers: vi.fn(() => Promise.resolve({ data: [] })),
  getLeaveSchedule: vi.fn(() => Promise.resolve({ success: true, data: { schedule_start: '07:00', schedule_end: '18:00', day_cap_hours: 7, reasons: ['Personal'] } })) } }))
// profileApi.getSignature() resolves to { signature } directly (api.get<T>
// unwraps the response body — see src/api/client.ts), not a { data } wrapper.
// The component reads `sigRes?.signature`, so the mock must match that shape
// or the preload effect never fires and SignatureCanvas mounts instead (which
// crashes under jsdom — no canvas getContext support).
vi.mock('@/api/profile', () => ({ profileApi: { getSignature: vi.fn(() => Promise.resolve({ signature: 'sig' })), saveSignature: vi.fn() } }))
vi.mock('@/api/digest', () => ({ digestApi: { searchUsers: vi.fn(() => Promise.resolve({ data: [] })) } }))
// SignatureCanvas mounts a real <canvas> + signature_pad on the first render
// (before the preloaded-signature query resolves). jsdom has no canvas
// backend (getContext returns null), which crashes signature_pad's
// constructor. This is pre-existing / unrelated to edit mode — stub it out
// so the test can exercise the submit flow without a real canvas backend.
vi.mock('@/components/shared/SignatureCanvas', () => ({ default: () => null }))
import { InvoireForm } from './InvoireForm'

it('edit mode PATCHes instead of POSTing', async () => {
  const qc = new QueryClient()
  render(<QueryClientProvider client={qc}><InvoireForm onClose={() => {}} onSubmitted={() => {}}
    submissionId={42} initial={{ f_bi_leave_date: '2026-08-25', f_bi_start_time: '09:00',
      f_bi_duration_hours: '1.5', f_bi_reason: 'Personal', f_bi_second_approver: '', f_bi_notes: '' }} /></QueryClientProvider>)
  // The submit button is present from the first render, but the signature
  // gate (`invalid.signature`) only clears once the preloaded profile
  // signature query resolves and the img preview swaps in — wait for that
  // first, or the click races the query and gets silently no-opped by the
  // client-side validation gate.
  await screen.findByAltText('semnătură')
  fireEvent.click(await screen.findByRole('button', { name: /Trimite|Salvează/ }))
  // The PATCH must carry the preloaded signature (backend modify 400s without a
  // non-empty signature_image) AND the pre-satisfied consent flag — these are
  // the critical invariants of edit mode, so assert them explicitly, not just
  // the prefilled duration.
  await waitFor(() => expect(update).toHaveBeenCalledWith(42, expect.objectContaining({
    f_bi_duration_hours: '1.5',
    signature_image: 'sig',
    f_bi_terms_accepted: true,
  })))
})
