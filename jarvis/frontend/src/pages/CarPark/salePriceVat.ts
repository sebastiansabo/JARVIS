// Sale-price VAT view for the vehicle detail card. Pure + testable: given the
// displayed sale price and the car's VAT regime, produce the ex-VAT (net) and
// incl-VAT (gross) figures plus a status label.
//
// Mirrors the regime logic in profitInputs.ts (MARGIN ⇔ vat_deductible===false)
// and the price's VAT-inclusive flag (price_includes_vat). In MARGIN regime VAT
// is not deductible/separable (net == gross), so no net figure is shown — the
// label carries "Fără TVA (marjă)" instead of a misleading number.

export type SaleVatRegime = 'NORMAL' | 'MARGIN'

export interface SaleVatView {
  regime: SaleVatRegime
  vatRate: number
  /** Whether the displayed price already includes VAT (false = net price). */
  includesVat: boolean
  /** Ex-VAT price. null in MARGIN (not separable) or when price is unusable. */
  netEur: number | null
  /** Incl-VAT price. null in MARGIN or when price is unusable. */
  grossEur: number | null
  /** Short VAT status, e.g. "TVA 21%", "preț fără TVA", "Fără TVA (marjă)". */
  statusLabel: string
}

const round2 = (n: number): number => Math.round(n * 100) / 100

export function saleVatView(
  price: number | null | undefined,
  opts: {
    priceIncludesVat?: boolean | null
    vatDeductible?: boolean | null
    vatRate?: number | null
  },
): SaleVatView {
  const regime: SaleVatRegime = opts.vatDeductible === false ? 'MARGIN' : 'NORMAL'
  const vatRate = Number(opts.vatRate) || 21
  const includesVat = opts.priceIncludesVat !== false

  if (regime === 'MARGIN') {
    return { regime, vatRate, includesVat, netEur: null, grossEur: null, statusLabel: 'Fără TVA (marjă)' }
  }

  const p = Number(price)
  if (!Number.isFinite(p) || p <= 0) {
    return { regime, vatRate, includesVat, netEur: null, grossEur: null, statusLabel: `TVA ${vatRate}%` }
  }

  const factor = 1 + vatRate / 100
  const netEur = includesVat ? round2(p / factor) : p
  const grossEur = includesVat ? p : round2(p * factor)
  const statusLabel = includesVat ? `TVA ${vatRate}%` : 'preț fără TVA'
  return { regime, vatRate, includesVat, netEur, grossEur, statusLabel }
}
