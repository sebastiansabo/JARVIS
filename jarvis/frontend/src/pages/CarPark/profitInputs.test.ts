import { describe, test, expect } from 'vitest'
import { acquisitionProfitInputs, type ProfitInputsVehicle } from './profitInputs'

const vehicle = (o: Partial<ProfitInputsVehicle>): ProfitInputsVehicle => ({
  purchase_price_net: null,
  acquisition_price: null,
  purchase_vat_rate: null,
  vat_deductible: true,
  cost_lines: null,
  ...o,
})

describe('acquisitionProfitInputs', () => {
  test('NORMAL car: canonical net/gross used directly + one cost line', () => {
    // 48500 net EUR, 57715 gross EUR, 19% VAT, one 1000 EUR cost line.
    const out = acquisitionProfitInputs(vehicle({
      purchase_price_net: 48500,
      acquisition_price: 57715,
      purchase_vat_rate: 19,
      vat_deductible: true,
      cost_lines: JSON.stringify([{ eur: 1000 }]),
    }))
    expect(out.regime).toBe('NORMAL')
    expect(out.vatRate).toBe(19)
    expect(out.netAcqEur).toBe(48500)
    expect(out.grossAcqEur).toBe(57715)
    expect(out.costLinesEur).toBe(1000)
    expect(out.inputVatEur).toBe(9215) // gross − net
    expect(out.landedCostEur).toBe(49500) // net + cost lines (net basis, NOT gross)
    expect(out.purchaseGrossEur).toBe(57715)
  })

  test('MARGIN car (vat_deductible false): net == gross, no input VAT', () => {
    const out = acquisitionProfitInputs(vehicle({
      purchase_price_net: 10000,
      acquisition_price: 10000,
      vat_deductible: false,
      cost_lines: JSON.stringify([{ eur: 500 }]),
    }))
    expect(out.regime).toBe('MARGIN')
    expect(out.vatRate).toBe(21) // MARGIN forces standard rate
    expect(out.netAcqEur).toBe(10000)
    expect(out.grossAcqEur).toBe(10000)
    expect(out.netAcqEur).toBe(out.grossAcqEur)
    expect(out.inputVatEur).toBe(0)
    expect(out.landedCostEur).toBe(10500)
  })

  test('legacy NORMAL row missing acquisition_price → gross derived from net', () => {
    const out = acquisitionProfitInputs(vehicle({
      purchase_price_net: 10000,
      acquisition_price: null,
      purchase_vat_rate: 19,
      vat_deductible: true,
    }))
    expect(out.regime).toBe('NORMAL')
    expect(out.netAcqEur).toBe(10000)
    expect(out.grossAcqEur).toBe(11900) // 10000 * 1.19
    expect(out.inputVatEur).toBe(1900)
  })

  test('legacy MARGIN row missing acquisition_price → gross == net (no VAT uplift)', () => {
    const out = acquisitionProfitInputs(vehicle({
      purchase_price_net: 10000,
      acquisition_price: null,
      vat_deductible: false,
    }))
    expect(out.regime).toBe('MARGIN')
    expect(out.netAcqEur).toBe(10000)
    expect(out.grossAcqEur).toBe(10000) // NOT 10000 * 1.21 — margin cars carry no purchase-side VAT
    expect(out.grossAcqEur).toBe(out.netAcqEur)
    expect(out.inputVatEur).toBe(0)
  })

  test('missing vat rate falls back to 21 in NORMAL', () => {
    const out = acquisitionProfitInputs(vehicle({
      purchase_price_net: 10000,
      acquisition_price: 12100,
      purchase_vat_rate: null,
      vat_deductible: true,
    }))
    expect(out.vatRate).toBe(21)
    expect(out.inputVatEur).toBe(2100)
  })

  test('NORMAL row missing purchase_price_net → net reconstructed from gross', () => {
    // ppn missing, only GROSS acquisition_price present → divide out the VAT.
    const out = acquisitionProfitInputs(vehicle({
      purchase_price_net: null,
      acquisition_price: 11900,
      purchase_vat_rate: 19,
      vat_deductible: true,
    }))
    expect(out.regime).toBe('NORMAL')
    expect(out.grossAcqEur).toBe(11900)
    expect(out.netAcqEur).toBeCloseTo(11900 / 1.19, 6) // 10000
    expect(out.inputVatEur).toBeCloseTo(11900 - 11900 / 1.19, 6)
    expect(out.landedCostEur).toBeCloseTo(11900 / 1.19, 6)
  })

  test('MARGIN row missing purchase_price_net → net == gross (no VAT division)', () => {
    const out = acquisitionProfitInputs(vehicle({
      purchase_price_net: null,
      acquisition_price: 10000,
      vat_deductible: false,
    }))
    expect(out.regime).toBe('MARGIN')
    expect(out.grossAcqEur).toBe(10000)
    expect(out.netAcqEur).toBe(10000) // margin cars carry no purchase-side VAT
    expect(out.inputVatEur).toBe(0)
  })

  test('legacy RON NORMAL row: net EUR = NET LEI / kurs, gross uplifts by VAT', () => {
    // acquisition_price = NET LEI (50000), kurs 5 → net EUR 10000; gross = 10000*1.20.
    // purchase_price_net here is GROSS EUR and must be IGNORED on the kurs path.
    const out = acquisitionProfitInputs(vehicle({
      acquisition_currency: 'RON',
      acquisition_price: 50000,
      acquisition_exchange_rate: 5,
      purchase_price_net: 99999,
      purchase_vat_rate: 20,
      vat_deductible: true,
    }))
    expect(out.regime).toBe('NORMAL')
    expect(out.netAcqEur).toBe(10000)
    expect(out.grossAcqEur).toBe(12000)
    expect(out.inputVatEur).toBe(2000)
    expect(out.landedCostEur).toBe(10000)
    expect(out.purchaseGrossEur).toBe(12000)
  })

  test('legacy RON row without kurs → falls back to gross-EUR purchase_price_net', () => {
    const out = acquisitionProfitInputs(vehicle({
      acquisition_currency: 'RON',
      acquisition_price: 50000,       // NET LEI, unusable without a kurs
      acquisition_exchange_rate: 0,
      purchase_price_net: 11900,      // GROSS EUR fallback
      purchase_vat_rate: 19,
      vat_deductible: true,
    }))
    expect(out.netAcqEur).toBeCloseTo(10000, 6) // 11900 / 1.19
    expect(out.grossAcqEur).toBeCloseTo(11900, 6)
    expect(out.inputVatEur).toBeCloseTo(1900, 6)
  })

  test('legacy RON MARGIN row: net == gross (no purchase-side VAT)', () => {
    const out = acquisitionProfitInputs(vehicle({
      acquisition_currency: 'RON',
      acquisition_price: 50000,
      acquisition_exchange_rate: 5,
      purchase_vat_rate: 20,
      vat_deductible: false,
    }))
    expect(out.regime).toBe('MARGIN')
    expect(out.netAcqEur).toBe(10000)
    expect(out.grossAcqEur).toBe(10000)
    expect(out.inputVatEur).toBe(0)
    expect(out.landedCostEur).toBe(10000)
  })

  test('unparseable cost_lines → 0 cost, no throw', () => {
    const out = acquisitionProfitInputs(vehicle({
      purchase_price_net: 5000,
      acquisition_price: 5950,
      purchase_vat_rate: 19,
      cost_lines: 'not json',
    }))
    expect(out.costLinesEur).toBe(0)
    expect(out.landedCostEur).toBe(5000)
  })
})
