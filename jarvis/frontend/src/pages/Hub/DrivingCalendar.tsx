import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, CalendarDays, Car } from 'lucide-react'
import { cn } from '@/lib/utils'
import { naiveDate } from '@/lib/naiveDate'
import { foiParcursApi } from '@/api/foiParcurs'
import { sessionStatus } from '@/pages/FoiParcurs/sessionStatus'
import type { FoiContract, FpVehicle } from '@/types/foiParcurs'

type CalView = 'day' | 'week' | 'month'
const WEEKDAY_LABELS = ['Lu', 'Ma', 'Mi', 'Jo', 'Vi', 'Sâ', 'Du']
const pad = (n: number) => String(n).padStart(2, '0')

function keyOf(d: Date): string { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
function dayKeyOf(iso?: string | null): string { const d = naiveDate(iso); return d ? keyOf(d) : 'unknown' }
function addDays(d: Date, n: number): Date { const x = new Date(d); x.setDate(x.getDate() + n); return x }
function addMonths(d: Date, n: number): Date { const x = new Date(d); x.setDate(1); x.setMonth(x.getMonth() + n); return x }
function startOfWeek(d: Date): Date { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x }
function dayLabel(key: string): string {
  if (key === 'unknown') return 'Fără dată'
  return new Date(`${key}T00:00:00`).toLocaleDateString('ro-RO', { weekday: 'long', day: '2-digit', month: 'long' })
}
function formatTime(iso?: string | null): string {
  const d = naiveDate(iso)
  return d ? d.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' }) : '—'
}

interface Props {
  companyId: number
  brand: string
  onActivate: (id: number) => void
  onReturn: (id: number) => void
}

/**
 * Apple/iOS mobile-first calendar for the Hub Driving Sessions panel — a web
 * port of the jarvis-mobile-2 TestDrive Calendar (Day / Week / Month). Shows
 * planned + live sessions (excludes finalized), bucketed by naive wall-clock
 * day. Company/brand come from the panel; tapping a session opens its
 * activate/return overlay (planned → activate, driving/late → return).
 */
export default function DrivingCalendar({ companyId, brand, onActivate, onReturn }: Props) {
  const [view, setView] = useState<CalView>('week')
  const [anchor, setAnchor] = useState<Date>(() => new Date())
  const [picked, setPicked] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () => foiParcursApi.getContracts({ company_id: companyId || undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })
  const { data: vehiclesData } = useQuery({ queryKey: ['fp-vehicles'], queryFn: () => foiParcursApi.getVehicles(), staleTime: 30_000 })
  const vinVehicle = useMemo(() => new Map((vehiclesData?.vehicles ?? []).map((v) => [v.vin, v] as const)), [vehiclesData])

  const todayKey = keyOf(new Date())

  // planned/driving/late sessions for the selected company + brand, by day.
  const byDay = useMemo(() => {
    const map = new Map<string, FoiContract[]>()
    for (const c of data?.contracts ?? []) {
      if (brand && c.vin && (vinVehicle.get(c.vin)?.mark ?? '').trim() !== brand) continue
      const k = sessionStatus(c).key
      if (k !== 'planificat' && k !== 'driving' && k !== 'intarziat') continue
      const key = dayKeyOf(c.departure_datetime)
      const list = map.get(key) ?? []
      list.push(c)
      map.set(key, list)
    }
    for (const list of map.values()) list.sort((a, b) => (a.departure_datetime || '').localeCompare(b.departure_datetime || ''))
    return map
  }, [data, brand, vinVehicle])

  const openContract = (c: FoiContract) => {
    if (sessionStatus(c).key === 'planificat') onActivate(c.id)
    else onReturn(c.id)
  }
  const go = (dir: 1 | -1) => {
    setAnchor((a) => (view === 'day' ? addDays(a, dir) : view === 'week' ? addDays(a, 7 * dir) : addMonths(a, dir)))
    setPicked(null)
  }
  const goToday = () => { setAnchor(new Date()); setPicked(null) }

  // Period label + agenda day-keys (day/week).
  let periodLabel = ''
  let agendaKeys: string[] = []
  if (view === 'day') {
    periodLabel = anchor.toLocaleDateString('ro-RO', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })
    agendaKeys = [keyOf(anchor)]
  } else if (view === 'week') {
    const ws = startOfWeek(anchor); const we = addDays(ws, 6)
    const weM = we.toLocaleDateString('ro-RO', { month: 'long' })
    periodLabel = ws.getMonth() === we.getMonth()
      ? `${ws.getDate()} – ${we.getDate()} ${weM}`
      : `${ws.getDate()} ${ws.toLocaleDateString('ro-RO', { month: 'long' })} – ${we.getDate()} ${weM}`
    agendaKeys = Array.from({ length: 7 }, (_, i) => keyOf(addDays(ws, i)))
  } else {
    periodLabel = anchor.toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })
  }

  // Month grid (6 weeks) + selected-day.
  const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const gridStart = startOfWeek(monthStart)
  const monthCells = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const monthActiveKey = picked ?? (monthCells.some((d) => keyOf(d) === todayKey) ? todayKey : keyOf(monthStart))
  const agendaGroups = agendaKeys.map((k) => [k, byDay.get(k) ?? []] as const).filter(([, items]) => items.length > 0)

  return (
    <div className="space-y-3">
      {/* iOS view switcher */}
      <div className="flex h-9 gap-0.5 rounded-lg bg-muted p-0.5">
        {([['day', 'Zi'], ['week', 'Săptămână'], ['month', 'Lună']] as const).map(([v, label]) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={cn('flex-1 rounded-md text-sm font-medium transition-colors', view === v ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Period navigation */}
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => go(-1)} className="flex h-9 w-9 items-center justify-center rounded-full bg-muted transition-colors hover:bg-muted/70"><ChevronLeft className="h-5 w-5" /></button>
        <p className="flex-1 text-center text-sm font-semibold capitalize">{periodLabel}</p>
        <button type="button" onClick={() => go(1)} className="flex h-9 w-9 items-center justify-center rounded-full bg-muted transition-colors hover:bg-muted/70"><ChevronRight className="h-5 w-5" /></button>
        <button type="button" onClick={goToday} className="rounded-full bg-muted px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-muted/70">Azi</button>
      </div>

      {isLoading ? (
        <div className="space-y-2.5">{[...Array(3)].map((_, i) => <div key={i} className="h-16 animate-pulse rounded-2xl bg-muted" />)}</div>
      ) : isError ? (
        <p className="py-8 text-center text-sm text-destructive">Nu s-a putut încărca calendarul.</p>
      ) : view === 'month' ? (
        <>
          <div className="rounded-2xl border border-border/60 bg-card p-2">
            <div className="grid grid-cols-7">
              {WEEKDAY_LABELS.map((w) => <div key={w} className="py-1 text-center text-[10px] font-semibold text-muted-foreground">{w}</div>)}
              {monthCells.map((d) => {
                const k = keyOf(d)
                const inMonth = d.getMonth() === anchor.getMonth()
                const count = byDay.get(k)?.length ?? 0
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setPicked(k)}
                    className={cn(
                      'relative flex aspect-square flex-col items-center justify-center rounded-lg text-sm',
                      !inMonth && 'text-muted-foreground/40',
                      k === monthActiveKey && 'bg-primary/15 font-bold',
                      k === todayKey && 'ring-1 ring-primary',
                    )}
                  >
                    {d.getDate()}
                    {count > 0 && <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-primary" />}
                  </button>
                )
              })}
            </div>
          </div>
          <DayGroup label={dayLabel(monthActiveKey)} items={byDay.get(monthActiveKey) ?? []} vinVehicle={vinVehicle} onOpen={openContract} emptyText="Nicio sesiune în această zi" />
        </>
      ) : agendaGroups.length === 0 ? (
        <Empty />
      ) : (
        agendaGroups.map(([key, items]) => (
          <DayGroup key={key} label={dayLabel(key)} items={items} vinVehicle={vinVehicle} onOpen={openContract} />
        ))
      )}
    </div>
  )
}

function Empty() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted"><CalendarDays className="h-8 w-8 text-muted-foreground/40" /></div>
      <p className="text-sm text-muted-foreground">Nicio sesiune în această perioadă</p>
    </div>
  )
}

function DayGroup({ label, items, vinVehicle, onOpen, emptyText }: {
  label: string; items: FoiContract[]; vinVehicle: Map<string, FpVehicle>; onOpen: (c: FoiContract) => void; emptyText?: string
}) {
  return (
    <div className="space-y-2">
      <p className="px-1 text-xs font-semibold uppercase capitalize tracking-wide text-muted-foreground">{label}</p>
      {items.length === 0 ? (
        emptyText ? <p className="px-1 py-4 text-center text-sm text-muted-foreground">{emptyText}</p> : null
      ) : (
        <div className="space-y-2">{items.map((c) => <CalendarRow key={c.id} contract={c} vehicle={c.vin ? vinVehicle.get(c.vin) : undefined} onOpen={() => onOpen(c)} />)}</div>
      )}
    </div>
  )
}

function CalendarRow({ contract: c, vehicle, onOpen }: { contract: FoiContract; vehicle?: FpVehicle; onOpen: () => void }) {
  const ss = sessionStatus(c)
  const tester = c.client_name || (c.client_id != null ? `Client #${c.client_id}` : '—')
  const vehicleName = vehicle ? [vehicle.mark, vehicle.model].filter(Boolean).join(' ') || vehicle.registration_number || c.vin : c.vin || '—'
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-2xl border border-border/60 bg-card p-3.5 text-left shadow-sm transition-transform active:scale-[0.99]"
    >
      <div className="flex h-9 w-11 shrink-0 items-center justify-center rounded-xl bg-muted">
        <span className="text-[11px] font-bold leading-none tabular-nums">{formatTime(c.departure_datetime)}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[15px] font-semibold">{tester}</span>
          <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide', ss.badgeClass)}>{ss.label}</span>
        </div>
        <div className="mt-0.5 flex items-center gap-1 truncate text-[13px] text-muted-foreground">
          <Car className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{vehicleName}</span>
        </div>
      </div>
    </button>
  )
}
