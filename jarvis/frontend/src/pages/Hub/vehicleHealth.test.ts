import { describe, it, expect } from 'vitest'
import { vehicleHealth } from './vehicleHealth'

const TODAY = new Date('2026-08-18T00:00:00')
const complete = {
  registration_number: 'CJ 12 ABC', vin: 'WVW1', brand: 'Audi', color: 'Negru',
  odometer_km: 1000, mileage_floor: 1000, norma_combustibil: 6.5, norma_energie: null,
  category: 'AUTOTURISM M1', insurance_valid_until: '2027-01-01',
  itp_valid_until: '2027-01-01', vignette_valid_until: '2027-01-01',
}

describe('vehicleHealth', () => {
  it('reports ok for a complete car', () => {
    const h = vehicleHealth(complete as any, TODAY)
    expect(h.gravity).toBe('ok')
    expect(h.tags).toEqual([])
  })
  it('flags missing registration as critical', () => {
    const h = vehicleHealth({ ...complete, registration_number: '' } as any, TODAY)
    expect(h.gravity).toBe('critical')
    expect(h.tags.map(t => t.label)).toContain('Fără NR')
  })
  it('flags expired RCA as critical', () => {
    const h = vehicleHealth({ ...complete, insurance_valid_until: '2026-08-01' } as any, TODAY)
    expect(h.gravity).toBe('critical')
    expect(h.tags.map(t => t.label)).toContain('RCA expirat')
  })
  it('flags ITP within 30 days as warning with day count', () => {
    const h = vehicleHealth({ ...complete, itp_valid_until: '2026-09-01' } as any, TODAY)
    expect(h.gravity).toBe('warning')
    expect(h.tags.map(t => t.label)).toContain('ITP expiră 14z')
  })
  it('does not flag a doc expiring in 31 days', () => {
    const h = vehicleHealth({ ...complete, itp_valid_until: '2026-09-18' } as any, TODAY)
    expect(h.gravity).toBe('ok')
  })
  it('flags missing odometer as warning', () => {
    const h = vehicleHealth({ ...complete, odometer_km: null, mileage_floor: null } as any, TODAY)
    expect(h.tags.map(t => t.label)).toContain('Fără km')
  })
})
