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
 *
 * LEGACY FALLBACK: pre-migration rows (acquisition_currency === 'RON') stored
 * NET LEI in acquisition_price and GROSS EUR in purchase_price_net. The RON
 * branch converts NET LEI / kurs → net EUR (or derives from the gross-EUR
 * purchase_price_net when no kurs). Mirrors money.py net_buy + PricingSheet.
 */
import type { VatRegime } from './pricingEngine'

/** The subset of a Vehicle this derivation reads. Vehicle satisfies it structurally. */
export type ProfitInputsVehicle = {
  purchase_price_net: number | null
  acquisition_price: number | null
  purchase_vat_rate: number | null
  vat_deductible: boolean
  cost_lines: string | null
  /** Legacy 'RON' marks the pre-migration editor convention (NET LEI + GROSS EUR ppn). */
  acquisition_currency?: string | null
  /** RON/EUR BNR kurs, needed to convert a legacy 'RON' row's NET LEI to EUR. */
  acquisition_exchange_rate?: number | null
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
  let netAcqEur: number
  let grossAcqEur: number
  if (vehicle.acquisition_currency === 'RON') {
    // Legacy editor convention: acquisition_price = NET LEI, purchase_price_net =
    // GROSS EUR. Convert NET LEI / kurs → net EUR; without a usable kurs, derive
    // net from the gross-EUR purchase_price_net. NORMAL matches money.py net_buy
    // and PricingSheet's 'RON' branch. MARGIN keeps net == gross (no deductible
    // purchase-side VAT) — consistent with the canonical MARGIN path below.
    const kurs = Number(vehicle.acquisition_exchange_rate) || 0
    const netLei = Number(vehicle.acquisition_price) || 0
    if (kurs > 0 && netLei > 0) {
      netAcqEur = netLei / kurs
    } else {
      const grossFallback = Number(vehicle.purchase_price_net) || 0
      netAcqEur = regime === 'MARGIN' ? grossFallback : grossFallback / (1 + vatRate / 100)
    }
    grossAcqEur = regime === 'MARGIN' ? netAcqEur : netAcqEur * (1 + vatRate / 100)
  } else {
    // Canonical: purchase_price_net = NET EUR cost basis (used directly);
    // acquisition_price = GROSS EUR. Fall back to deriving gross from net for any
    // canonical row missing acquisition_price (MARGIN → gross == net, no uplift).
    netAcqEur = Number(vehicle.purchase_price_net) || 0
    grossAcqEur = Number(vehicle.acquisition_price)
      || (regime === 'MARGIN' ? netAcqEur : netAcqEur * (1 + vatRate / 100))
    // Symmetric fallback (mirrors PricingSheet.computePricingModel): a row with a
    // GROSS EUR acquisition_price but missing purchase_price_net still gets a NET
    // basis, so cost/profit never collapse to zero. NORMAL divides out the VAT;
    // MARGIN keeps net == gross (no deductible purchase-side VAT).
    if (netAcqEur <= 0 && grossAcqEur > 0) {
      netAcqEur = regime === 'MARGIN' ? grossAcqEur : grossAcqEur / (1 + vatRate / 100)
    }
  }
  const costLinesEur = sumCostLinesEur(vehicle.cost_lines)
  const landedCostEur = netAcqEur + costLinesEur
  const inputVatEur = regime === 'NORMAL' ? grossAcqEur - netAcqEur : 0
  return {
    regime, vatRate, netAcqEur, grossAcqEur, costLinesEur,
    landedCostEur, purchaseGrossEur: grossAcqEur, inputVatEur,
  }
}
