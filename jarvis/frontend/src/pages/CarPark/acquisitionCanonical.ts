const r2 = (n: number) => Math.round(n * 100) / 100
const pos = (v: unknown): number => (typeof v === 'number' && v > 0 ? v : 0)

export function toCanonical({ netLei, vatRate, kurs }:
  { netLei: unknown; vatRate: unknown; kurs: unknown }) {
  const n = pos(netLei), k = pos(kurs), v = typeof vatRate === 'number' ? vatRate : 0
  if (n <= 0 || k <= 0) return { acquisition_price: null, purchase_price_net: null }
  return { acquisition_price: r2((n * (1 + v / 100)) / k), purchase_price_net: r2(n / k) }
}

export function netLeiFromCanonical({ purchase_price_net, kurs }:
  { purchase_price_net: unknown; kurs: unknown }): number | null {
  const p = pos(purchase_price_net), k = pos(kurs)
  return p > 0 && k > 0 ? r2(p * k) : null
}
