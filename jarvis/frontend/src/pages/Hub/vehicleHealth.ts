export type Gravity = 'critical' | 'warning' | 'info' | 'ok'
export interface HealthTag { label: string; gravity: 'critical' | 'warning' | 'info' }
export interface VehicleHealth { gravity: Gravity; tags: HealthTag[] }

export interface HealthVehicle {
  registration_number?: string | null
  vin?: string | null
  brand?: string | null
  color?: string | null
  odometer_km?: number | null
  mileage_floor?: number | null
  norma_combustibil?: number | null
  norma_energie?: number | null
  category?: string | null
  insurance_valid_until?: string | null
  itp_valid_until?: string | null
  vignette_valid_until?: string | null
  talon_doc?: string | null
  civ_doc?: string | null
  insurance_doc?: string | null
  registration_doc?: string | null
}

const RANK: Record<Gravity, number> = { critical: 3, warning: 2, info: 1, ok: 0 }

function daysUntil(dateStr: string | null | undefined, today: Date): number | null {
  if (!dateStr) return null
  const d = new Date(`${dateStr}T00:00:00`)
  if (Number.isNaN(d.getTime())) return null
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((d.getTime() - t.getTime()) / 86_400_000)
}

export function vehicleHealth(v: HealthVehicle, today: Date = new Date()): VehicleHealth {
  const tags: HealthTag[] = []
  if (!v.registration_number) tags.push({ label: 'Fără NR', gravity: 'critical' })
  if (!v.vin) tags.push({ label: 'Fără VIN', gravity: 'critical' })

  const docs = [
    { until: v.insurance_valid_until, name: 'RCA', expired: 'RCA expirat' },
    { until: v.itp_valid_until, name: 'ITP', expired: 'ITP expirat' },
    { until: v.vignette_valid_until, name: 'Rovinietă', expired: 'Rovinietă expirată' },
  ]
  for (const doc of docs) {
    const d = daysUntil(doc.until, today)
    if (d === null) continue
    if (d < 0) tags.push({ label: doc.expired, gravity: 'critical' })
    else if (d <= 30) tags.push({ label: `${doc.name} expiră ${d}z`, gravity: 'warning' })
  }

  if (v.odometer_km == null && v.mileage_floor == null) tags.push({ label: 'Fără km', gravity: 'warning' })
  if (v.norma_combustibil == null && v.norma_energie == null) tags.push({ label: 'Fără normă', gravity: 'warning' })
  if (!v.category) tags.push({ label: 'Fără categorie', gravity: 'warning' })

  if (!v.brand) tags.push({ label: 'Fără marcă', gravity: 'info' })
  if (!v.color) tags.push({ label: 'Fără culoare', gravity: 'info' })

  const gravity = tags.reduce<Gravity>((g, t) => (RANK[t.gravity] > RANK[g] ? t.gravity : g), 'ok')
  return { gravity, tags }
}
