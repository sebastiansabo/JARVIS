import type { BuybackOffer } from '@/types/buyback'

/**
 * Pick the "latest" offer: the one with the most recent `created_at`, breaking
 * ties by the highest `id`. When `predicate` is supplied, only offers matching
 * it are considered (e.g. pending-only for the client-decision action).
 * Returns `undefined` when nothing qualifies.
 */
export function pickLatestOffer(
  offers: BuybackOffer[],
  predicate?: (offer: BuybackOffer) => boolean,
): BuybackOffer | undefined {
  const pool = predicate ? offers.filter(predicate) : offers
  if (!pool.length) return undefined
  return pool.reduce((latest, o) => {
    const oTime = new Date(o.created_at).getTime()
    const latestTime = new Date(latest.created_at).getTime()
    if (oTime !== latestTime) return oTime > latestTime ? o : latest
    return o.id > latest.id ? o : latest
  })
}
