import { describe, test, expect } from 'vitest'
import { computePricingModel, type PricingInputs } from './PricingSheet'

// Minimal engine inputs — only netEur/grossEur derivation is under test here;
// the tiering/anchor math is covered by pricingEngine.test.ts.
const inp: PricingInputs = {
  target: 600,
  finRate: 0.05,
  targetDays: 45,
  warrantyPct: 1.5,
  anchor: 0,
  comps: null,
  anchorDate: '',
}

describe('computePricingModel — acquisition currency derivation', () => {
  test('canonical EUR car: purchase_price_net = NET EUR, acquisition_price = GROSS EUR', () => {
    const form = {
      acquisition_currency: 'EUR',
      purchase_price_net: 48500,
      acquisition_price: 57715,
      purchase_vat_rate: 19,
      vat_deductible: true,
    }
    const m = computePricingModel(form, [], inp)
    expect(m.regime).toBe('NORMAL')
    expect(m.netEur).toBe(48500)
    expect(m.grossEur).toBe(57715)
    expect(m.costBasisEur).toBe(48500) // NORMAL uses net
  })

  test('canonical MARGIN car: gross falls back to net (no VAT uplift) when acquisition_price is missing', () => {
    const form = {
      acquisition_currency: 'EUR',
      purchase_price_net: 10000,
      acquisition_price: null,
      vat_deductible: false,
    }
    const m = computePricingModel(form, [], inp)
    expect(m.regime).toBe('MARGIN')
    expect(m.netEur).toBe(10000)
    expect(m.grossEur).toBe(10000)
    expect(m.costBasisEur).toBe(10000) // MARGIN uses gross, but gross == net here
  })

  test('legacy RON car: acquisition_price = NET LEI, converted via kurs', () => {
    // 40000 net LEI, 19% VAT, kurs 5 → net EUR 8000, gross EUR 9520 (matches acquisitionCanonical vectors)
    const form = {
      acquisition_currency: 'RON',
      acquisition_price: 40000,
      acquisition_exchange_rate: 5,
      purchase_vat_rate: 19,
      vat_deductible: true,
    }
    const m = computePricingModel(form, [], inp)
    expect(m.regime).toBe('NORMAL')
    expect(m.netEur).toBe(8000)
    expect(m.grossEur).toBe(9520)
  })

  test('legacy RON car with no kurs falls back to purchase_price_net as gross EUR', () => {
    const form = {
      acquisition_currency: 'RON',
      acquisition_price: 40000,
      acquisition_exchange_rate: 0,
      purchase_price_net: 9000,
      purchase_vat_rate: 19,
      vat_deductible: true,
    }
    const m = computePricingModel(form, [], inp)
    expect(m.grossEur).toBe(9000)
    expect(m.netEur).toBeCloseTo(9000 / 1.19, 6)
  })
})
