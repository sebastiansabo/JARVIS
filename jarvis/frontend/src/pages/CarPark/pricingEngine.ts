/**
 * Vehicle pricing engine — pure functions, no I/O.
 *
 * Correct under both Romanian VAT regimes:
 *  - NORMAL: VAT-registered supplier; sale VAT is on the full price, input VAT is reclaimed.
 *  - MARGIN (art. 312 Cod fiscal): non-VAT supplier; VAT is due only on the spread
 *    (sale price − purchase price), never on the full price.
 *
 * Margin is always "margin on net revenue" = profit / net_revenue — NOT markup on cost.
 * All amounts are EUR unless a caller converts for display. Round only at the boundary.
 */

export type VatRegime = 'MARGIN' | 'NORMAL'

export interface EngineParams {
  regime: VatRegime
  /** VAT rate as a percent, e.g. 21. */
  vatRate: number
  /** Total acquisition cost basis + all cost lines (incl. computed financing/warranty), EUR. */
  landedCostEur: number
  /** Gross purchase price in EUR — the taxable base of the margin scheme. */
  purchaseGrossEur: number
  /** Deductible input VAT (EUR); non-zero only for NORMAL. */
  inputVatEur: number
}

export interface Econ {
  price: number
  vatDue: number
  netRevenue: number
  profitNet: number
  /** profit / net_revenue */
  marginNet: number
  /** profit / landed_cost */
  markup: number
}

const rOf = (p: EngineParams) => p.vatRate / 100
/** VAT share of a gross amount: r / (1 + r) — 21% → 0.173553…. */
const qOf = (p: EngineParams) => {
  const r = rOf(p)
  return r / (1 + r)
}

export function vatDue(price: number, p: EngineParams): number {
  if (p.regime === 'MARGIN') {
    const spread = Math.max(0, price - p.purchaseGrossEur)
    return spread * qOf(p)
  }
  // NORMAL: VAT collected on the sale minus the reclaimed input VAT.
  return price - price / (1 + rOf(p)) - p.inputVatEur
}

export function netRevenue(price: number, p: EngineParams): number {
  if (p.regime === 'MARGIN') return price - vatDue(price, p)
  return price / (1 + rOf(p))
}

export function profitNet(price: number, p: EngineParams): number {
  return netRevenue(price, p) - p.landedCostEur
}

export function marginNet(price: number, p: EngineParams): number {
  const net = netRevenue(price, p)
  return net === 0 ? 0 : profitNet(price, p) / net
}

export function markup(price: number, p: EngineParams): number {
  return p.landedCostEur === 0 ? 0 : profitNet(price, p) / p.landedCostEur
}

/** Gross price that yields a required net profit `target`. */
export function priceForProfit(target: number, p: EngineParams): number {
  const need = p.landedCostEur + target
  if (p.regime === 'MARGIN') {
    const q = qOf(p)
    return (need - p.purchaseGrossEur * q) / (1 - q)
  }
  return need * (1 + rOf(p))
}

export const breakevenPrice = (p: EngineParams) => priceForProfit(0, p)

export function econ(price: number, p: EngineParams): Econ {
  return {
    price,
    vatDue: vatDue(price, p),
    netRevenue: netRevenue(price, p),
    profitNet: profitNet(price, p),
    marginNet: marginNet(price, p),
    markup: markup(price, p),
  }
}

export interface MaxBidParams {
  regime: VatRegime
  vatRate: number
  /** Effective market anchor (median × band multiplier), EUR. */
  anchorEffectiveEur: number
  /** Sum of manual cost lines (EUR). */
  manualCostLinesEur: number
  /** Financing factor: (rate_per_day/100) × target_days. */
  financingFactor: number
  /** Warranty reserve as a fraction, e.g. 0.015. */
  warrantyPct: number
  /** Required net profit (EUR). */
  profitTarget: number
}

/** Highest acquisition cost basis that still reaches the profit target at the anchor. */
export function maxPurchasePrice(m: MaxBidParams): { net: number; gross: number } {
  const r = m.vatRate / 100
  const q = r / (1 + r)
  const { anchorEffectiveEur: A, manualCostLinesEur: L, financingFactor: f, warrantyPct: w, profitTarget: T } = m
  if (m.regime === 'MARGIN') {
    const bid = (A * (1 - q - w) - L - T) / (1 - q + f)
    return { net: bid, gross: bid }
  }
  const net = (A / (1 + r) - L - A * w - T) / (1 + f)
  return { net, gross: net * (1 + r) }
}
