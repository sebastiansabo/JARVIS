import { describe, it, expect } from 'vitest'
import { vehicleTenant, matchesTenant } from './tenant'

describe('vehicleTenant', () => {
  it('uses brand (the tenant label), ignoring the descriptive mark casing', () => {
    expect(vehicleTenant({ brand: 'Mazda', mark: 'MAZDA' })).toBe('Mazda')
  })

  it('falls back to mark only when brand is empty', () => {
    expect(vehicleTenant({ brand: '', mark: 'MG' })).toBe('MG')
  })
})

describe('matchesTenant', () => {
  // Tenant membership is the catalog `brand`, so both casings of the
  // descriptive mark belong to the one "Mazda" tenant.
  it('groups a car by brand even when its mark casing differs', () => {
    expect(matchesTenant({ brand: 'Mazda', mark: 'Mazda' }, 'Mazda')).toBe(true)
    expect(matchesTenant({ brand: 'Mazda', mark: 'MAZDA' }, 'Mazda')).toBe(true)
  })

  it('excludes a car from a different tenant', () => {
    expect(matchesTenant({ brand: 'MG Motor', mark: 'MG' }, 'Mazda')).toBe(false)
  })

  it('matches the MG tenant by its brand label, not the "MG" mark', () => {
    expect(matchesTenant({ brand: 'MG Motor', mark: 'MG' }, 'MG Motor')).toBe(true)
  })

  it('treats an empty tenant selection as "all tenants"', () => {
    expect(matchesTenant({ brand: 'Mazda', mark: 'MAZDA' }, '')).toBe(true)
  })

  it('is case-insensitive on the tenant label', () => {
    expect(matchesTenant({ brand: 'Mazda' }, 'mazda')).toBe(true)
  })
})
