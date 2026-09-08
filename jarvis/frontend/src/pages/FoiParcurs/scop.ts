import type { FoiContract } from '@/types/foiParcurs'

/** The Locul/Scopul shown for a session — mirrors the backend `_scop_text`
 *  resolution: a manual override wins, else the type-derived base:
 *  event → "Eveniment: {name}", client → "Test Drive {model}", internal → its
 *  Comentariu (itinerary) verbatim, else a generic purpose. */
export function resolveScop(c: FoiContract, vehLabel: string, override?: string | null): string {
  if (override && override.trim()) return override.trim()
  if (c.source === 'gap-event') return c.itinerary ? `Eveniment: ${c.itinerary}` : 'Eveniment'
  if (c.is_internal) return (c.itinerary || '').trim() || 'Deplasare în interes de serviciu'
  return `Test Drive ${vehLabel}`.trim()
}
