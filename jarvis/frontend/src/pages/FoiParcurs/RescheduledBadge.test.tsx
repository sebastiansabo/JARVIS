import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import RescheduledBadge from './RescheduledBadge'
import type { FoiContract } from '@/types/foiParcurs'

const base = { id: 1 } as FoiContract

describe('RescheduledBadge', () => {
  it('renders nothing for a session that was never rescheduled', () => {
    const { container } = render(<RescheduledBadge session={base} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders "Replanificat" with a when-tooltip when rescheduled_at is set', () => {
    render(<RescheduledBadge session={{ ...base, rescheduled_at: '2026-10-07T09:00:00' }} />)
    const badge = screen.getByText('Replanificat')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveAttribute('title', expect.stringContaining('Replanificat la'))
  })
})
