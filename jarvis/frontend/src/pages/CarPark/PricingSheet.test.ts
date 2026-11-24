import { describe, test, expect } from 'vitest'
import { computePricingModel, composeSheetCostLines, type PricingInputs } from './PricingSheet'

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

// ── composeSheetCostLines — migration invariant ───────────────────────────
// Task 2: the Fișă reads cost_lines JSON only. Once the backfill nulls
// cost_lines and the acquisition extras live in the structured `achizitie`
// cost row, the sheet's landed/floor/suggested price must not move. The
// composer is the seam where the JSON shim and the structured total meet —
// pin the no-double-count invariant here, not in computePricingModel (which
// only sums `eur` and would make a same-input test tautological).
describe('composeSheetCostLines', () => {
  const form = { purchase_price_net: 10000, acquisition_price: 11900, purchase_vat_rate: 19, vat_deductible: true }
  const inpZero: PricingInputs = { target: 0, finRate: 0, targetDays: 0, warrantyPct: 0, anchor: 0, comps: null, anchorDate: '' }

  test('composer sums JSON eur before migration and structured achizitie after, never double-counting', () => {
    const pre = composeSheetCostLines([{ eur: 800 }], [])                                  // JSON only
    const post = composeSheetCostLines([], [{ cost_type: 'achizitie', total_amount: 800 }]) // migrated
    const sum = (ls: { eur: number | null }[]) => ls.reduce((s, l) => s + (l.eur ?? 0), 0)
    expect(sum(pre)).toBe(800)
    expect(sum(post)).toBe(800)
  })

  test('landed cost is unchanged when acquisition extras move from cost_lines JSON to structured achizitie', () => {
    const pre = computePricingModel(form, composeSheetCostLines([{ eur: 800 }], []), inpZero)
    const post = computePricingModel(form, composeSheetCostLines([], [{ cost_type: 'achizitie', total_amount: 800 }]), inpZero)
    expect(post.landedCostEur).toBe(pre.landedCostEur)
  })

  test('ignores non-achizitie breakdown types (they were never in the sheet)', () => {
    const r = composeSheetCostLines([], [{ cost_type: 'repair', total_amount: 500 }])
    expect(r.reduce((s, l) => s + (l.eur ?? 0), 0)).toBe(0)
  })
})
