import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, FileText } from 'lucide-react'
import { api } from '@/api/client'
import { foiParcursApi } from '@/api/foiParcurs'
import { naiveDate } from '@/lib/naiveDate'
import { sessionStatus } from './sessionStatus'
import type { FoiContract } from '@/types/foiParcurs'

interface DamageItem {
  zone?: string | null
  severity?: string | null
  note?: string | null
  photos?: string[] | null
}

interface OdometerEntry {
  id?: number | null
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
  const d = naiveDate(dt) // departure/return are wall-clock times — no TZ shift
  return d
    ? d.toLocaleString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—'
}

const SEVERITY: Record<string, { label: string; cls: string }> = {
  minor: { label: 'Minor', cls: 'bg-amber-100 text-amber-800' },
  moderate: { label: 'Mediu', cls: 'bg-orange-100 text-orange-800' },
  severe: { label: 'Grav', cls: 'bg-red-100 text-red-800' },
}

const hasDamage = (items?: DamageItem[] | null) => Array.isArray(items) && items.length > 0

// Mirror the app/Hub session statuses (sessionStatus.ts). The odometer-history
// endpoint returns `status` + `returned` but not `td_status`, so we synthesize it:
// returned/COMPLETED → complete (Finalizat); FILLED past its return → incomplete
// (Întârziat); else driving (În desfășurare). MISSED → Ratat is handled by status.
function entryStatus(e: OdometerEntry) {
  const overdue =
    !e.returned &&
    e.status === 'FILLED' &&
    (() => {
      const r = naiveDate(e.return_datetime)
      if (r) return r < new Date()
      const d = naiveDate(e.departure_datetime)
      return !!d && Date.now() - d.getTime() > 86_400_000
    })()
  const td_status = e.returned || e.status === 'COMPLETED' ? 'complete' : overdue ? 'incomplete' : 'driving'
  return sessionStatus({ status: e.status ?? undefined, td_status } as unknown as FoiContract)
}

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
  const ss = entryStatus(e)
  const alarm = ss.key === 'intarziat' || ss.key === 'ratat' // needs attention (red)
  const depCount = hasDamage(e.departure_damage) ? e.departure_damage!.length : 0
  const retCount = hasDamage(e.return_damage) ? e.return_damage!.length : 0
  const damageCount = depCount + retCount

  return (
    <div
      className={`rounded-md border px-3 py-1.5 ${
        alarm ? 'border-red-300 bg-red-50 dark:border-red-900/50 dark:bg-red-950/20' : 'bg-background'
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
        <span className="font-medium tabular-nums">{fmt(e.departure_datetime)}</span>
        <span className="text-muted-foreground tabular-nums">→ {e.returned ? fmt(e.return_datetime) : '-'}</span>
        {ss.key !== 'finalizat' && (
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${ss.badgeClass}`}>
            {ss.key === 'intarziat' ? `⚠ ${ss.label}` : ss.label}
          </span>
        )}
        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">{e.route_type || '—'}</span>
        <span className="font-medium">{e.client_name || 'Fără client'}</span>
        <span className="text-muted-foreground tabular-nums">· KM {nf(e.km_start)} → {e.returned ? nf(e.km_end) : '-'}</span>
        {driven != null && <span className="text-muted-foreground tabular-nums">· Parcurs {nf(driven)}</span>}
        {gap != null && (
          <span className="flex items-center gap-1 font-medium text-destructive tabular-nums">
            <AlertTriangle className="h-3 w-3" />+{nf(gap)} km gol
          </span>
        )}
        {e.id != null && (e.status === 'FILLED' || e.status === 'COMPLETED') && (
          <a
            href={foiParcursApi.getContractPdfUrl(e.id, 'legal')}
            target="_blank"
            rel="noopener"
            onClick={(ev) => ev.stopPropagation()}
            className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/10"
          >
            <FileText className="h-3.5 w-3.5" /> Contract
          </a>
        )}
      </div>

      {damageCount > 0 && (
        <div className="mt-1.5 border-t pt-1.5">
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
  const [mode, setMode] = useState<'planned' | 'active' | 'istoric'>('planned')

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Se încarcă istoricul…</div>

  const entries = data?.entries ?? []
  if (entries.length === 0)
    return <div className="p-4 text-sm text-muted-foreground">Nicio cursă înregistrată pentru acest vehicul.</div>

  const totalGap = entries.reduce((s, e) => s + (e.gap_km && e.gap_km > 0 ? e.gap_km : 0), 0)

  // Planned = scheduled, not started yet; Active = out now (incl. overdue-not-returned);
  // Istoric = finished only (returned or missed). Unfinished sessions never fall into Istoric.
  const byDepartureAsc = (a: OdometerEntry, b: OdometerEntry) =>
    (naiveDate(a.departure_datetime)?.getTime() ?? Infinity) - (naiveDate(b.departure_datetime)?.getTime() ?? Infinity)
  // Bucket by the canonical app/Hub status: Planned = scheduled/unallocated;
  // Active = out now or overdue-still-out; Istoric = finished (Finalizat) or Ratat.
  const keyOf = (e: OdometerEntry) => entryStatus(e).key
  const planned = entries.filter((e) => keyOf(e) === 'planificat' || keyOf(e) === 'nealocat').sort(byDepartureAsc)
  const active = entries.filter((e) => keyOf(e) === 'driving' || keyOf(e) === 'intarziat').sort(byDepartureAsc)
  const istoric = entries.filter((e) => keyOf(e) === 'finalizat' || keyOf(e) === 'ratat').reverse() // newest first
  const rows = mode === 'planned' ? planned : mode === 'active' ? active : istoric

  const tabCls = (m: 'planned' | 'active' | 'istoric') =>
    `rounded px-2 py-0.5 text-[11px] font-semibold transition-colors ${
      mode === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
    }`

  return (
    <div className="space-y-2 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold">Sesiuni vehicul</h4>
          <div className="flex items-center gap-1 rounded-md border p-0.5">
            <button type="button" className={tabCls('planned')} onClick={() => setMode('planned')}>
              Planned ({planned.length})
            </button>
            <button type="button" className={tabCls('active')} onClick={() => setMode('active')}>
              Active ({active.length})
            </button>
            <button type="button" className={tabCls('istoric')} onClick={() => setMode('istoric')}>
              Istoric ({istoric.length})
            </button>
          </div>
        </div>
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

      {rows.length === 0 ? (
        <div className="py-2 text-xs text-muted-foreground">
          {mode === 'planned'
            ? 'Nicio sesiune planificată.'
            : mode === 'active'
              ? 'Nicio sesiune activă acum.'
              : 'Nicio sesiune în istoric.'}
        </div>
      ) : (
        <div className="space-y-1.5">
          {rows.map((e, i) => (
            <DriveEntry key={e.contract_id ?? i} e={e} />
          ))}
        </div>
      )}
    </div>
  )
}
