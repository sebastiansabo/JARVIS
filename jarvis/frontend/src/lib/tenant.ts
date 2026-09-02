/** Tenant = Company × Brand. A dealership operates one tenant per franchise
 *  brand (e.g. "Autoworld PLUS › Mazda" and "Autoworld PLUS › MG Motor" are two
 *  distinct tenants), defined in company-brands settings — independent of what
 *  stock happens to exist under it. */
export interface TenantVehicle {
  brand?: string | null
  mark?: string | null
}

/** The tenant a car belongs to is identified by its catalog `brand` — the label
 *  defined in company-brands settings. `mark` is only descriptive make metadata
 *  (and its casing drifts, e.g. "MAZDA"), so it is a fallback, never the key. */
export function vehicleTenant(v: TenantVehicle): string {
  return (v.brand ?? '').trim() || (v.mark ?? '').trim()
}

/** True when a vehicle belongs to the selected tenant brand. '' = all tenants.
 *  Matched case-insensitively so descriptive casing drift never hides a car. */
export function matchesTenant(v: TenantVehicle, brand: string): boolean {
  const sel = brand.trim()
  if (!sel) return true
  return vehicleTenant(v).toLowerCase() === sel.toLowerCase()
}
