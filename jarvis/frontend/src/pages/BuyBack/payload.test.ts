import { describe, it, expect } from 'vitest'
import { buildCreatePayload } from './BuyBackForm'

describe('buildCreatePayload', () => {
  it('coerces numbers, omits empty optionals, keeps required', () => {
    const p = buildCreatePayload({ vin: 'WBA12345678901234', brand: 'BMW', model: '320d',
      mileage_km: '85000', general_condition: 4, client_asking_price_eur: '9500',
      manufacture_date: '2019-06-01', variant: '', has_damage: true, acquisition_type: 'buyback' } as any)
    expect(p.vin).toBe('WBA12345678901234'); expect(p.brand).toBe('BMW')
    expect(p.mileage_km).toBe(85000)                 // number, not "85000"
    expect(p.client_asking_price_eur).toBe(9500)
    expect('variant' in p).toBe(false)               // empty optional omitted
    expect(p.has_damage).toBe(true)
  })
  it('never emits a non-whitelisted key', () => {
    const p = buildCreatePayload({ vin: 'X', brand: 'A', model: 'B', hacker_field: 1 } as any)
    expect('hacker_field' in p).toBe(false)
  })
})
