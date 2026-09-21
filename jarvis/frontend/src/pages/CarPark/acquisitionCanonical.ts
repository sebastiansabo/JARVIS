const r2 = (n: number) => Math.round(n * 100) / 100
const pos = (v: unknown): number => (typeof v === 'number' && v > 0 ? v : 0)

export function toCanonical({ netLei, vatRate, kurs }:
  { netLei: unknown; vatRate: unknown; kurs: unknown }) {
  const n = pos(netLei), k = pos(kurs), v = typeof vatRate === 'number' ? vatRate : 0
  if (n <= 0 || k <= 0) return { acquisition_price: null, purchase_price_net: null }
  return { acquisition_price: r2((n * (1 + v / 100)) / k), purchase_price_net: r2(n / k) }
}

// EUR-native acquisition entry: a GROSS (VAT-inclusive) EUR amount → the
// canonical pair WITHOUT needing a RON kurs. Used for cars whose acquisition is
// already in EUR (imports store only a gross EUR price; transfers store the
// EUR transfer price), so the user can edit the buy price in EUR directly.
//   acquisition_price = gross EUR
//   purchase_price_net = gross / (1 + vat/100)   (net == gross for margin / vat 0)
// gross <= 0 yields nulls — never manufacture a basis out of nothing.
export function canonicalFromGrossEur({ grossEur, vatRate }:
  { grossEur: unknown; vatRate: unknown }) {
  const g = pos(grossEur), v = typeof vatRate === 'number' && vatRate > 0 ? vatRate : 0
  if (g <= 0) return { acquisition_price: null, purchase_price_net: null }
  return { acquisition_price: r2(g), purchase_price_net: r2(g / (1 + v / 100)) }
}

export function netLeiFromCanonical({ purchase_price_net, kurs }:
  { purchase_price_net: unknown; kurs: unknown }): number | null {
  const p = pos(purchase_price_net), k = pos(kurs)
  return p > 0 && k > 0 ? r2(p * k) : null
}

// Inverse of toCanonical for the GROSS-EUR entry field: a VAT-inclusive EUR
// amount → the net LEI base. gross EUR × kurs = gross LEI; ÷ (1 + vat/100) = net LEI.
export function netLeiFromGrossEur({ grossEur, vatRate, kurs }:
  { grossEur: unknown; vatRate: unknown; kurs: unknown }): number | null {
  const g = pos(grossEur), k = pos(kurs), v = typeof vatRate === 'number' ? vatRate : 0
  return g > 0 && k > 0 ? r2((g * k) / (1 + v / 100)) : null
}
