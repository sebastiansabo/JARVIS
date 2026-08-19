import { describe, it, expect } from 'vitest'
import { isCompanyClientLike } from './companyClient'

describe('isCompanyClientLike', () => {
  it('is true when client_type is company', () => {
    expect(isCompanyClientLike({ id: 1, client_type: 'company', display_name: 'Anything' } as any)).toBe(true)
  })
  it('is true for a company name even when mis-typed as person (NELAURA case)', () => {
    expect(
      isCompanyClientLike({ id: 1, client_type: 'person', display_name: 'NELAURA COMIMPEX SRL J12/978/1994' } as any),
    ).toBe(true)
  })
  it('recognises SA / PFA / SNC legal forms', () => {
    expect(isCompanyClientLike({ id: 1, client_type: 'person', display_name: 'DACIA SA' } as any)).toBe(true)
    expect(isCompanyClientLike({ id: 1, client_type: 'person', display_name: 'Ionescu PFA' } as any)).toBe(true)
    expect(isCompanyClientLike({ id: 1, client_type: 'person', display_name: 'Ceva SNC' } as any)).toBe(true)
  })
  it('is false for a plain person', () => {
    expect(isCompanyClientLike({ id: 1, client_type: 'person', display_name: 'Ion Popescu' } as any)).toBe(false)
    expect(isCompanyClientLike({ id: 1, client_type: 'person', display_name: 'Maria Vasilescu' } as any)).toBe(false)
  })
  it('is false for null/undefined', () => {
    expect(isCompanyClientLike(null)).toBe(false)
    expect(isCompanyClientLike(undefined)).toBe(false)
  })
})
