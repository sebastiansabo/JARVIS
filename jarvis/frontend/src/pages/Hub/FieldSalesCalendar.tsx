import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { cn, usePersistedState } from '@/lib/utils'
import { fieldSalesApi, type FSVisit } from '@/api/fieldSales'
import { STATUS_CONFIG, VISIT_TYPE_LABELS } from '@/pages/Hub/HubFieldSalesPanel'

type CalView = 'month' | 'week' | 'day'
const VIEW_OPTIONS: readonly [CalView, string][] = [['month', 'Lună'], ['week', 'Săptămână'], ['day', 'Zi']]
const WEEKDAY_LABELS = ['Lu', 'Ma', 'Mi', 'Jo', 'Vi', 'Sâ', 'Du']
const pad = (n: number) => String(n).padStart(2, '0')

function keyOf(d: Date): string { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
function addDays(d: Date, n: number): Date { const x = new Date(d); x.setDate(x.getDate() + n); return x }
function addMonths(d: Date, n: number): Date { const x = new Date(d); x.setDate(1); x.setMonth(x.getMonth() + n); return x }
function startOfWeek(d: Date): Date { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x }
// FSVisit.planned_date is already a plain "YYYY-MM-DD" string (date-only, no
// time component), so grouping needs no Date parsing/timezone handling —
// unlike DrivingCalendar's dayKeyOf, which parses a timestamptz value via
// naiveDate.
function dayKeyOf(dateStr?: string | null): string { return dateStr ? dateStr.slice(0, 10) : 'unknown' }
function dayLabel(key: string): string {
  return new Date(`${key}T00:00:00`).toLocaleDateString('ro-RO', { weekday: 'long', day: '2-digit', month: 'long' })
}

// --- Time-grid geometry (Week/Day views) ------------------------------------
// Visible window is a fixed 07:00–21:00 at 48px/hour; slot clicks snap to
// 30-minute increments. `toMin` must tolerate the backend's TIME column
// serializing as either "HH:MM" or "HH:MM:SS" — split on ':' and only read
// the first two segments.
const HOUR_START = 7
const HOUR_END = 21
const PX_PER_HOUR = 48
const SNAP_MIN = 30
function toMin(t?: string | null): number | null {
  if (!t) return null
  const [h, m] = t.split(':')
  return Number(h) * 60 + Number(m)
}
function minToTime(min: number): string { return `${pad(Math.floor(min / 60))}:${pad(min % 60)}` }
function snap(min: number): number { return Math.round(min / SNAP_MIN) * SNAP_MIN }
function yToMin(y: number): number { return snap(HOUR_START * 60 + (y / PX_PER_HOUR) * 60) }
function minToY(min: number): number { return ((min - HOUR_START * 60) / 60) * PX_PER_HOUR }
function addHour(t: string): string { return minToTime(Math.min(toMin(t)! + 60, HOUR_END * 60)) }

/**
 * Calendar for the Hub Field Sales panel — a web port of DrivingCalendar's
 * view switcher + month grid (the foiParcurs vehicle join is dropped; visits
 * carry everything needed for display already). Shows the signed-in KAM's
 * own visits (fieldSalesApi.getMyVisits) grouped by planned_date; tapping a
 * listed visit opens the shared detail overlay via `onOpen`. Week/Day render
 * a 07:00–21:00 time-grid (see the geometry helpers above) with slot-click-
 * to-add and block-click-to-open; dragging to create/move/resize visits is a
 * follow-up task.
 */
export default function FieldSalesCalendar({ onOpen, onAdd }: {
  onOpen: (visitId: number) => void
  onAdd: (date: string, time?: string, endTime?: string) => void
}) {
  const [view, setView] = usePersistedState<CalView>('hub-fs-cal-view', 'month')
  const [anchor, setAnchor] = useState<Date>(() => new Date())
  const [picked, setPicked] = useState<string | null>(null)

  const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const gridStart = startOfWeek(monthStart)
  const gridStartKey = keyOf(gridStart)
  const monthCells = useMemo(() => Array.from({ length: 42 }, (_, i) => addDays(gridStart, i)), [gridStartKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const weekStart = startOfWeek(anchor)
  const dayCols = view === 'day' ? [anchor] : Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))

  // Visible-range bounds for the active view — month keeps its existing
  // 42-cell grid window, week/day narrow the fetch to just what's rendered.
  const rangeStart = view === 'week' ? weekStart : view === 'day' ? anchor : gridStart
  const rangeEnd = view === 'week' ? addDays(weekStart, 6) : view === 'day' ? anchor : addDays(gridStart, 41)
  const rangeStartKey = keyOf(rangeStart)
  const rangeEndKey = keyOf(rangeEnd)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['field-sales-cal', view, rangeStartKey],
    queryFn: () => fieldSalesApi.getMyVisits(rangeStartKey, rangeEndKey),
  })

  const byDay = useMemo(() => {
    const map = new Map<string, FSVisit[]>()
    for (const v of data?.visits ?? []) {
      const key = dayKeyOf(v.planned_date)
      const list = map.get(key) ?? []
      list.push(v)
      map.set(key, list)
    }
    for (const list of map.values()) list.sort((a, b) => (a.planned_time || '').localeCompare(b.planned_time || ''))
    return map
  }, [data])

  const todayKey = keyOf(new Date())
  const activeKey = picked ?? (monthCells.some((d) => keyOf(d) === todayKey) ? todayKey : keyOf(monthStart))
  const activeVisits = byDay.get(activeKey) ?? []

  const go = (dir: 1 | -1) => {
    setAnchor((a) => (view === 'day' ? addDays(a, dir) : view === 'week' ? addDays(a, 7 * dir) : addMonths(a, dir)))
    setPicked(null)
  }
  const goToday = () => { setAnchor(new Date()); setPicked(null) }

  let periodLabel: string
  if (view === 'day') {
    periodLabel = anchor.toLocaleDateString('ro-RO', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })
  } else if (view === 'week') {
    const weekEnd = addDays(weekStart, 6)
    const endMonth = weekEnd.toLocaleDateString('ro-RO', { month: 'long' })
    periodLabel = weekStart.getMonth() === weekEnd.getMonth()
      ? `${weekStart.getDate()} – ${weekEnd.getDate()} ${endMonth}`
      : `${weekStart.getDate()} ${weekStart.toLocaleDateString('ro-RO', { month: 'long' })} – ${weekEnd.getDate()} ${endMonth}`
  } else {
    periodLabel = anchor.toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })
  }

  return (
    <div className="space-y-3">
      {/* View switcher */}
      <div className="flex h-9 gap-0.5 rounded-lg bg-muted p-0.5">
        {VIEW_OPTIONS.map(([v, label]) => (
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
      ) : view !== 'month' ? (
        <FSTimeGrid dayCols={dayCols} byDay={byDay} onOpen={onOpen} onAdd={onAdd} />
      ) : (
        <>
          <div className="overflow-x-auto">
            <div className="min-w-[280px] rounded-2xl border border-border/60 bg-card p-2">
              <div className="grid grid-cols-7">
                {WEEKDAY_LABELS.map((w) => <div key={w} className="py-1 text-center text-[10px] font-semibold text-muted-foreground">{w}</div>)}
                {monthCells.map((d) => {
                  const k = keyOf(d)
                  const inMonth = d.getMonth() === anchor.getMonth()
                  const dayVisits = byDay.get(k) ?? []
                  return (
                    <div
                      key={k}
                      data-testid={`day-${k}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => setPicked(k)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setPicked(k) } }}
                      className={cn(
                        'group relative flex aspect-square min-w-0 cursor-pointer flex-col items-center justify-center gap-0.5 rounded-lg text-sm',
                        !inMonth && 'text-muted-foreground/40',
                        k === activeKey && 'bg-primary/15 font-bold',
                        k === todayKey && 'ring-1 ring-primary',
                      )}
                    >
                      {d.getDate()}
                      {dayVisits.length > 0 && (
                        dayVisits.length > 3 ? (
                          <span data-testid="day-dot" className="text-[9px] font-bold text-primary">{dayVisits.length}</span>
                        ) : (
                          <span className="flex items-center gap-0.5">
                            {dayVisits.map((v) => (
                              <span key={v.id} data-testid="day-dot" className={cn('h-1.5 w-1.5 rounded-full', STATUS_CONFIG[v.status]?.dot ?? 'bg-muted-foreground')} />
                            ))}
                          </span>
                        )
                      )}
                      {/* Hover add-affordance — hidden by default, shown on cell
                          hover; stopPropagation so it doesn't also select the day. */}
                      <button
                        type="button"
                        data-testid="day-add"
                        aria-label={`Adaugă rapid ${k}`}
                        onClick={(e) => { e.stopPropagation(); onAdd(k) }}
                        className="absolute right-0.5 top-0.5 hidden h-4 w-4 items-center justify-center rounded-full bg-primary text-primary-foreground group-hover:flex"
                      >
                        <Plus className="h-3 w-3" />
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2 px-1">
              <p className="text-xs font-semibold uppercase capitalize tracking-wide text-muted-foreground">{dayLabel(activeKey)}</p>
              <button
                type="button"
                onClick={() => onAdd(activeKey)}
                className="flex shrink-0 items-center gap-1 rounded-full bg-teal-600 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-teal-700"
              >
                <Plus className="h-3.5 w-3.5" />Adaugă vizită
              </button>
            </div>
            {activeVisits.length === 0 ? (
              <p className="px-1 py-4 text-center text-sm text-muted-foreground">Nicio vizita in aceasta zi</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {activeVisits.map((v) => <CalendarVisitRow key={v.id} visit={v} onOpen={() => onOpen(v.id)} />)}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// Compact row for the selected day's visit list. Reuses STATUS_CONFIG /
// VISIT_TYPE_LABELS from the panel instead of a full VisitCard, since the
// calendar has no check-in/finalize mutations wired up (that stays the Azi
// tab's job) and a card with dead action buttons would be confusing here.
function CalendarVisitRow({ visit, onOpen }: { visit: FSVisit; onOpen: () => void }) {
  const cfg = STATUS_CONFIG[visit.status] ?? STATUS_CONFIG.planned
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-2xl border border-border/60 bg-card p-3.5 text-left shadow-sm transition-transform active:scale-[0.99]"
    >
      <div className="flex h-9 w-11 shrink-0 items-center justify-center rounded-xl bg-muted">
        <span className="text-[11px] font-bold leading-none tabular-nums">{visit.planned_time ? visit.planned_time.slice(0, 5) : '—'}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[15px] font-semibold">{visit.client_name}</span>
          <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide', cfg.bg, cfg.text)}>{cfg.label}</span>
        </div>
        <p className="mt-0.5 truncate text-[13px] text-muted-foreground">{VISIT_TYPE_LABELS[visit.visit_type] ?? visit.visit_type}</p>
      </div>
    </button>
  )
}

// Week/Day time-grid — a fixed 07:00–21:00 window (see the geometry helpers
// above) with one day column per `dayCols` entry (7 for week, 1 for day) and
// an hour gutter on the left. Each column shows a "Fără oră" strip for
// visits with no planned_time, then an hour-lined grid with absolutely
// positioned blocks for timed visits. Clicking a block opens it; clicking
// empty grid space computes the clicked time (snapped to 30 min) and
// proposes a 1h visit via onAdd. No drag yet — that's a follow-up task.
function FSTimeGrid({ dayCols, byDay, onOpen, onAdd }: {
  dayCols: Date[]
  byDay: Map<string, FSVisit[]>
  onOpen: (visitId: number) => void
  onAdd: (date: string, time?: string, endTime?: string) => void
}) {
  const hours = Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, i) => HOUR_START + i)
  const gridHeight = (HOUR_END - HOUR_START) * PX_PER_HOUR
  const todayKey = keyOf(new Date())

  return (
    <div className="overflow-x-auto">
      <div className="flex min-w-[560px] gap-1 rounded-2xl border border-border/60 bg-card p-2">
        {/* hour gutter — invisible header spacers keep hour rows aligned with
            each column's grid start regardless of its "Fără oră" strip. */}
        <div className="w-10 shrink-0">
          <p className="invisible mb-1 truncate text-center text-[10px] font-semibold uppercase">00</p>
          <p className="invisible text-[9px] font-semibold uppercase tracking-wide">Fără oră</p>
          {hours.map((h) => (
            <div key={h} className="relative" style={{ height: PX_PER_HOUR }}>
              <span className="absolute -top-2 right-1 text-[10px] font-medium text-muted-foreground">{`${pad(h)}:00`}</span>
            </div>
          ))}
        </div>

        {/* day columns */}
        <div className={cn('grid flex-1 gap-1', dayCols.length > 1 ? 'grid-cols-7' : 'grid-cols-1')}>
          {dayCols.map((d) => {
            const dk = keyOf(d)
            const visits = byDay.get(dk) ?? []
            const timed = visits.filter((v) => v.planned_time)
            const untimed = visits.filter((v) => !v.planned_time)
            return (
              <div key={dk} className="min-w-0">
                <p className={cn('mb-1 truncate text-center text-[10px] font-semibold uppercase text-muted-foreground', dk === todayKey && 'text-primary')}>
                  {d.toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit' })}
                </p>
                <p className={cn('text-[9px] font-semibold uppercase tracking-wide text-muted-foreground', untimed.length === 0 && 'invisible')}>Fără oră</p>
                <div className="mb-0.5 space-y-0.5">
                  {untimed.map((v) => {
                    const cfg = STATUS_CONFIG[v.status] ?? STATUS_CONFIG.planned
                    return (
                      <button
                        key={v.id}
                        type="button"
                        data-testid={`fs-block-${v.id}`}
                        onClick={() => onOpen(v.id)}
                        className={cn('block w-full truncate rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold', cfg.bg, cfg.text)}
                      >
                        {v.client_name}
                      </button>
                    )
                  })}
                </div>
                <div
                  data-testid={`fs-col-${dk}`}
                  className="relative cursor-pointer rounded-lg bg-muted/30"
                  style={{ height: gridHeight }}
                  onClick={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect()
                    const startMin = yToMin(e.clientY - rect.top)
                    onAdd(dk, minToTime(startMin), minToTime(startMin + 60))
                  }}
                >
                  {hours.slice(0, -1).map((h) => (
                    <div key={h} className="absolute inset-x-0 border-t border-border/30" style={{ top: minToY(h * 60) }} />
                  ))}
                  {timed.map((v) => {
                    const start = v.planned_time!
                    const top = minToY(toMin(start)!)
                    const endStr = v.planned_end_time ?? addHour(start)
                    const height = Math.max(minToY(toMin(endStr)!) - top, 18)
                    const cfg = STATUS_CONFIG[v.status] ?? STATUS_CONFIG.planned
                    return (
                      <button
                        key={v.id}
                        type="button"
                        data-testid={`fs-block-${v.id}`}
                        onClick={(e) => { e.stopPropagation(); onOpen(v.id) }}
                        style={{ top, height }}
                        className={cn('absolute left-0.5 right-0.5 overflow-hidden rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold leading-tight shadow-sm', cfg.bg, cfg.text)}
                      >
                        <span className="block truncate">{`${start.slice(0, 5)} ${v.client_name}`}</span>
                        <span className="block truncate text-[9px] font-normal opacity-80">{VISIT_TYPE_LABELS[v.visit_type] ?? v.visit_type}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
