import { describe, it, expect, vi } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Control the getForm promise so we can drive the loading -> loaded transition
// that previously crashed with "Rendered more hooks than during the previous render".
vi.mock('@/api/evaluation360', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/evaluation360')>()
  return {
    ...actual,
    eval360Api: {
      ...actual.eval360Api,
      getForm: vi.fn(),
      saveDraft: vi.fn().mockResolvedValue({ draft: {} }),
      submit: vi.fn().mockResolvedValue({ ok: true }),
      commentNudge: vi.fn().mockResolvedValue({ ok: true }),
    },
  }
})

import { eval360Api, type EvaluationForm as EvaluationFormData } from '@/api/evaluation360'
import { EvaluationForm } from './index'

const FORM: EvaluationFormData = {
  assignment: {
    id: 1, cycle_id: 5, subject_id: 10, relationship: 'peer', status: 'invited',
    due_at: null, subject_name: 'Ana Pop', cycle_name: 'Q3 2026', review_end: null,
    answered: 0, total: 1, est_minutes: 1,
  },
  questions: [{
    id: 11, competency_id: 2, competency_name: 'Comunicare', type: 'rating',
    text_by_audience: { peer: 'Cât de bine demonstrează: Comunicare?' },
    required: true, sort_order: 0,
  }],
  draft: {},
  is_submitted: false,
}

function renderWithClient(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('EvaluationForm', () => {
  it('mounts through loading → loaded without a hook-order crash', async () => {
    let resolve!: (v: EvaluationFormData) => void
    vi.mocked(eval360Api.getForm).mockReturnValue(
      new Promise<EvaluationFormData>((r) => { resolve = r }),
    )

    renderWithClient(<EvaluationForm assignmentId={1} onBack={() => {}} />)
    // Loading render runs fewer hooks; resolving flips it to the loaded render.
    resolve(FORM)

    // If any hook were declared after an early return, this loaded render would throw.
    expect(await screen.findByText('Ana Pop')).toBeInTheDocument()
    expect(screen.getByText('Comunicare')).toBeInTheDocument()
  })
})
