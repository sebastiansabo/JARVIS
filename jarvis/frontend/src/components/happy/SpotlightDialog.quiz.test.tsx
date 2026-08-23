import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Mock the Happy client so the quiz flow runs without a network.
vi.mock('@/api/happy', () => ({
  happyApi: {
    getQuiz: vi.fn(),
    ackQuiz: vi.fn(),
  },
}))

import { happyApi } from '@/api/happy'
import { SpotlightDialog } from './SpotlightDialog'
import type { HappySurfaceItem } from '@/types/happy'

const QUIZ_ITEM: HappySurfaceItem = {
  id: 42,
  kind: 'policy',
  tier: 'important',
  kicker: 'HR · Politică',
  title: 'Politica de securitate',
  summary: '',
  body_md: '',
  event_at: null,
  media: null,
  cta: null,
  ack: { mode: 'quiz', deadline_at: null, state: 'pending', questions: 1 },
  dismissible: true,
  snooze_remaining: 0,
  impression_token: 'tok-42',
}

function renderDialog() {
  return render(
    <MemoryRouter>
      <SpotlightDialog
        item={QUIZ_ITEM}
        open
        onOpenChange={vi.fn()}
        onCta={vi.fn()}
        onAck={vi.fn()}
        onAcknowledged={vi.fn()}
        onSnooze={vi.fn()}
      />
    </MemoryRouter>,
  )
}

describe('SpotlightDialog quiz mode', () => {
  // Radix Dialog/RadioGroup + useIsMobile need a few DOM APIs jsdom lacks.
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

  beforeEach(() => {
    vi.mocked(happyApi.getQuiz).mockResolvedValue({
      questions: [
        { id: 1, position: 1, prompt: 'Care este regula?', options: ['Răspuns greșit', 'Răspuns corect'] },
      ],
    })
    vi.mocked(happyApi.ackQuiz).mockReset()
  })

  it('renders the fetched quiz questions and options', async () => {
    renderDialog()
    expect(await screen.findByText('1. Care este regula?')).toBeInTheDocument()
    expect(screen.getByText('Răspuns greșit')).toBeInTheDocument()
    expect(screen.getByText('Răspuns corect')).toBeInTheDocument()
  })

  it('reveals the correct option after a wrong answer', async () => {
    vi.mocked(happyApi.ackQuiz).mockResolvedValue({
      acknowledged: false,
      quiz: { all_correct: false, results: [{ position: 1, correct: false, correct_index: 1 }] },
    })

    renderDialog()
    await screen.findByText('1. Care este regula?')

    // Pick the wrong option (index 0), then submit.
    const radios = screen.getAllByRole('radio')
    fireEvent.click(radios[0])
    fireEvent.click(screen.getByRole('button', { name: 'Confirmă' }))

    // The reveal hint appears and the correct option is flagged — no score shown.
    expect(await screen.findByText('Alege răspunsul corect pentru a continua.')).toBeInTheDocument()
    expect(happyApi.ackQuiz).toHaveBeenCalledWith(42, 'tok-42', { 1: 0 })
  })
})
