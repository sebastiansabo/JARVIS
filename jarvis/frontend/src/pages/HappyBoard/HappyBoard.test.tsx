import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PulseResultsView } from './PulseResultsView'
import { ReachFunnel } from './ReachFunnel'
import type { PulseResults, CampaignFunnel } from '@/api/happyAdmin'

describe('PulseResultsView (backend results contract)', () => {
  // Shape mirrors backend PulseRepository.get_results EXACTLY: `cohorts` is a
  // DICT keyed by cohort_key; each block is either a suppressed marker or a map
  // of question-key -> typed score.
  const results: PulseResults = {
    pulse_id: 7,
    min_group_size: 5,
    participation: { responses: 5, invited: 5, rate: 1 },
    overall: { q1: { type: 'enps', n: 5, nps: 40 } },
    cohorts: {
      'node:12': { q1: { type: 'enps', n: 5, nps: 40 } },
      'node:99': { suppressed: true, reason: 'below_min_group_size', n: 2 },
    },
  }

  it('renders the aggregated overall eNPS score', () => {
    render(<PulseResultsView results={results} />)
    // eNPS surfaces for both the overall roll-up and the shown cohort.
    expect(screen.getAllByText('eNPS 40').length).toBeGreaterThanOrEqual(1)
  })

  it('renders a suppressed cohort with the hidden label and NOT its numbers', () => {
    render(<PulseResultsView results={results} />)
    expect(screen.getByText('Ascuns (sub pragul de anonimat)')).toBeInTheDocument()
    // The suppressed cohort's response count (2) must never be shown.
    expect(screen.queryByText(/2 răsp\./)).not.toBeInTheDocument()
    expect(screen.queryByText(/^2$/)).not.toBeInTheDocument()
  })

  it('renders a freshly-created pulse (empty cohorts dict, no responses) WITHOUT crashing', () => {
    // Regression: a new pulse yields cohorts={} and a suppressed overall. The old
    // view did `cohorts.map(...)` on a dict → "r.map is not a function".
    const fresh: PulseResults = {
      pulse_id: 8,
      min_group_size: 5,
      participation: { responses: 0, invited: 5, rate: null },
      overall: { suppressed: true, reason: 'below_min_group_size', n: 0 },
      cohorts: {},
    }
    render(<PulseResultsView results={fresh} />)
    expect(screen.getByText('Nu există cohorte de afișat.')).toBeInTheDocument()
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
