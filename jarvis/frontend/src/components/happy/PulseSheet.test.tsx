import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PulseSheet } from './PulseSheet'
import type { HappyPulse, HappyPulseQuestion } from '@/types/happy'

const PULSE: HappyPulse = {
  id: 7,
  slug: 'pulse-2026-w34',
  title: 'Pulse săptămânal',
  cadence: 'weekly',
  closes_at: null,
}

const QUESTIONS: HappyPulseQuestion[] = [
  { position: 1, prompt_ro: 'Cât de mulțumit ești?', prompt_en: null, qtype: 'likert5', driver: 'wellbeing' },
  { position: 2, prompt_ro: 'Cât de probabil ne recomanzi?', prompt_en: null, qtype: 'enps', driver: 'ambassadorship' },
]

const NOTICE =
  'Răspunsurile sunt anonime. Rezultatele se raportează doar pe grupuri de minim 5 persoane.'

function renderSheet() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PulseSheet
        pulse={PULSE}
        questions={QUESTIONS}
        anonymityNotice={NOTICE}
        open
        onOpenChange={vi.fn()}
      />
    </QueryClientProvider>,
  )
}

describe('PulseSheet', () => {
  beforeAll(() => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    })) as unknown as typeof window.matchMedia
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
    window.HTMLElement.prototype.releasePointerCapture = vi.fn()
  })

  it('renders the anonymity notice ABOVE the first question', () => {
    renderSheet()
    const notice = screen.getByText(NOTICE)
    const firstQuestion = screen.getByText('1. Cât de mulțumit ești?')
    expect(notice).toBeInTheDocument()
    expect(firstQuestion).toBeInTheDocument()
    // DOCUMENT_POSITION_FOLLOWING (4) means firstQuestion comes after the notice.
    expect(notice.compareDocumentPosition(firstQuestion) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('renders every question prompt', () => {
    renderSheet()
    expect(screen.getByText('1. Cât de mulțumit ești?')).toBeInTheDocument()
    expect(screen.getByText('2. Cât de probabil ne recomanzi?')).toBeInTheDocument()
  })
})
