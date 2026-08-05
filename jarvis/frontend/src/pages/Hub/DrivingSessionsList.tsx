import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Car, Gauge, User2, Search, RotateCcw, PlayCircle, ChevronDown,
  FileDown, Trash2, Phone, CalendarDays,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { foiParcursApi } from '@/api/foiParcurs'
import { sessionStatus } from '@/pages/FoiParcurs/sessionStatus'
import type { FoiContract, FpVehicle } from '@/types/foiParcurs'

/** Short ro-RO date+time. Departure/return are naive wall-clock strings; the
 *  standalone module renders them with plain Date, so we match that (no TZ shift
 *  logic here — consistent with the rest of the web FoiParcurs module). */
function fmtDateTime(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso.length <= 16 ? `${iso}` : iso)
  return isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('ro-RO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

interface Props {
  companyId: number
  brand: string
  /** Selected car VINs (from the panel's Filtre modal); [] = all cars. */
  carFilter?: string[]
  /** Selected consultant (advisor) names; [] = all consultants. */
  consultantFilter?: string[]
  onActivate: (id: number) => void
  onReturn: (id: number) => void
}

/**
 * Apple/iOS-style, mobile-first session list for the Hub Driving Sessions panel.
 * Replaces the wide desktop SessionsTab table (which overflows the narrow Hub
 * column). Ports the jarvis-mobile-2 TestDriveCard look: tinted avatar, name +
 * status pill, vehicle, advisor + datetime, and a right-edge Începe/Retur
 * action, with tap-to-expand details. Reuses the same data + status derivation;
 * actions call back into the panel's overlay openers.
 */
export default function DrivingSessionsList({ companyId, brand, carFilter = [], consultantFilter = [], onActivate, onReturn }: Props) {
  const queryClient = useQueryClient()
  const [showArchived, setShowArchived] = useState(false)
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () => foiParcursApi.getContracts({ company_id: companyId > 0 ? companyId : undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })
  const { data: vehiclesData } = useQuery({ queryKey: ['fp-vehicles'], queryFn: () => foiParcursApi.getVehicles(), staleTime: 30_000 })

  const vinVehicle = useMemo(
    () => new Map((vehiclesData?.vehicles ?? []).map((v) => [v.vin, v] as const)),
    [vehiclesData],
  )

  const discardMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.discardTestDrive(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] }),
  })

  const items = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (data?.contracts ?? []).filter((c) => {
      // Match the selected brand against the vehicle's `brand` (the dealer/catalog
      // name that populates the dropdown, e.g. "MG Motor"), falling back to `mark`
      // (the short manufacturer code, e.g. "MG"). They differ for some marques, so
      // comparing only `mark` used to hide every session (see MG on Autoworld PLUS).
      if (brand && c.vin) {
        const vh = vinVehicle.get(c.vin)
        if ((vh?.brand ?? '').trim() !== brand && (vh?.mark ?? '').trim() !== brand) return false
      }
      if (carFilter.length && (!c.vin || !carFilter.includes(c.vin))) return false
      if (consultantFilter.length && !consultantFilter.includes((c.advisor_name ?? '').trim())) return false
      const isComplete = sessionStatus(c).key === 'finalizat'
      if (showArchived ? !isComplete : isComplete) return false
      if (q) {
        const hay = `${c.client_name ?? ''} ${c.vin ?? ''} ${c.advisor_name ?? ''} ${vinVehicle.get(c.vin ?? '')?.model ?? ''}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [data, brand, vinVehicle, showArchived, search, carFilter, consultantFilter])

  return (
    <div className="space-y-3">
      {/* iOS search field */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Caută după client, VIN, consilier"
          className="h-11 w-full rounded-xl border border-transparent bg-muted/60 pl-9 pr-3 text-base outline-none transition-colors placeholder:text-muted-foreground focus:border-border focus:bg-background"
        />
      </div>

      {/* iOS segmented control */}
      <div className="flex h-9 gap-0.5 rounded-lg bg-muted p-0.5">
        {[
          { key: false, label: 'Active' },
          { key: true, label: 'Arhivă' },
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

      {/* List */}
      {isLoading ? (
        <div className="space-y-2.5">
          {[...Array(4)].map((_, i) => <div key={i} className="h-[76px] animate-pulse rounded-2xl bg-muted" />)}
        </div>
      ) : isError ? (
        <p className="py-10 text-center text-sm text-destructive">Nu s-au putut încărca sesiunile.</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
            <Car className="h-8 w-8 text-muted-foreground/40" />
          </div>
          <p className="text-sm text-muted-foreground">
            {search ? 'Niciun rezultat' : showArchived ? 'Nicio sesiune arhivată' : 'Nicio sesiune activă'}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {items.map((c) => (
            <SessionCard
              key={c.id}
              contract={c}
              vehicle={c.vin ? vinVehicle.get(c.vin) : undefined}
              expanded={expandedId === c.id}
              onToggle={() => setExpandedId((prev) => (prev === c.id ? null : c.id))}
              onActivate={() => onActivate(c.id)}
              onReturn={() => onReturn(c.id)}
              onDiscard={() => {
                if (confirm('Renunți la această sesiune planificată? Acțiunea nu poate fi anulată.')) discardMutation.mutate(c.id)
              }}
              discarding={discardMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function SessionCard({
  contract: c, vehicle, expanded, onToggle, onActivate, onReturn, onDiscard, discarding,
}: {
  contract: FoiContract
  vehicle?: FpVehicle
  expanded: boolean
  onToggle: () => void
  onActivate: () => void
  onReturn: () => void
  onDiscard: () => void
  discarding: boolean
}) {
  const ss = sessionStatus(c)
  const isPlanned = ss.key === 'planificat'
  const isDone = ss.key === 'finalizat'
  const showRetur = ss.key === 'driving' || ss.key === 'intarziat'

  const tester = c.client_name || (c.client_id != null ? `Client #${c.client_id}` : '—')
  const vehicleName = vehicle
    ? [vehicle.mark, vehicle.model].filter(Boolean).join(' ') || vehicle.registration_number || c.vin
    : c.vin || '—'

  return (
    <div className="overflow-hidden rounded-2xl border border-border/60 bg-card shadow-sm">
      <div className="flex items-stretch">
        {/* Tap target: opens/closes the detail expansion */}
        <button
          type="button"
          onClick={onToggle}
          className="flex min-w-0 flex-1 items-center gap-3 p-3.5 text-left transition-transform active:scale-[0.99]"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-500/10">
            <Car className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate text-[15px] font-semibold leading-tight">{tester}</span>
              <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide', ss.badgeClass)}>
                {ss.label}
              </span>
            </div>
            <div className="mt-0.5 flex items-center gap-1 truncate text-[13px] text-muted-foreground">
              <Gauge className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{vehicleName}</span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1 truncate text-[12px] text-muted-foreground">
                <User2 className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{c.advisor_name || '—'}</span>
              </span>
              <span className="shrink-0 text-[12px] text-muted-foreground">{fmtDateTime(c.departure_datetime)}</span>
            </div>
          </div>
          <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground/60 transition-transform', expanded && 'rotate-180')} />
        </button>

        {/* Right-edge primary action (mirrors the mobile card) */}
        {isPlanned ? (
          <button
            type="button"
            onClick={onActivate}
            aria-label="Începe sesiunea"
            className="flex w-16 shrink-0 flex-col items-center justify-center gap-0.5 border-l border-border/60 text-indigo-600 transition-transform active:scale-95 dark:text-indigo-400"
          >
            <PlayCircle className="h-5 w-5" />
            <span className="text-[10px] font-semibold uppercase tracking-wide">Începe</span>
          </button>
        ) : showRetur ? (
          <button
            type="button"
            onClick={onReturn}
            aria-label="Completează retur"
            className="flex w-16 shrink-0 flex-col items-center justify-center gap-0.5 border-l border-border/60 text-primary transition-transform active:scale-95"
          >
            <RotateCcw className="h-5 w-5" />
            <span className="text-[10px] font-semibold uppercase tracking-wide">Retur</span>
          </button>
        ) : null}
      </div>

      {/* Inline detail expansion */}
      {expanded && (
        <div className="border-t border-border/60 bg-muted/20 px-3.5 py-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
            <Field label="Client" value={tester} />
            <Field label="Telefon" value={c.client_phone || '—'} icon={<Phone className="h-3 w-3" />} />
            <Field label="Vehicul" value={vehicleName} />
            <Field label="VIN" value={c.vin || '—'} mono />
            <Field label="Kilometraj" value={`${c.km_start ?? vehicle?.mileage_floor ?? '—'}${isDone && c.km_end != null ? ` → ${c.km_end}` : ''} km`} />
            <Field label="Perioadă" value={`${fmtDateTime(c.departure_datetime)}${c.return_datetime ? ` – ${fmtDateTime(c.return_datetime)}` : ''}`} icon={<CalendarDays className="h-3 w-3" />} />
          </dl>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {!isPlanned && (
              <a
                href={foiParcursApi.getContractPdfUrl(c.id, 'legal')}
                target="_blank"
                rel="noopener"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-background px-3 text-[13px] font-medium shadow-sm ring-1 ring-border transition-colors hover:bg-muted"
              >
                <FileDown className="h-3.5 w-3.5" /> Descarcă PDF
              </a>
            )}
            {isPlanned && (
              <button
                type="button"
                onClick={onDiscard}
                disabled={discarding}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-destructive ring-1 ring-destructive/30 transition-colors hover:bg-destructive/10 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" /> Renunță
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, value, icon, mono }: { label: string; value: string; icon?: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground/70">{icon}{label}</dt>
      <dd className={cn('mt-0.5 truncate font-medium', mono && 'font-mono text-[12px]')}>{value}</dd>
    </div>
  )
}
