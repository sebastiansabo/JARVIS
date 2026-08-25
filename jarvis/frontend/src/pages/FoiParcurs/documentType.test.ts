import { describe, it, expect } from 'vitest'
import { DOC_TYPE_LABELS, contextFromSearch } from './documentType'

describe('documentType helpers', () => {
  it('labels use Romanian user-facing names', () => {
    expect(DOC_TYPE_LABELS.sales).toBe('Vânzări')
    expect(DOC_TYPE_LABELS.service).toBe('Mașini de curtoazie')
  })
  it('reads the ?context= key verbatim (types are now user-defined)', () => {
    expect(contextFromSearch('?context=service')).toBe('service')
    expect(contextFromSearch('?context=comodat')).toBe('comodat')
  })
  it('defaults to sales when there is no context param', () => {
    expect(contextFromSearch('')).toBe('sales')
  })
})
