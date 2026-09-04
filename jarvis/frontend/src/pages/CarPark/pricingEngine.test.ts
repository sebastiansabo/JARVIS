import { describe, it, expect } from 'vitest'
import {
  type EngineParams,
  vatDue,
  netRevenue,
  profitNet,
  marginNet,
  markup,
  priceForProfit,
  breakevenPrice,
} from './pricingEngine'

// ── Golden vectors (spec §4.5), exact to ±0.01 ─────────────────────────────

describe('Vector A — MARGIN regime', () => {
  const A: EngineParams = {
    regime: 'MARGIN',
    vatRate: 21,
    landedCostEur: 15943.35,
    purchaseGrossEur: 14000,
    inputVatEur: 0,
  }
  it('vat_due(17890) = 675.12', () => expect(vatDue(17890, A)).toBeCloseTo(675.12, 2))
  it('net_revenue(17890) = 17214.88', () => expect(netRevenue(17890, A)).toBeCloseTo(17214.88, 2))
  it('profit_net(17890) = 1271.53', () => expect(profitNet(17890, A)).toBeCloseTo(1271.53, 2))
  it('margin_net(17890) = 7.39%', () => expect(marginNet(17890, A) * 100).toBeCloseTo(7.39, 2))
  it('markup(17890) = 7.98%', () => expect(markup(17890, A) * 100).toBeCloseTo(7.98, 2))
  it('breakeven = 16351.45', () => expect(breakevenPrice(A)).toBeCloseTo(16351.45, 2))
  it('critical (T=600) = 17077.45', () => expect(priceForProfit(600, A)).toBeCloseTo(17077.45, 2))
})

describe('Vector B — purchase 100, list 125', () => {
  const MARGIN: EngineParams = { regime: 'MARGIN', vatRate: 21, landedCostEur: 100, purchaseGrossEur: 100, inputVatEur: 0 }
  const NORMAL: EngineParams = { regime: 'NORMAL', vatRate: 21, landedCostEur: 100, purchaseGrossEur: 121, inputVatEur: 21 }

  it('MARGIN net_revenue = 120.66', () => expect(netRevenue(125, MARGIN)).toBeCloseTo(120.66, 2))
  it('MARGIN vat_due = 4.34', () => expect(vatDue(125, MARGIN)).toBeCloseTo(4.34, 2))
  it('MARGIN profit_net = 20.66', () => expect(profitNet(125, MARGIN)).toBeCloseTo(20.66, 2))
  it('MARGIN margin_net = 17.12%', () => expect(marginNet(125, MARGIN) * 100).toBeCloseTo(17.12, 2))

  it('NORMAL net_revenue = 103.31', () => expect(netRevenue(125, NORMAL)).toBeCloseTo(103.31, 2))
  it('NORMAL vat_due = 0.69', () => expect(vatDue(125, NORMAL)).toBeCloseTo(0.69, 2))
  it('NORMAL profit_net = 3.31', () => expect(profitNet(125, NORMAL)).toBeCloseTo(3.31, 2))
  it('NORMAL margin_net = 3.20%', () => expect(marginNet(125, NORMAL) * 100).toBeCloseTo(3.2, 2))
})

describe('Vector C — NORMAL loss must render as a loss', () => {
  const NORMAL: EngineParams = { regime: 'NORMAL', vatRate: 21, landedCostEur: 100, purchaseGrossEur: 121, inputVatEur: 21 }
  it('net_revenue(101) = 83.47', () => expect(netRevenue(101, NORMAL)).toBeCloseTo(83.47, 2))
  it('profit_net(101) = -16.53', () => expect(profitNet(101, NORMAL)).toBeCloseTo(-16.53, 2))
  it('is negative, never +1%', () => expect(marginNet(101, NORMAL)).toBeLessThan(0))
})

// ── Property tests (spec §12) ──────────────────────────────────────────────

describe('properties', () => {
  const cases: EngineParams[] = [
    { regime: 'MARGIN', vatRate: 21, landedCostEur: 15943.35, purchaseGrossEur: 14000, inputVatEur: 0 },
    { regime: 'NORMAL', vatRate: 21, landedCostEur: 100, purchaseGrossEur: 121, inputVatEur: 21 },
    { regime: 'MARGIN', vatRate: 19, landedCostEur: 8000, purchaseGrossEur: 7000, inputVatEur: 0 },
    { regime: 'NORMAL', vatRate: 19, landedCostEur: 12000, purchaseGrossEur: 14280, inputVatEur: 2280 },
  ]

  it('profit_net(breakeven) = 0', () => {
    for (const p of cases) expect(profitNet(breakevenPrice(p), p)).toBeCloseTo(0, 6)
  })

  it('profit_net(critical) = target', () => {
    for (const p of cases) {
      const T = 600
      expect(profitNet(priceForProfit(T, p), p)).toBeCloseTo(T, 6)
    }
  })

  it('net_revenue is monotonic in price', () => {
    for (const p of cases) {
      let prev = -Infinity
      for (let P = 0; P <= 50000; P += 250) {
        const n = netRevenue(P, p)
        expect(n).toBeGreaterThanOrEqual(prev)
        prev = n
      }
    }
  })
})
