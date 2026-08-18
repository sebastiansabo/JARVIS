import { describe, it, expect } from 'vitest'
import { buildStartSlots, fmtDurationLabel, buildDurationOptions, computeReturn } from './leaveSlots'

describe('buildStartSlots', () => {
  it('30-min slots from start to end-30', () => {
    expect(buildStartSlots('09:00', '11:00')).toEqual(['09:00', '09:30', '10:00', '10:30'])
  })
})

describe('fmtDurationLabel', () => {
  it('formats half/whole/mixed', () => {
    expect(fmtDurationLabel(0.5)).toBe('30 min')
    expect(fmtDurationLabel(1)).toBe('1 h')
    expect(fmtDurationLabel(1.5)).toBe('1:30 h')
  })
})

describe('buildDurationOptions', () => {
  it('caps by day cap and remaining window', () => {
    const opts = buildDurationOptions('09:00', '18:00', 2)
    expect(opts.map(o => o.value)).toEqual([0.5, 1, 1.5, 2])
  })
  it('shrinks near end of window', () => {
    const opts = buildDurationOptions('17:00', '18:00', 7)
    expect(opts.map(o => o.value)).toEqual([0.5, 1])
  })
})

describe('computeReturn', () => {
  it('adds duration', () => {
    expect(computeReturn('09:00', 1.5)).toBe('10:30')
  })
})
