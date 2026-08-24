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

  it('headlines the aggregated overall eNPS score', () => {
    render(<PulseResultsView results={results} />)
    // Overall is the big headline number + caption.
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText(/eNPS · 5 răsp\./)).toBeInTheDocument()
  })

  it('shows revealed cohorts and folds suppressed ones into a single count', () => {
    render(<PulseResultsView results={results} />)
    // Revealed cohort renders its eNPS badge.
    expect(screen.getByText('eNPS 40')).toBeInTheDocument()
    // Suppressed cohort is collapsed; its response count (2) must never be shown.
    expect(screen.getByText('1 cohortă ascunsă (sub prag)')).toBeInTheDocument()
    expect(screen.queryByText(/2 răsp\./)).not.toBeInTheDocument()
  })

  it('orders revealed cohorts by response count, most first', () => {
    const many: PulseResults = {
      participation: { responses: 40, invited: 50, rate: 0.8 },
      overall: { q1: { type: 'enps', n: 40, nps: 25 } },
      cohorts: {
        'node:1': { q1: { type: 'enps', n: 8, nps: 10 } }, // fewer
        'node:2': { q1: { type: 'enps', n: 22, nps: 60 } }, // most
      },
    }
    render(<PulseResultsView results={many} />)
    const big = screen.getByText('Departament 2')
    const small = screen.getByText('Departament 1')
    // "most responses first" → node:2 (22) precedes node:1 (8) in the DOM.
    expect(big.compareDocumentPosition(small) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('hides the overall roll-up when below the anonymity threshold', () => {
    // Mirrors the real 2-of-5 state: overall + both cohorts under min_group_size.
    const below: PulseResults = {
      pulse_id: 9,
      min_group_size: 5,
      participation: { responses: 2, invited: 5, rate: 0.4 },
      overall: { suppressed: true, reason: 'below_min_group_size', n: 2 },
      cohorts: {
        'company:11': { suppressed: true, reason: 'below_min_group_size', n: 1 },
        'company:16': { suppressed: true, reason: 'below_min_group_size', n: 1 },
      },
    }
    render(<PulseResultsView results={below} />)
    expect(screen.getByText('Ascuns (sub pragul de anonimat)')).toBeInTheDocument()
    expect(screen.getByText('2 cohorte ascunse (sub prag)')).toBeInTheDocument()
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
