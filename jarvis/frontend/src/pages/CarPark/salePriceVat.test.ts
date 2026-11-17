import { describe, it, expect } from 'vitest'
import { saleVatView } from './salePriceVat'

describe('saleVatView', () => {
  it('NORMAL regime, VAT-inclusive price → net = gross / (1+rate)', () => {
    const v = saleVatView(34390, { priceIncludesVat: true, vatDeductible: true, vatRate: 21 })
    expect(v.regime).toBe('NORMAL')
    expect(v.netEur).toBe(28421.49) // 34390 / 1.21
    expect(v.grossEur).toBe(34390)
    expect(v.statusLabel).toBe('TVA 21%')
  })

  it('NORMAL regime, net price (price_includes_vat false) → gross = net * (1+rate)', () => {
    const v = saleVatView(28421.49, { priceIncludesVat: false, vatDeductible: true, vatRate: 21 })
    expect(v.includesVat).toBe(false)
    expect(v.netEur).toBe(28421.49) // already net
    expect(v.grossEur).toBe(34390) // 28421.49 * 1.21
    expect(v.statusLabel).toBe('preț fără TVA')
  })

  it('MARGIN regime → no net/gross figure, margin label', () => {
    const v = saleVatView(34390, { priceIncludesVat: true, vatDeductible: false, vatRate: 21 })
    expect(v.regime).toBe('MARGIN')
    expect(v.netEur).toBeNull()
    expect(v.grossEur).toBeNull()
    expect(v.statusLabel).toBe('Fără TVA (marjă)')
  })

  it('defaults vatRate to 21 when missing/invalid', () => {
    const v = saleVatView(12100, { priceIncludesVat: true, vatDeductible: true, vatRate: null })
    expect(v.vatRate).toBe(21)
    expect(v.netEur).toBe(10000) // 12100 / 1.21
  })

  it('honors a custom stored vatRate', () => {
    const v = saleVatView(11900, { priceIncludesVat: true, vatDeductible: true, vatRate: 19 })
    expect(v.vatRate).toBe(19)
    expect(v.netEur).toBe(10000) // 11900 / 1.19
  })

  it('unusable price in NORMAL → null figures but keeps the TVA label', () => {
    const v = saleVatView(null, { priceIncludesVat: true, vatDeductible: true, vatRate: 21 })
    expect(v.netEur).toBeNull()
    expect(v.grossEur).toBeNull()
    expect(v.statusLabel).toBe('TVA 21%')
  })

  it('treats undefined vat_deductible as NORMAL (the default regime)', () => {
    const v = saleVatView(12100, { priceIncludesVat: true, vatDeductible: null, vatRate: 21 })
    expect(v.regime).toBe('NORMAL')
  })
})
