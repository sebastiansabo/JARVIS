import { describe, it, expect } from 'vitest'
import { resolveScop } from './scop'

const s = (o: Record<string, unknown>) => o as never

describe('resolveScop', () => {
  it('override wins over everything', () => {
    expect(resolveScop(s({ is_internal: true, itinerary: 'Service' }), 'VW Golf', 'Reparație DEKRA')).toBe('Reparație DEKRA')
  })
  it('event → Eveniment: {name}', () => {
    expect(resolveScop(s({ source: 'gap-event', itinerary: 'Salon Auto' }), 'VW Golf', undefined)).toBe('Eveniment: Salon Auto')
  })
  it('internal → Comentariu verbatim', () => {
    expect(resolveScop(s({ is_internal: true, itinerary: 'Service Brașov' }), 'VW Golf', undefined)).toBe('Service Brașov')
  })
  it('internal without comment → fallback', () => {
    expect(resolveScop(s({ is_internal: true, itinerary: '' }), 'VW Golf', undefined)).toBe('Deplasare în interes de serviciu')
  })
  it('client → Test Drive {model}', () => {
    expect(resolveScop(s({ is_internal: false, source: 'td_form' }), 'VW Golf', undefined)).toBe('Test Drive VW Golf')
  })
})
