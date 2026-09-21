/**
 * Pure derivation of the acquisition/cost inputs that feed the profitability
 * econ engine (see pricingEngine.ts). Extracted from Detail.tsx's
 * ProfitabilitySummary so the canonical-currency math is unit-testable.
 *
 * CANONICAL MODEL:
 *   purchase_price_net = NET EUR cost basis (used directly, no VAT division)
 *   acquisition_price  = GROSS EUR actually paid (incl. VAT)
 * In MARGIN regime (vat_deductible === false) purchase-side VAT is
 * non-deductible, so for that car net == gross and there is no input VAT.
 * All amounts are EUR.
 */
import type { VatRegime } from './pricingEngine'

/** The subset of a Vehicle this derivation reads. Vehicle satisfies it structurally. */
export type ProfitInputsVehicle = {
  purchase_price_net: number | null
  acquisition_price: number | null
  purchase_vat_rate: number | null
  vat_deductible: boolean
  cost_lines: string | null
}

export type AcquisitionProfitInputs = {
  regime: VatRegime
  vatRate: number
  /** Canonical NET EUR cost basis (purchase_price_net, used directly). */
  netAcqEur: number
  /** Canonical GROSS EUR paid (acquisition_price, with legacy fallback). */
  grossAcqEur: number
  /** Σ cost_lines.eur — extra costs only, NOT the buy price. */
  costLinesEur: number
  /** netAcqEur + costLinesEur — the econ engine's landed cost. */
  landedCostEur: number
  /** === grossAcqEur; the margin-scheme taxable base. */
  purchaseGrossEur: number
  /** Deductible input VAT (gross − net); 0 in MARGIN. */
  inputVatEur: number
}

/** Sum the `eur` field of the vehicle.cost_lines JSON array → 0 on any error. */
function sumCostLinesEur(raw: string | null | undefined): number {
  if (!raw) return 0
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return 0
    return parsed.reduce((s: number, l) => s + (Number((l as { eur?: unknown }).eur) || 0), 0)
  } catch {
    return 0
  }
}

export function acquisitionProfitInputs(vehicle: ProfitInputsVehicle): AcquisitionProfitInputs {
  const regime: VatRegime = vehicle.vat_deductible === false ? 'MARGIN' : 'NORMAL'
  const vatRate = regime === 'MARGIN' ? 21 : (Number(vehicle.purchase_vat_rate) || 21)
  const netAcqEur = Number(vehicle.purchase_price_net) || 0 // canonical NET EUR cost basis
  // canonical GROSS EUR column; fall back to deriving gross from net for any
  // legacy row missing acquisition_price. MARGIN cars carry no purchase-side
  // VAT, so their gross == net (no (1+vat) uplift on the fallback).
  const grossAcqEur = Number(vehicle.acquisition_price)
    || (regime === 'MARGIN' ? netAcqEur : netAcqEur * (1 + vatRate / 100))
  const costLinesEur = sumCostLinesEur(vehicle.cost_lines)
  const landedCostEur = netAcqEur + costLinesEur
  const inputVatEur = regime === 'NORMAL' ? grossAcqEur - netAcqEur : 0
  return {
    regime, vatRate, netAcqEur, grossAcqEur, costLinesEur,
    landedCostEur, purchaseGrossEur: grossAcqEur, inputVatEur,
  }
}
