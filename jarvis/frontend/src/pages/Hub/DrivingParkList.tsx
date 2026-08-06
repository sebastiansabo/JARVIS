import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Car, Gauge, Search, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FpVehicle } from '@/types/foiParcurs'

interface Props {
  companyId: number
  brand: string
  /** Selected car VINs (from the panel's Filtre modal); [] = all cars. */
  carFilter?: string[]
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

type ParkStatus = { label: string; badgeClass: string; reason?: string }
// Availability derived from the vehicle's own flags (read-only view — no session
// cross-reference): archived → locked-out → scheduled-block-now → available.
function parkStatus(v: FpVehicle): ParkStatus {
  if (v.is_active === false) return { label: 'Arhivat', badgeClass: 'bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300', reason: v.archive_category ?? v.archive_note ?? undefined }
  if (v.locked_out) return { label: 'Blocat', badgeClass: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300', reason: v.lockout_category ?? v.lockout_note ?? undefined }
  if (v.blocked_now) return { label: 'Blocat', badgeClass: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200', reason: v.active_block_category ?? undefined }
  return { label: 'Disponibil', badgeClass: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' }
}

/**
 * Read-only, mobile-first fleet view for the Hub Driving Sessions panel's "Parc"
 * tab. Mirrors the DrivingSessionsList look (tinted avatar, name + status pill,
 * tap-to-expand details) but for vehicles, and carries NO mutating actions —
 * add/edit/lock/archive live only in the desktop foi-parcurs StockTab. Reuses
 * the ['fp-vehicles','all'] cache (active + archived) and filters client-side.
 */
export default function DrivingParkList({ companyId, brand, carFilter = [] }: Props) {
  const [showArchived, setShowArchived] = useState(false)
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['fp-vehicles', 'all'],
    // active_only=false returns archived vehicles too — we split via the toggle.
    queryFn: () => foiParcursApi.getVehicles(false),
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
          {items.map((v) => (
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

function ParkCard({ vehicle: v, expanded, onToggle }: { vehicle: FpVehicle; expanded: boolean; onToggle: () => void }) {
  const st = parkStatus(v)
  const name = vehicleName(v)
  const odo = v.mileage_floor ?? v.odometer_km

  return (
    <div className="overflow-hidden rounded-2xl border border-border/60 bg-card shadow-sm">
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
