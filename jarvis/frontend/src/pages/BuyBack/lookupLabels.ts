import { AUTOVIT_EQUIPMENT } from '@/data/autovitData'

// The shape of GET /api/buyback/lookups/options (each dimension is a value→label list).
export type OptionsMap = Record<string, { value: string; label: string }[]>

// Resolve a stored code to its RO label; returns null (→ "—" in <Field>) when
// empty, and falls back to the raw code when the option list doesn't have it.
function toLabel(
  list: { value: string; label: string }[] | undefined,
  value: string | null | undefined,
): string | null {
  if (value == null || value === '') return null
  return list?.find((o) => o.value === value)?.label ?? value
}

/** Build per-dimension labelers from the lookups payload (equipment maps via the
 *  static AUTOVIT list, since it's a client-side comma-joined value set). */
export function makeLabelers(opts: OptionsMap | undefined) {
  const eq = new Map<string, string>()
  for (const g of AUTOVIT_EQUIPMENT) for (const o of g.options) eq.set(o.value, o.label)
  return {
    fuel: (v?: string | null) => toLabel(opts?.fuel_types, v),
    transmission: (v?: string | null) => toLabel(opts?.transmissions, v),
    gearbox: (v?: string | null) => toLabel(opts?.gearboxes, v),
    vat: (v?: string | null) => toLabel(opts?.vat_statuses, v),
    clientType: (v?: string | null) => toLabel(opts?.client_types, v),
    clientSource: (v?: string | null) => toLabel(opts?.client_sources, v),
    acquisition: (v?: string | null) => toLabel(opts?.acquisition_types, v),
    equipment: (v?: string | null): string | null =>
      !v ? null : v.split(',').map((s) => s.trim()).filter(Boolean).map((c) => eq.get(c) ?? c).join(', ') || null,
  }
}
