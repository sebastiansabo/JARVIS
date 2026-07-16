import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown } from 'lucide-react'
import { api } from '@/api/client'

interface DamageItem {
  zone?: string | null
  severity?: string | null
  note?: string | null
  photos?: string[] | null
}

interface OdometerEntry {
  contract_id?: string | null
  route_type?: string | null
  status?: string | null
  returned?: boolean
  km_start?: number | null
  km_end?: number | null
  departure_datetime?: string | null
  return_datetime?: string | null
  client_name?: string | null
  gap_km?: number | null
  departure_damage?: DamageItem[] | null
  return_damage?: DamageItem[] | null
}

interface OdometerHistoryResp {
  success?: boolean
  vin?: string
  current_odometer?: number | null
  entries?: OdometerEntry[]
}

const nf = (n?: number | null) => (n == null ? '—' : n.toLocaleString('ro-RO'))

function fmt(dt?: string | null) {
  if (!dt) return '—'
  const d = new Date(dt)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const SEVERITY: Record<string, { label: string; cls: string }> = {
  minor: { label: 'Minor', cls: 'bg-amber-100 text-amber-800' },
  moderate: { label: 'Mediu', cls: 'bg-orange-100 text-orange-800' },
  severe: { label: 'Grav', cls: 'bg-red-100 text-red-800' },
}

const hasDamage = (items?: DamageItem[] | null) => Array.isArray(items) && items.length > 0

function DamageBlock({ label, items }: { label: string; items?: DamageItem[] | null }) {
  if (!hasDamage(items)) return null
  return (
    <div className="space-y-1.5">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="space-y-1.5">
        {items!.map((d, i) => {
          const sev = SEVERITY[String(d.severity)] ?? { label: String(d.severity ?? '—'), cls: 'bg-muted text-foreground' }
          return (
            <div key={i} className="text-xs">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{d.zone}</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${sev.cls}`}>{sev.label}</span>
                {d.note && <span className="text-muted-foreground">— {d.note}</span>}
              </div>
              {Array.isArray(d.photos) && d.photos.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {d.photos.map((p, j) => (
                    <img key={j} src={p} alt="avarie" className="h-12 w-12 rounded border object-cover" />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** One drive: km line (with "-"/Driving for cars still out) + a collapsed
 *  damage report (departure/return) that expands on click. */
function DriveEntry({ e }: { e: OdometerEntry }) {
  const [showDamage, setShowDamage] = useState(false)
  const driven = e.returned && e.km_start != null && e.km_end != null ? e.km_end - e.km_start : null
  const gap = e.gap_km != null && e.gap_km > 0 ? e.gap_km : null
  const depCount = hasDamage(e.departure_damage) ? e.departure_damage!.length : 0
  const retCount = hasDamage(e.return_damage) ? e.return_damage!.length : 0
  const damageCount = depCount + retCount

  return (
    <div className="space-y-2 rounded-lg border bg-background p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{fmt(e.departure_datetime)}</span>
          <span className="text-muted-foreground">→ {e.returned ? fmt(e.return_datetime) : '-'}</span>
          {!e.returned && (
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">Driving</span>
          )}
        </div>
        <span className="text-muted-foreground">
          {e.route_type || '—'}
          {e.client_name ? ` · ${e.client_name}` : ''}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs tabular-nums">
        <span>
          KM: <b>{nf(e.km_start)}</b> → <b>{e.returned ? nf(e.km_end) : '-'}</b>
        </span>
        <span className="text-muted-foreground">Parcurs: {driven == null ? '-' : nf(driven)}</span>
        {gap != null && (
          <span className="flex items-center gap-1 font-medium text-destructive">
            <AlertTriangle className="h-3 w-3" />+{nf(gap)} km gol
          </span>
        )}
      </div>

      {damageCount > 0 && (
        <div className="border-t pt-2">
          <button
            type="button"
            onClick={() => setShowDamage((s) => !s)}
            className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showDamage ? 'rotate-180' : ''}`} />
            Raport avarii ({damageCount})
          </button>
          {showDamage && (
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <DamageBlock label="Avarii predare" items={e.departure_damage} />
              <DamageBlock label="Avarii retur" items={e.return_damage} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Per-car history for the expanded Driving Hub row: odometer evolution (with
 *  KM gaps) + collapsed per-drive damage (severity + photos). */
export function VehicleOdometerHistory({ vin }: { vin: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['odometer-history', vin],
    queryFn: () => api.get<OdometerHistoryResp>('/api/foi-parcurs/odometer-history', { vin }),
    staleTime: 30_000,
  })

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Se încarcă istoricul…</div>

  const entries = data?.entries ?? []
  if (entries.length === 0)
    return <div className="p-4 text-sm text-muted-foreground">Nicio cursă înregistrată pentru acest vehicul.</div>

  const rows = [...entries].reverse() // newest first
  const totalGap = entries.reduce((s, e) => s + (e.gap_km && e.gap_km > 0 ? e.gap_km : 0), 0)

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold">Istoric vehicul — kilometraj & avarii</h4>
        <div className="flex items-center gap-4 text-xs">
          {data?.current_odometer != null && (
            <span className="text-muted-foreground">
              Curent: <span className="font-semibold text-foreground">{nf(data.current_odometer)} km</span>
            </span>
          )}
          {totalGap > 0 && (
            <span className="flex items-center gap-1 font-medium text-destructive">
              <AlertTriangle className="h-3.5 w-3.5" />
              {nf(totalGap)} km neînregistrați
            </span>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {rows.map((e, i) => (
          <DriveEntry key={e.contract_id ?? i} e={e} />
        ))}
      </div>
    </div>
  )
}
