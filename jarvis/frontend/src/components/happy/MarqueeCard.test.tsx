import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { MarqueeCard } from './MarqueeCard'
import type { HappySurfaceItem } from '@/types/happy'

const ITEM: HappySurfaceItem = {
  id: 1,
  kind: 'event',
  tier: 'normal',
  kicker: 'HR · Eveniment',
  title: 'Zi de curățenie la birou',
  summary: 'Ne vedem sâmbătă la 10:00.',
  body_md: '',
  event_at: null,
  media: null,
  cta: null,
  ack: null,
  dismissible: true,
  snooze_remaining: 0,
  impression_token: 'tok-1',
}

describe('MarqueeCard', () => {
  it('renders the title', () => {
    render(
      <MemoryRouter>
        <MarqueeCard item={ITEM} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Zi de curățenie la birou')).toBeInTheDocument()
  })

  it('renders nothing when there is no item', () => {
    const { container } = render(
      <MemoryRouter>
        <MarqueeCard item={null} />
      </MemoryRouter>,
    )
    expect(container.textContent).toBe('')
  })
})
