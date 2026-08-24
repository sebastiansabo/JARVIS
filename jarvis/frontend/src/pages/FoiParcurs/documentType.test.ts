import { describe, it, expect } from 'vitest'
import { DOC_TYPE_LABELS, contextFromSearch } from './documentType'

describe('documentType helpers', () => {
  it('labels use Romanian user-facing names', () => {
    expect(DOC_TYPE_LABELS.sales).toBe('Vânzări')
    expect(DOC_TYPE_LABELS.service).toBe('Mașini de curtoazie')
  })
  it('reads ?context=service from the query string', () => {
    expect(contextFromSearch('?context=service')).toBe('service')
  })
  it('defaults to sales for anything else', () => {
    expect(contextFromSearch('')).toBe('sales')
    expect(contextFromSearch('?context=bogus')).toBe('sales')
  })
})
