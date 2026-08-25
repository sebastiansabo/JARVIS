import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Car, Gauge, Search, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FpVehicle } from '@/types/foiParcurs'
import type { DocType } from '@/pages/FoiParcurs/documentType'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { vehicleHealth, type Gravity, type HealthTag } from './vehicleHealth'

interface Props {
  companyId: number
  brand: string
  /** Selected car VINs (from the panel's Filtre modal); [] = all cars. */
  carFilter?: string[]
  /** Which fleet/pool to show — 'sales' (default) or 'service' (courtesy). */
  documentType?: DocType
}

function vehicleName(v: FpVehicle): string {
  return [v.mark, v.model].filter(Boolean).join(' ') || v.registration_number || v.vin
}

/** Short ro-RO date; accepts a bare "YYYY-MM-DD" or a full ISO string. */
function fmtDate(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
}
function isExpired(iso?: string | null): boolean {
  if (!iso) return false
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  return !isNaN(d.getTime()) && d.getTime() < Date.now()
}

/** Client-side sort mode for the fleet list, keyed off the same odometer
 * reading (`mileage_floor ?? odometer_km`) shown on each ParkCard. */
type OdoSort = 'default' | 'odo_desc' | 'odo_asc'
function odoOf(v: FpVehicle): number | null {
  return v.mileage_floor ?? v.odometer_km ?? null
}

type ParkStatus = { label: string; badgeClass: string; reason?: string }
// Availability precedence: archived → locked-out → scheduled-block-now →
// out-on-a-test-drive (on_drive) → available. on_drive comes from the list
// query cross-referencing live FILLED td_form sessions, so a car physically
// out with a client no longer reads as a false "Disponibil".
function parkStatus(v: FpVehicle): ParkStatus {
  if (v.is_active === false) return { label: 'Arhivat', badgeClass: 'bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300', reason: v.archive_category ?? v.archive_note ?? undefined }
  if (v.locked_out) return { label: 'Blocat', badgeClass: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300', reason: v.lockout_category ?? v.lockout_note ?? undefined }
  if (v.blocked_now) return { label: 'Blocat', badgeClass: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200', reason: v.active_block_category ?? undefined }
  if (v.on_drive) return { label: 'Pe drum', badgeClass: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300', reason: [v.on_drive_client, v.on_drive_until ? `revine ${fmtDate(v.on_drive_until)}` : null].filter(Boolean).join(' · ') || undefined }
  return { label: 'Disponibil', badgeClass: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' }
}

/**
 * Read-only, mobile-first fleet view for the Hub Driving Sessions panel's "Parc"
 * tab. Mirrors the DrivingSessionsList look (tinted avatar, name + status pill,
 * tap-to-expand details) but for vehicles, and carries NO mutating actions —
 * add/edit/lock/archive live only in the desktop foi-parcurs StockTab. Reuses
 * the ['fp-vehicles','all'] cache (active + archived) and filters client-side.
 */
export default function DrivingParkList({ companyId, brand, carFilter = [], documentType = 'sales' }: Props) {
  const [showArchived, setShowArchived] = useState(false)
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [odoSort, setOdoSort] = useState<OdoSort>('default')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['fp-vehicles', 'all', documentType],
    // active_only=false returns archived vehicles too — we split via the toggle.
    queryFn: () => foiParcursApi.getVehicles(false, documentType),
    staleTime: 30_000,
  })

  const items = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (data?.vehicles ?? [])
      .filter((v) => {
        if (companyId > 0 && v.company_id !== companyId) return false
        // Match brand against the vehicle's `brand` (catalog label) with a `mark`
        // fallback — same rule the sessions list uses (see DrivingSessionsList).
        if (brand && (v.brand ?? '').trim() !== brand && (v.mark ?? '').trim() !== brand) return false
        if (carFilter.length && !carFilter.includes(v.vin)) return false
        const archived = v.is_active === false
        if (showArchived ? !archived : archived) return false
        if (q) {
          const hay = `${vehicleName(v)} ${v.registration_number ?? ''} ${v.vin} ${v.brand ?? ''}`.toLowerCase()
          if (!hay.includes(q)) return false
        }
        return true
      })
      .sort((a, b) => vehicleName(a).localeCompare(vehicleName(b)))
  }, [data, companyId, brand, carFilter, showArchived, search])

  // Pure client-side re-sort of the already-filtered list; unknown odometer
  // readings (both mileage_floor and odometer_km null) always sink to the
  // bottom regardless of direction.
  const sorted = useMemo(() => {
    if (odoSort === 'default') return items
    const withKey = [...items]
    withKey.sort((a, b) => {
      const ka = odoOf(a), kb = odoOf(b)
      if (ka == null && kb == null) return 0
      if (ka == null) return 1
      if (kb == null) return -1
      return odoSort === 'odo_desc' ? kb - ka : ka - kb
    })
    return withKey
  }, [items, odoSort])

  return (
    <div className="space-y-3">
      {/* iOS search field */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Caută mașină, nr., VIN"
          className="h-11 w-full rounded-xl border border-transparent bg-muted/60 pl-9 pr-3 text-base outline-none transition-colors placeholder:text-muted-foreground focus:border-border focus:bg-background"
        />
      </div>

      {/* Client-side odometer sort — purely reorders the list already produced above */}
      <Select value={odoSort} onValueChange={(v) => setOdoSort(v as OdoSort)}>
        <SelectTrigger className="w-[190px]"><SelectValue placeholder="Ordonează" /></SelectTrigger>
        <SelectContent>
          <SelectItem value="default">Ordine implicită</SelectItem>
          <SelectItem value="odo_desc">Odometru: mare → mic</SelectItem>
          <SelectItem value="odo_asc">Odometru: mic → mare</SelectItem>
        </SelectContent>
      </Select>

      {/* iOS segmented control — read-only view of active vs archived cars */}
      <div className="flex h-9 gap-0.5 rounded-lg bg-muted p-0.5">
        {[
          { key: false, label: 'Active' },
          { key: true, label: 'Arhivate' },
        ].map((seg) => (
          <button
            key={String(seg.key)}
            type="button"
            onClick={() => setShowArchived(seg.key)}
            className={cn(
              'flex-1 rounded-md text-sm font-medium transition-colors',
              showArchived === seg.key ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
            )}
          >
            {seg.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2.5">
          {[...Array(4)].map((_, i) => <div key={i} className="h-[72px] animate-pulse rounded-2xl bg-muted" />)}
        </div>
      ) : isError ? (
        <p className="py-10 text-center text-sm text-destructive">Nu s-au putut încărca mașinile.</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
            <Car className="h-8 w-8 text-muted-foreground/40" />
          </div>
          <p className="text-sm text-muted-foreground">
            {search ? 'Niciun rezultat' : showArchived ? 'Nicio mașină arhivată' : 'Nicio mașină în parc'}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {sorted.map((v) => (
            <ParkCard
              key={v.id}
              vehicle={v}
              expanded={expandedId === v.id}
              onToggle={() => setExpandedId((prev) => (prev === v.id ? null : v.id))}
            />
          ))}
        </div>
      )}
    </div>
  )
}

const GRAVITY_ACCENT: Record<Gravity, string> = {
  critical: 'border-l-4 border-l-red-500',
  warning: 'border-l-4 border-l-amber-500',
  info: 'border-l-4 border-l-slate-300',
  ok: 'border-l-4 border-l-emerald-500',
}
const TAG_CLASS: Record<HealthTag['gravity'], string> = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  info: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
}

function ParkCard({ vehicle: v, expanded, onToggle }: { vehicle: FpVehicle; expanded: boolean; onToggle: () => void }) {
  const st = parkStatus(v)
  const name = vehicleName(v)
  const odo = v.mileage_floor ?? v.odometer_km
  const health = vehicleHealth(v)

  return (
    <div className={cn('overflow-hidden rounded-2xl border border-border/60 bg-card shadow-sm', GRAVITY_ACCENT[health.gravity])}>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 p-3.5 text-left transition-transform active:scale-[0.99]"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-500/10">
          <Car className="h-4 w-4 text-blue-600 dark:text-blue-400" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[15px] font-semibold leading-tight">{name}</span>
            <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide', st.badgeClass)}>{st.label}</span>
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 truncate text-[13px] text-muted-foreground">
            <span className="truncate">{v.registration_number || '—'}</span>
            {v.brand && <><span aria-hidden>·</span><span className="truncate">{v.brand}</span></>}
          </div>
          <div className="mt-1 flex items-center gap-1 truncate text-[12px] text-muted-foreground">
            <Gauge className="h-3.5 w-3.5 shrink-0" />
            <span className="shrink-0">{odo != null ? `${odo.toLocaleString('ro-RO')} km` : '— km'}</span>
            {st.reason && <span className="truncate">· {st.reason}</span>}
          </div>
          {health.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1" title={health.tags.map((t) => t.label).join(' · ')}>
              {health.tags.slice(0, 3).map((t) => (
                <span key={t.label} className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', TAG_CLASS[t.gravity])}>
                  {t.label}
                </span>
              ))}
              {health.tags.length > 3 && (
                <span className="rounded px-1.5 py-0.5 text-[10px] font-medium bg-muted text-muted-foreground">
                  +{health.tags.length - 3}
                </span>
              )}
            </div>
          )}
        </div>
        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground/60 transition-transform', expanded && 'rotate-180')} />
      </button>

      {expanded && (
        <div className="border-t border-border/60 bg-muted/20 px-3.5 py-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
            <Field label="VIN" value={v.vin} mono />
            <Field label="Categorie" value={v.category || '—'} />
            <Field label="Combustibil" value={v.fuel_type || '—'} />
            <Field label="Culoare" value={v.color || '—'} />
            <Field label="ITP" value={fmtDate(v.itp_valid_until)} warn={isExpired(v.itp_valid_until)} />
            <Field label="RCA" value={fmtDate(v.insurance_valid_until)} warn={isExpired(v.insurance_valid_until)} />
            <Field label="Rovinietă" value={fmtDate(v.vignette_valid_until)} warn={isExpired(v.vignette_valid_until)} />
            {v.is_active === false && (
              <Field label="Arhivat" value={[v.archive_category, fmtDate(v.archived_at)].filter((x) => x && x !== '—').join(' · ') || '—'} />
            )}
          </dl>
        </div>
      )}
    </div>
  )
}

function Field({ label, value, mono, warn }: { label: string; value: string; mono?: boolean; warn?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-muted-foreground/70">{label}</dt>
      <dd className={cn('mt-0.5 truncate font-medium', mono && 'font-mono text-[12px]', warn && 'text-destructive')}>{value}</dd>
    </div>
  )
}
