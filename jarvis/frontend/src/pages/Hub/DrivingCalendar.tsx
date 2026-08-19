import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Car } from 'lucide-react'
import { cn, usePersistedState, useIsMobile } from '@/lib/utils'
import { naiveDate } from '@/lib/naiveDate'
import { foiParcursApi } from '@/api/foiParcurs'
import { sessionStatus, carColor } from '@/pages/FoiParcurs/sessionStatus'
import TimeGrid, { type TimeGridEvent } from '@/pages/Hub/TimeGrid'
import SessionDetailModal from '@/pages/Hub/SessionDetailModal'
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
// Minutes-of-day (wall-clock) from a timestamptz, read naively — null when the
// value is absent/invalid, which pushes the session into the grid's "Fără oră"
// band instead of the hour columns.
function minsOfDay(iso?: string | null): number | null {
  const d = naiveDate(iso)
  return d ? d.getHours() * 60 + d.getMinutes() : null
}
function vehicleName(vehicle: FpVehicle | undefined, vin?: string | null): string {
  if (vehicle) return [vehicle.mark, vehicle.model].filter(Boolean).join(' ') || vehicle.registration_number || vin || '—'
  return vin || '—'
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
  /** Create a session for a dragged calendar range — full "YYYY-MM-DDTHH:MM"
   *  departure/return strings (return may be a later day for multi-day sessions). */
  onAdd: (departure: string, ret: string) => void
}

/**
 * Apple/iOS mobile-first calendar for the Hub Driving Sessions panel — a web
 * port of the jarvis-mobile-2 TestDrive Calendar (Day / Week / Month). Shows
 * planned + live sessions (excludes finalized), bucketed by naive wall-clock
 * day. Company/brand come from the panel; tapping a session opens its
 * activate/return overlay (planned → activate, driving/late → return).
 *
 * Week/Day render a shared 07:00–21:00 <TimeGrid> (same look as the Field
 * Sales calendar) with status-tinted blocks; dragging/clicking empty grid
 * space proposes a new session at that slot via `onAdd`. Month keeps the
 * dot-grid + selected-day agenda list.
 */
export default function DrivingCalendar({ companyId, brand, carFilter = [], consultantFilter = [], onActivate, onReturn, onAdd }: Props) {
  // Persisted so abandoning a new-session overlay (or any remount) doesn't
  // reset the calendar to a different view; Week is the default.
  const [view, setView] = usePersistedState<CalView>('hub-driving-cal-view', 'week')
  const [anchor, setAnchor] = useState<Date>(() => new Date())
  const [picked, setPicked] = useState<string | null>(null)
  // Rolling day-offset for the week window: an edge-drag advances it by ±1 day
  // (not a whole week); arrows/Azi reset it so the week stays Mon–Sun aligned.
  const [weekOffset, setWeekOffset] = useState(0)
  // Month drag-to-select a date range → multi-day session (a..b unordered).
  const [monthDrag, setMonthDrag] = useState<{ a: string; b: string } | null>(null)
  const monthRange = monthDrag ? (monthDrag.a <= monthDrag.b ? [monthDrag.a, monthDrag.b] : [monthDrag.b, monthDrag.a]) : null
  const inMonthRange = (k: string) => !!monthRange && k >= monthRange[0] && k <= monthRange[1]

  const { data, isLoading, isError } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () => foiParcursApi.getContracts({ company_id: companyId > 0 ? companyId : undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })
  const { data: vehiclesData } = useQuery({ queryKey: ['fp-vehicles'], queryFn: () => foiParcursApi.getVehicles(), staleTime: 30_000 })
  const vinVehicle = useMemo(() => new Map((vehiclesData?.vehicles ?? []).map((v) => [v.vin, v] as const)), [vehiclesData])

  const todayKey = keyOf(new Date())

  // planned/driving/late sessions for the selected company + brand, by day.
  const byDay = useMemo(() => {
    const map = new Map<string, FoiContract[]>()
    for (const c of data?.contracts ?? []) {
      // Match on the vehicle's `brand` (catalog name in the dropdown, e.g. "MG
      // Motor") with a fallback to `mark` (short code, e.g. "MG"). See the same
      // note in DrivingSessionsList — filtering on `mark` alone hid MG sessions.
      if (brand && c.vin) {
        const vh = vinVehicle.get(c.vin)
        if ((vh?.brand ?? '').trim() !== brand && (vh?.mark ?? '').trim() !== brand) continue
      }
      const k = sessionStatus(c).key
      if (k !== 'planificat' && k !== 'driving' && k !== 'intarziat') continue
      if (carFilter.length && (!c.vin || !carFilter.includes(c.vin))) continue
      if (consultantFilter.length && !consultantFilter.includes((c.advisor_name ?? '').trim())) continue
      const key = dayKeyOf(c.departure_datetime)
      const list = map.get(key) ?? []
      list.push(c)
      map.set(key, list)
    }
    for (const list of map.values()) list.sort((a, b) => (a.departure_datetime || '').localeCompare(b.departure_datetime || ''))
    return map
  }, [data, brand, vinVehicle, carFilter, consultantFilter])

  const byId = useMemo(() => new Map((data?.contracts ?? []).map((c) => [c.id, c] as const)), [data])

  // Clicking a session opens its detail modal (was: jump straight to
  // activate/return). The modal's Începe/Retur then call onActivate/onReturn.
  const [detail, setDetail] = useState<FoiContract | null>(null)
  const openContract = (c: FoiContract) => setDetail(c)
  const openById = (id: number) => { const c = byId.get(id); if (c) setDetail(c) }

  // Drag-to-reschedule (PLANNED only) — optimistic update of the shared
  // contracts cache, rolled back on error. Backend re-guards status + past-date.
  const queryClient = useQueryClient()
  const [moveErr, setMoveErr] = useState<string | null>(null)
  const contractsKey = ['foi-contracts-all', companyId] as const
  const rescheduleMut = useMutation({
    mutationFn: ({ id, departure, ret }: { id: number; departure: string; ret: string }) =>
      foiParcursApi.rescheduleTestDrive(id, { departure_datetime: departure, return_datetime: ret }),
    onMutate: async ({ id, departure, ret }) => {
      await queryClient.cancelQueries({ queryKey: contractsKey })
      const prev = queryClient.getQueryData<{ contracts: FoiContract[] }>(contractsKey)
      if (prev) {
        queryClient.setQueryData(contractsKey, {
          ...prev,
          contracts: prev.contracts.map((c) => (c.id === id ? { ...c, departure_datetime: departure, return_datetime: ret } : c)),
        })
      }
      return { prev }
    },
    onError: (err, _v, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(contractsKey, ctx.prev)
      setMoveErr((err as { data?: { error?: string } })?.data?.error ?? 'Nu s-a putut reprograma sesiunea')
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] }),
  })
  const onMove = (id: number, dayKey: string, startTime: string, endTime: string) => {
    setMoveErr(null)
    rescheduleMut.mutate({ id, departure: `${dayKey}T${startTime}`, ret: `${dayKey}T${endTime}` })
  }
  // Month drag-to-day: keep the session's time, change only the date.
  const hhmm = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`
  const rescheduleToDay = (id: number, targetKey: string) => {
    const c = byId.get(id)
    const dep = c && naiveDate(c.departure_datetime)
    if (!c || !dep || keyOf(dep) === targetKey) return
    const ret = naiveDate(c.return_datetime)
    onMove(id, targetKey, hhmm(dep), ret ? hhmm(ret) : hhmm(new Date(dep.getTime() + 3600000)))
  }
  const go = (dir: 1 | -1) => {
    // Week view is a rolling 7-day span → arrows slide it by ONE day (same as
    // an edge-drag); day/month step by a day/month.
    if (view === 'week') setWeekOffset((o) => o + dir)
    else if (view === 'day') setAnchor((a) => addDays(a, dir))
    else setAnchor((a) => addMonths(a, dir))
    setPicked(null)
  }
  const goToday = () => { setAnchor(new Date()); setWeekOffset(0); setPicked(null) }

  // Visible day columns (Week/Day) + their time-grid events.
  const weekDays = useIsMobile() ? 3 : 7 // phones show a 3-day span, not the full week
  const weekStart = addDays(startOfWeek(anchor), weekOffset) // rolling window (offset in days)
  const dayCols = view === 'day' ? [anchor] : view === 'week' ? Array.from({ length: weekDays }, (_, i) => addDays(weekStart, i)) : []
  // All sessions whose [departure, return] span intersects the visible window
  // (so a multi-day session that started earlier still shows on the days it
  // covers here). TimeGrid slices each into the per-day segments it renders.
  const rangeStart = dayCols.length ? keyOf(dayCols[0]) : ''
  const rangeEnd = dayCols.length ? keyOf(dayCols[dayCols.length - 1]) : ''
  const events: TimeGridEvent[] = view === 'month'
    ? []
    : Array.from(byDay.values()).flat().flatMap((c): TimeGridEvent[] => {
        const dep = dayKeyOf(c.departure_datetime)
        const retKey = naiveDate(c.return_datetime) ? dayKeyOf(c.return_datetime) : undefined
        const spanEnd = retKey && retKey > dep ? retKey : dep
        if (dep > rangeEnd || spanEnd < rangeStart) return [] // outside the visible window
        return [{
          id: c.id,
          dayKey: dep,
          endDayKey: retKey, // multi-day span (return day)
          startMin: minsOfDay(c.departure_datetime),
          endMin: minsOfDay(c.return_datetime),
          color: carColor(c.vin), // colour by car
          groupKey: c.vin || undefined, // same-car overlap (interlaced) detection
          title: c.client_name || (c.client_id != null ? `Client #${c.client_id}` : '—'),
          subtitle: vehicleName(c.vin ? vinVehicle.get(c.vin) : undefined, c.vin),
          meta: c.vin ? `VIN: ...${c.vin.slice(-6)}` : undefined, // last 6 of the VIN
          draggable: sessionStatus(c).key === 'planificat', // only planned sessions reschedule
        }]
      })

  // Period label (day/week/month).
  let periodLabel: string
  if (view === 'day') {
    periodLabel = anchor.toLocaleDateString('ro-RO', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })
  } else if (view === 'week') {
    const we = addDays(weekStart, weekDays - 1)
    const weM = we.toLocaleDateString('ro-RO', { month: 'long' })
    periodLabel = weekStart.getMonth() === we.getMonth()
      ? `${weekStart.getDate()} – ${we.getDate()} ${weM}`
      : `${weekStart.getDate()} ${weekStart.toLocaleDateString('ro-RO', { month: 'long' })} – ${we.getDate()} ${weM}`
  } else {
    periodLabel = anchor.toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })
  }

  // Month grid (6 weeks) + selected-day.
  const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const gridStart = startOfWeek(monthStart)
  const monthCells = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const monthActiveKey = picked ?? (monthCells.some((d) => keyOf(d) === todayKey) ? todayKey : keyOf(monthStart))

  return (
    <div className="space-y-3">
      {/* iOS view switcher (≥44px tall) */}
      <div className="flex h-11 gap-0.5 rounded-xl bg-muted p-1">
        {([['day', 'Zi'], ['week', 'Săptămână'], ['month', 'Lună']] as const).map(([v, label]) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={cn('flex-1 rounded-lg text-sm font-medium transition-colors', view === v ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Period navigation (≥44px tap targets) */}
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => go(-1)} aria-label="Perioada anterioară" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-muted transition-colors hover:bg-muted/70"><ChevronLeft className="h-5 w-5" /></button>
        <p className="flex-1 text-center text-sm font-semibold capitalize">{periodLabel}</p>
        <button type="button" onClick={() => go(1)} aria-label="Perioada următoare" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-muted transition-colors hover:bg-muted/70"><ChevronRight className="h-5 w-5" /></button>
        <button type="button" onClick={goToday} className="h-11 shrink-0 rounded-full bg-muted px-4 text-sm font-semibold transition-colors hover:bg-muted/70">Azi</button>
      </div>

      {isLoading ? (
        <div className="space-y-2.5">{[...Array(3)].map((_, i) => <div key={i} className="h-16 animate-pulse rounded-2xl bg-muted" />)}</div>
      ) : isError ? (
        <p className="py-8 text-center text-sm text-destructive">Nu s-a putut încărca calendarul.</p>
      ) : view === 'month' ? (
        // Desktop: calendar (≤600px) and the selected day's sessions sit side by
        // side on one line; phones stack them.
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
          <div className="w-full rounded-2xl border border-border/60 bg-card p-2 lg:max-w-[600px]">
            <div className="grid grid-cols-7">
              {WEEKDAY_LABELS.map((w) => <div key={w} className="py-1 text-center text-[10px] font-semibold text-muted-foreground">{w}</div>)}
              {monthCells.map((d) => {
                const k = keyOf(d)
                const inMonth = d.getMonth() === anchor.getMonth()
                const count = byDay.get(k)?.length ?? 0
                const weekend = d.getDay() === 0 || d.getDay() === 6
                return (
                  <button
                    key={k}
                    type="button"
                    data-testid={`dc-day-${k}`}
                    onClick={() => setPicked(k)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => { e.preventDefault(); const id = Number(e.dataTransfer.getData('text/plain')); if (id) rescheduleToDay(id, k) }}
                    // Drag across cells → a multi-day session (default 09:00–18:00);
                    // a plain click still selects the day (via onClick).
                    onPointerDown={(e) => { if (e.button !== 0 && e.pointerType === 'mouse') return; setMonthDrag({ a: k, b: k }) }}
                    onPointerEnter={() => setMonthDrag((md) => (md ? { ...md, b: k } : md))}
                    onPointerUp={() => {
                      const r = monthRange
                      setMonthDrag(null)
                      if (r && r[0] !== r[1]) onAdd(`${r[0]}T09:00`, `${r[1]}T18:00`)
                    }}
                    className={cn(
                      'relative flex aspect-square flex-col items-center justify-center rounded-lg text-sm',
                      weekend && 'bg-zinc-200/40 dark:bg-red-950/25',
                      !inMonth && 'text-muted-foreground/40',
                      inMonthRange(k) && 'bg-primary/25',
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
          <div className="w-full rounded-2xl border border-border/60 bg-card p-3 lg:flex-1">
            <DayGroup label={dayLabel(monthActiveKey)} items={byDay.get(monthActiveKey) ?? []} vinVehicle={vinVehicle} onOpen={openContract} emptyText="Nicio sesiune în această zi" />
          </div>
        </div>
      ) : (
        <>
          {moveErr && <p className="px-1 text-xs text-destructive">{moveErr}</p>}
          {/* Day view stacks 4 lines (time / client / car / VIN) per card, so it
              needs taller hourly slots than the compact week bars. */}
          <TimeGrid dayCols={dayCols} events={events} onEventClick={openById} onSlotAdd={onAdd} onMove={onMove} pxPerHour={view === 'day' ? 112 : undefined} />
        </>
      )}

      {detail && (
        <SessionDetailModal
          session={detail}
          vehicle={detail.vin ? vinVehicle.get(detail.vin) : undefined}
          onClose={() => setDetail(null)}
          onActivate={() => { const { id } = detail; setDetail(null); onActivate(id) }}
          onReturn={() => { const { id } = detail; setDetail(null); onReturn(id) }}
        />
      )}
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
  const planned = ss.key === 'planificat'
  const tester = c.client_name || (c.client_id != null ? `Client #${c.client_id}` : '—')
  return (
    <button
      type="button"
      draggable={planned}
      onDragStart={(e) => { e.dataTransfer.setData('text/plain', String(c.id)); e.dataTransfer.effectAllowed = 'move' }}
      onClick={onOpen}
      title={planned ? 'Trage pe o zi din calendar pentru a reprograma' : undefined}
      className={cn('flex w-full items-center gap-3 rounded-2xl border border-border/60 bg-card p-3.5 text-left shadow-sm transition-transform active:scale-[0.99]', planned && 'cursor-grab')}
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
          <span className="truncate">{vehicleName(vehicle, c.vin)}</span>
        </div>
      </div>
    </button>
  )
}
