import type { FoiContract } from '@/types/foiParcurs'

/** The Locul/Scopul shown for a session — mirrors the backend `_scop_text` /
 *  `_td_traseu` resolution: a manual override wins, else the type-derived base:
 *  event → "Eveniment: {name}", internal → its Comentariu (itinerary) verbatim
 *  (else a generic purpose), client → "Test Drive {model}" up to the company's
 *  TD max (`tdMax`, default 50, inclusive) and "Comodat / Test Drive {model}"
 *  beyond it. Cosmetic only — the session stays a test drive. */
export function resolveScop(
  c: FoiContract, vehLabel: string, override?: string | null, tdMax = 50,
): string {
  if (override && override.trim()) return override.trim()
  if (c.source === 'gap-event') return c.itinerary ? `Eveniment: ${c.itinerary}` : 'Eveniment'
  if (c.is_internal) return (c.itinerary || '').trim() || 'Deplasare în interes de serviciu'
  const prefix = (c.distance_km || 0) > (tdMax || 50) ? 'Comodat / Test Drive' : 'Test Drive'
  return `${prefix} ${vehLabel}`.trim()
}
