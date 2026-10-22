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
  it('coerces market_price_eur (Preț Piață) to a number, omits it when blank', () => {
    const p = buildCreatePayload({ vin: 'X', brand: 'A', model: 'B', market_price_eur: '21500' } as any)
    expect(p.market_price_eur).toBe(21500)
    const blank = buildCreatePayload({ vin: 'X', brand: 'A', model: 'B', market_price_eur: '' } as any)
    expect('market_price_eur' in blank).toBe(false)
  })
  it('emits seller legal-identity fields when present, omits them when blank', () => {
    const p = buildCreatePayload({ vin: 'X', brand: 'A', model: 'B',
      seller_cnp: '1234567890123', seller_ci_serie: 'CJ', seller_address: 'Str. 1',
      seller_reg_no: '', seller_iban: '  ' } as any)
    expect(p.seller_cnp).toBe('1234567890123')
    expect(p.seller_ci_serie).toBe('CJ')
    expect(p.seller_address).toBe('Str. 1')
    expect('seller_reg_no' in p).toBe(false)
    expect('seller_iban' in p).toBe(false)
  })
  it('enforces the no-doubling invariant: a company sends the firm and clears seller_name', () => {
    // Even with a stale person name in seller_name (e.g. a legacy record),
    // a company payload sends the firm in seller_company_name and clears
    // seller_name so the two columns are never both populated.
    const p = buildCreatePayload({ vin: 'X', brand: 'A', model: 'B',
      client_type: 'company', seller_name: 'Ion Pop', seller_company_name: 'Auto Exemplu SRL' } as any)
    expect(p.seller_company_name).toBe('Auto Exemplu SRL')
    expect(p.seller_name).toBe('')
  })
  it('enforces the no-doubling invariant: a person sends the name and clears seller_company_name', () => {
    const p = buildCreatePayload({ vin: 'X', brand: 'A', model: 'B',
      client_type: 'person', seller_name: 'Ion Pop', seller_company_name: 'leftover' } as any)
    expect(p.seller_name).toBe('Ion Pop')
    expect(p.seller_company_name).toBe('')
  })
  it('never emits a non-whitelisted key', () => {
    const p = buildCreatePayload({ vin: 'X', brand: 'A', model: 'B', hacker_field: 1 } as any)
    expect('hacker_field' in p).toBe(false)
  })
})
