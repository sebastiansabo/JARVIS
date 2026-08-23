import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PulseResultsView } from './PulseResultsView'
import { ReachFunnel } from './ReachFunnel'
import type { PulseResults, CampaignFunnel } from '@/api/happyAdmin'

describe('PulseResultsView (anonymity threshold)', () => {
  const results: PulseResults = {
    participation: { responses: 42, invited: 60, rate: 0.7 },
    overall: { wellbeing: 4.2 },
    cohorts: [
      { key: 'vanzari', label: 'Vânzări', n: 18, enps: 30 },
      { key: 'it', label: 'IT', suppressed: true, reason: 'below_min_group_size', n: 2 },
    ],
  }

  it('renders a normal cohort with its numbers', () => {
    render(<PulseResultsView results={results} />)
    expect(screen.getByText('Vânzări')).toBeInTheDocument()
    expect(screen.getByText('18 răsp.')).toBeInTheDocument()
  })

  it('renders a suppressed cohort with the hidden label and NOT its numbers', () => {
    render(<PulseResultsView results={results} />)
    expect(screen.getByText('Ascuns (sub pragul de anonimat)')).toBeInTheDocument()
    // The suppressed cohort's response count (2) must never be shown.
    expect(screen.queryByText('2 răsp.')).not.toBeInTheDocument()
  })
})

describe('ReachFunnel', () => {
  it('renders each step with its percentage of the targeted base', () => {
    const funnel: CampaignFunnel = {
      targeted: 100,
      reached: 80,
      read_8s: 50,
      clicked: 20,
      acknowledged: 10,
      dismissed: 5,
    }
    render(<ReachFunnel funnel={funnel} />)
    expect(screen.getByText('Vizați')).toBeInTheDocument()
    // reached = 80 / 100 = 80%
    expect(screen.getByText(/\(80%\)/)).toBeInTheDocument()
    // acknowledged = 10 / 100 = 10%
    expect(screen.getByText(/\(10%\)/)).toBeInTheDocument()
  })
})
