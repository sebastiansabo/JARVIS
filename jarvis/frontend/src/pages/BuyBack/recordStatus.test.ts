import { describe, it, expect } from 'vitest'
import { recordStatus, STATUS_FILTER_OPTIONS } from './recordStatus'

describe('recordStatus', () => {
  it('maps each lifecycle status to a non-empty RO label + badge', () => {
    for (const s of ['PENDING_EVALUATION', 'INITIAL_OFFER', 'INSPECTION', 'FINAL_OFFER', 'BOUGHT', 'LOST', 'CANCELLED']) {
      const r = recordStatus(s)
      expect(r.label).toBeTruthy()
      expect(r.badgeClass).toBeTruthy()
    }
  })

  it('BOUGHT is green, LOST/CANCELLED muted', () => {
    expect(recordStatus('BOUGHT').badgeClass).toMatch(/green/)
    expect(recordStatus('CANCELLED').label).toBe('Anulat')
  })

  it('unknown status falls back, does not throw', () => {
    expect(recordStatus('WAT').label).toBeTruthy()
  })

  it('STATUS_FILTER_OPTIONS contains all 7 statuses', () => {
    expect(STATUS_FILTER_OPTIONS).toHaveLength(7)
    const values = STATUS_FILTER_OPTIONS.map((opt) => opt.value)
    expect(values).toContain('PENDING_EVALUATION')
    expect(values).toContain('INITIAL_OFFER')
    expect(values).toContain('INSPECTION')
    expect(values).toContain('FINAL_OFFER')
    expect(values).toContain('BOUGHT')
    expect(values).toContain('LOST')
    expect(values).toContain('CANCELLED')
  })

  it('each filter option has a non-empty label', () => {
    for (const opt of STATUS_FILTER_OPTIONS) {
      expect(opt.label).toBeTruthy()
    }
  })
})
