import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { cn, usePersistedState } from '@/lib/utils'
import { fieldSalesApi, type FSVisit, type VisitUpdatePayload } from '@/api/fieldSales'
import { STATUS_CONFIG, VISIT_TYPE_LABELS } from '@/pages/Hub/HubFieldSalesPanel'

type CalView = 'month' | 'week' | 'day'
// Cache shape of fieldSalesApi.getMyVisits — used to type the optimistic
// cache read/write in FSTimeGrid's move/resize mutation below.
type MyVisitsResp = { success: boolean; visits: FSVisit[]; date_from: string; date_to: string }
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
// Pointer movement (px, either axis) below which a press-and-release on a
// block body or its resize handle is treated as a click/no-op rather than a
// drag — see FSTimeGrid's move/resize pointer handlers.
const DRAG_THRESHOLD_PX = 4
function toMin(t?: string | null): number | null {
  if (!t) return null
  const [h, m] = t.split(':')
  return Number(h) * 60 + Number(m)
}
function minToTime(min: number): string { return `${pad(Math.floor(min / 60))}:${pad(min % 60)}` }
function snap(min: number): number { return Math.round(min / SNAP_MIN) * SNAP_MIN }
function yToMin(y: number): number { return snap(HOUR_START * 60 + (y / PX_PER_HOUR) * 60) }
function minToY(min: number): number { return ((min - HOUR_START * 60) / 60) * PX_PER_HOUR }
// Clamp a minutes-of-day value into the visible grid window. Needed because a
// captured pointer keeps reporting coordinates after it leaves the column
// (setPointerCapture), so a drag above/below the grid otherwise yields
// negative or past-21:00 minutes → malformed times like "-2:-30" / "28:00".
function clampMin(min: number): number { return Math.max(HOUR_START * 60, Math.min(HOUR_END * 60, min)) }
function addHour(t: string): string { return minToTime(Math.min(toMin(t)! + 60, HOUR_END * 60)) }

/**
 * Calendar for the Hub Field Sales panel — a web port of DrivingCalendar's
 * view switcher + month grid (the foiParcurs vehicle join is dropped; visits
 * carry everything needed for display already). Shows the signed-in KAM's
 * own visits (fieldSalesApi.getMyVisits) grouped by planned_date; tapping a
 * listed visit opens the shared detail overlay via `onOpen`. Week/Day render
 * a 07:00–21:00 time-grid (see the geometry helpers above) with slot-click-
 * or drag-to-add, block-click-to-open, and drag-to-move/resize of existing
 * visits (persisted via `fieldSalesApi.updateVisit`, optimistic-cached).
 */
export default function FieldSalesCalendar({ onOpen, onAdd, companyId }: {
  onOpen: (visitId: number) => void
  onAdd: (date: string, time?: string, endTime?: string) => void
  companyId?: number
}) {
  const [view, setView] = usePersistedState<CalView>('hub-fs-cal-view', 'month')
  const [anchor, setAnchor] = useState<Date>(() => new Date())
  const [picked, setPicked] = useState<string | null>(null)
  // Add is only offered once a company is resolved — mirrors the Azi tab's
  // `companyId > 0` gate so a no-company user can't open a dead AddVisitForm
  // from any calendar view (the form's client search is disabled without a
  // company anyway, but the entry point shouldn't dangle). Own visits still
  // render — getMyVisits is KAM-scoped, not a cross-tenant read.
  const canAdd = (companyId ?? 0) > 0

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

  // Named so FSTimeGrid's move/resize mutation can target the exact same
  // (active) cache entry for its optimistic update/rollback.
  const calQueryKey = ['field-sales-cal', view, rangeStartKey, companyId] as const
  const { data, isLoading, isError } = useQuery({
    queryKey: calQueryKey,
    queryFn: () => fieldSalesApi.getMyVisits(rangeStartKey, rangeEndKey, companyId),
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
        <FSTimeGrid dayCols={dayCols} byDay={byDay} onOpen={onOpen} onAdd={onAdd} canAdd={canAdd} queryKey={calQueryKey} />
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
                          hover; stopPropagation so it doesn't also select the day.
                          Suppressed entirely without a resolved company (canAdd). */}
                      {canAdd && (
                        <button
                          type="button"
                          data-testid="day-add"
                          aria-label={`Adaugă rapid ${k}`}
                          onClick={(e) => { e.stopPropagation(); onAdd(k) }}
                          className="absolute right-0.5 top-0.5 hidden h-4 w-4 items-center justify-center rounded-full bg-primary text-primary-foreground group-hover:flex"
                        >
                          <Plus className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2 px-1">
              <p className="text-xs font-semibold uppercase capitalize tracking-wide text-muted-foreground">{dayLabel(activeKey)}</p>
              {canAdd && (
                <button
                  type="button"
                  onClick={() => onAdd(activeKey)}
                  className="flex shrink-0 items-center gap-1 rounded-full bg-teal-600 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-teal-700"
                >
                  <Plus className="h-3.5 w-3.5" />Adaugă vizită
                </button>
              )}
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

// Drag state for FSTimeGrid's three interaction modes: 'create' (empty-grid
// drag/click → onAdd, unchanged from Task 6), 'move' (drag a block body to a
// new start time, duration preserved), and 'resize' (drag a block's bottom
// edge to a new end time). 'move'/'resize' carry RAW pointer clientX/clientY
// (not column-relative) at drag start (x0/y0) and live (x1/y1) — only the
// MOVEMENT (delta) is needed for the math, and a screen-space delta equals a
// column-space delta (the column doesn't resize/scroll mid-drag), so no
// column-rect lookup is needed for the core vertical calculation.
type CreateDrag = { mode: 'create'; col: string; y0: number; y1: number }
type MoveDrag = { mode: 'move'; visit: FSVisit; col: string; x0: number; y0: number; x1: number; y1: number }
type ResizeDrag = { mode: 'resize'; visit: FSVisit; col: string; y0: number; y1: number }
type DragState = CreateDrag | MoveDrag | ResizeDrag

// Week/Day time-grid — a fixed 07:00–21:00 window (see the geometry helpers
// above) with one day column per `dayCols` entry (7 for week, 1 for day) and
// an hour gutter on the left. Untimed visits (no planned_time) live in a
// SHARED all-day band spanning gutter + every column in one flex row, so the
// hour-grid below always starts at the same Y for the gutter and every column
// regardless of how many untimed visits any single day has (a per-column
// strip would push that column's hour lines/blocks down, breaking cross-
// column alignment). The band is omitted entirely when no visible day has an
// untimed visit. Empty grid space supports both a plain click (proposes a 1h
// visit at the clicked time) and a pointer-drag (proposes a visit spanning
// the dragged range, snapped to 30 min) via a single pointerdown/move/up flow
// on the COLUMN — mode 'create' in the `drag` state below.
//
// Existing blocks support two more drag modes, both persisted through
// `fieldSalesApi.updateVisit` via the `updateMut` optimistic mutation below:
// pressing a block's BODY starts mode 'move' (drags the whole visit to a new
// start time, duration preserved; switching day columns in week view is a
// best-effort pointer-x heuristic gated on a measurable column width, so it
// degrades to "stay on the same day" rather than guessing). Pressing the
// thin strip at a block's BOTTOM edge starts mode 'resize' (drags only the
// end time). Both distinguish a real drag from a plain click/tap by a
// >DRAG_THRESHOLD_PX pointer-movement threshold: below it, releasing on the
// block body calls `onOpen` (same as a plain click) instead of persisting;
// releasing on the resize handle below the threshold is a no-op.
//
// All block/handle pointer handlers stopPropagation (down/move/up/cancel) so
// they never bubble up into the column's create-mode handlers, AND the
// column's create-mode handlers separately gate on `drag.mode === 'create'`
// — belt and suspenders, since jsdom (no real hit-testing/pointer-capture
// redirection) still bubbles a captured element's events through the DOM as
// usual, unlike a real browser which would route them straight to the
// capturing element.
function FSTimeGrid({ dayCols, byDay, onOpen, onAdd, canAdd, queryKey }: {
  dayCols: Date[]
  byDay: Map<string, FSVisit[]>
  onOpen: (visitId: number) => void
  onAdd: (date: string, time?: string, endTime?: string) => void
  canAdd: boolean
  queryKey: readonly [string, CalView, string, number | undefined]
}) {
  const queryClient = useQueryClient()
  const [drag, setDrag] = useState<DragState | null>(null)
  // Suppresses one native "click" that might immediately follow a pointer-
  // resolved open (sub-threshold pointerup on a block body) or any
  // resize-handle release, so a real browser's own synthesized click (which
  // the pointer flow already acted on) can't re-trigger onOpen a second
  // time. jsdom's fireEvent never auto-synthesizes that follow-on click, so
  // this isn't exercised by the test suite, but it matters for real
  // pointer/mouse input.
  const suppressClickRef = useRef<number | null>(null)
  const [dragErr, setDragErr] = useState<string | null>(null)
  // Column DOM refs, keyed by day key. Used only for the best-effort
  // day-switch-by-pointer-x heuristic on move (see the block's onPointerUp);
  // every other geometry calculation here is delta-based and needs no rect.
  const colRefs = useRef<Record<string, HTMLDivElement | null>>({})

  const updateMut = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: VisitUpdatePayload; queryKey: readonly [string, CalView, string, number | undefined] }) => fieldSalesApi.updateVisit(id, patch),
    // `queryKey` travels in the mutation VARIABLES (not the closed-over prop)
    // because TanStack Query v5 re-reads the latest render's option closures
    // at execute time — if the user switches view/date-range while a PUT is
    // in flight, a closure-captured `queryKey` would target the now-active
    // (wrong) cache entry for rollback/patch instead of the one the drag
    // actually started against.
    onMutate: async ({ id, patch, queryKey: qk }) => {
      // Cancel in-flight refetches of the active view so they can't clobber
      // the optimistic write below with stale (pre-drag) data.
      await queryClient.cancelQueries({ queryKey: qk })
      const prev = queryClient.getQueryData<MyVisitsResp>(qk)
      if (prev) {
        queryClient.setQueryData<MyVisitsResp>(qk, {
          ...prev,
          visits: prev.visits.map((v) => (v.id === id ? { ...v, ...patch } : v)),
        })
      }
      return { prev }
    },
    onError: (err, vars, context) => {
      if (context?.prev) queryClient.setQueryData(vars.queryKey, context.prev)
      setDragErr((err as { data?: { error?: string } })?.data?.error ?? 'Eroare la actualizarea vizitei')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['field-sales-visits'] })
      queryClient.invalidateQueries({ queryKey: ['field-sales-mine'] })
      queryClient.invalidateQueries({ queryKey: ['field-sales-cal'] })
    },
  })

  const hours = Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, i) => HOUR_START + i)
  const gridHeight = (HOUR_END - HOUR_START) * PX_PER_HOUR
  const todayKey = keyOf(new Date())
  const gridColsClass = dayCols.length > 1 ? 'grid-cols-7' : 'grid-cols-1'

  const cols = dayCols.map((d) => {
    const dk = keyOf(d)
    const visits = byDay.get(dk) ?? []
    return { d, dk, timed: visits.filter((v) => v.planned_time), untimed: visits.filter((v) => !v.planned_time) }
  })
  const hasAnyUntimed = cols.some((c) => c.untimed.length > 0)

  return (
    <div className="overflow-x-auto">
      <div className="flex min-w-[560px] flex-col gap-1 rounded-2xl border border-border/60 bg-card p-2">
        {/* Day-label header row (gutter spacer + one label per column). */}
        <div className="flex gap-1">
          <div className="w-10 shrink-0" />
          <div className={cn('grid flex-1 gap-1', gridColsClass)}>
            {cols.map(({ d, dk }) => (
              <p key={dk} className={cn('truncate text-center text-[10px] font-semibold uppercase text-muted-foreground', dk === todayKey && 'text-primary')}>
                {d.toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit' })}
              </p>
            ))}
          </div>
        </div>

        {/* Shared all-day band — one flex row (gutter label + a cell per
            column) so every cell shares a uniform height; rendered only when
            some visible day has an untimed visit. */}
        {hasAnyUntimed && (
          <div data-testid="fs-allday-band" className="flex gap-1">
            <div className="flex w-10 shrink-0 items-start justify-end pr-1 pt-0.5">
              <span className="text-[9px] font-semibold uppercase leading-tight tracking-wide text-muted-foreground">Fără oră</span>
            </div>
            <div className={cn('grid flex-1 gap-1', gridColsClass)}>
              {cols.map(({ dk, untimed }) => (
                <div key={dk} className="min-w-0 space-y-0.5">
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
              ))}
            </div>
          </div>
        )}

        {/* Hour-grid — gutter labels + one relative day column each. All
            columns share the same fixed gridHeight and start at the same Y. */}
        <div data-testid="fs-hourgrid" className="flex gap-1">
          <div className="w-10 shrink-0">
            {hours.map((h) => (
              <div key={h} className="relative" style={{ height: PX_PER_HOUR }}>
                <span className="absolute -top-2 right-1 text-[10px] font-medium text-muted-foreground">{`${pad(h)}:00`}</span>
              </div>
            ))}
          </div>
          <div className={cn('grid flex-1 gap-1', gridColsClass)}>
            {cols.map(({ dk, timed }) => {
              const dragging = drag?.mode === 'create' && drag.col === dk
              // Selection rectangle geometry: both endpoints are re-quantized
              // through yToMin (which snaps to 30 min) → clampMin (kept inside
              // the visible window even when the captured pointer is dragged
              // off the column) → minToY, so the live rectangle always aligns
              // to a snap line inside the grid and matches what pointerup will
              // create.
              const selTop = dragging ? minToY(clampMin(yToMin(Math.min(drag!.y0, drag!.y1)))) : 0
              const selBottom = dragging ? minToY(clampMin(yToMin(Math.max(drag!.y0, drag!.y1)))) : 0
              return (
                <div
                  key={dk}
                  data-testid={`fs-col-${dk}`}
                  ref={(el) => { colRefs.current[dk] = el }}
                  // touch-action:none only on the actively-dragging column, so
                  // idle columns keep normal touch-scroll (tap-to-add still
                  // works; touch drag-to-create may compete with scroll, but
                  // tap is the touch primary — intended trade-off).
                  className={cn('relative min-w-0 cursor-pointer rounded-lg bg-muted/30', dragging && 'touch-none')}
                  style={{ height: gridHeight }}
                  onPointerDown={(e) => {
                    // No resolved company → the create/add path is closed (the
                    // add entry points are hidden too); don't start a create
                    // drag that could only open a dead, unscoped AddVisitForm.
                    if (!canAdd) return
                    // Ignore non-primary mouse buttons (right/middle) so they
                    // don't start a drag/create; touch/pen primary contact has
                    // button === 0 and passes through.
                    if (e.button !== 0 && e.pointerType === 'mouse') return
                    const rect = e.currentTarget.getBoundingClientRect()
                    const y0 = e.clientY - rect.top
                    e.currentTarget.setPointerCapture(e.pointerId)
                    setDrag({ mode: 'create', col: dk, y0, y1: y0 })
                  }}
                  onPointerMove={(e) => {
                    if (!drag || drag.mode !== 'create' || drag.col !== dk) return
                    const rect = e.currentTarget.getBoundingClientRect()
                    setDrag({ mode: 'create', col: dk, y0: drag.y0, y1: e.clientY - rect.top })
                  }}
                  onPointerUp={(e) => {
                    if (!drag || drag.mode !== 'create' || drag.col !== dk) return
                    e.currentTarget.releasePointerCapture(e.pointerId)
                    const a = clampMin(yToMin(Math.min(drag.y0, drag.y1)))
                    let b = clampMin(yToMin(Math.max(drag.y0, drag.y1)))
                    // Plain click (or a sub-snap drag): default to a 1h visit.
                    if (b - a < SNAP_MIN) b = clampMin(a + 60)
                    // If clamping collapsed the range against 21:00 (a click at
                    // the very bottom), pull the start back so a 1h slot fits.
                    let startMin = a
                    if (b - startMin < SNAP_MIN) startMin = clampMin(b - 60)
                    setDrag(null)
                    onAdd(dk, minToTime(startMin), minToTime(b))
                  }}
                  onPointerCancel={(e) => {
                    // An interrupted gesture (app switch / system gesture)
                    // must not leave a stuck selection rectangle.
                    if (!drag || drag.mode !== 'create' || drag.col !== dk) return
                    if (e.currentTarget.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
                    setDrag(null)
                  }}
                >
                  {hours.slice(0, -1).map((h) => (
                    <div key={h} className="absolute inset-x-0 border-t border-border/30" style={{ top: minToY(h * 60) }} />
                  ))}
                  {dragging && (
                    <div
                      data-testid="fs-drag-selection"
                      className="pointer-events-none absolute inset-x-0.5 rounded-md border border-primary/50 bg-primary/20"
                      style={{ top: selTop, height: Math.max(selBottom - selTop, 4) }}
                    />
                  )}
                  {timed.map((v) => {
                    const start = v.planned_time!
                    const startMin = toMin(start)!
                    const endStr = v.planned_end_time || addHour(start)
                    const endMin = toMin(endStr)!
                    // ORIGINAL (undragged) geometry — always derived from `v`,
                    // never from `drag`, so onPointerUp below can compute the
                    // final position from a fixed baseline + a delta-from-
                    // drag-start without double-applying an already-live-
                    // previewed offset (the closures here are recreated each
                    // render, including the ones mid-drag).
                    const top = minToY(startMin)
                    const bottomOriginal = minToY(endMin)
                    const movingThis = drag?.mode === 'move' && drag.visit.id === v.id
                    const resizingThis = drag?.mode === 'resize' && drag.visit.id === v.id
                    // Live preview only — never read back into the persisted
                    // calculation.
                    let previewTop = top
                    let previewBottom = bottomOriginal
                    if (movingThis) {
                      const dy = drag.y1 - drag.y0
                      const duration = endMin - startMin
                      const newStart = clampMin(yToMin(top + dy))
                      previewTop = minToY(newStart)
                      previewBottom = minToY(Math.min(newStart + duration, HOUR_END * 60))
                    } else if (resizingThis) {
                      const dy = drag.y1 - drag.y0
                      const newEnd = clampMin(Math.max(startMin + SNAP_MIN, yToMin(bottomOriginal + dy)))
                      previewBottom = minToY(newEnd)
                    }
                    const height = Math.max(previewBottom - previewTop, 18)
                    const cfg = STATUS_CONFIG[v.status] ?? STATUS_CONFIG.planned
                    return (
                      <button
                        key={v.id}
                        type="button"
                        data-testid={`fs-block-${v.id}`}
                        onPointerDown={(e) => {
                          if (e.button !== 0 && e.pointerType === 'mouse') return
                          e.stopPropagation()
                          e.currentTarget.setPointerCapture(e.pointerId)
                          setDragErr(null)
                          setDrag({ mode: 'move', visit: v, col: dk, x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY })
                        }}
                        onPointerMove={(e) => {
                          if (!drag || drag.mode !== 'move' || drag.visit.id !== v.id) return
                          e.stopPropagation()
                          setDrag({ ...drag, x1: e.clientX, y1: e.clientY })
                        }}
                        onPointerUp={(e) => {
                          if (!drag || drag.mode !== 'move' || drag.visit.id !== v.id) return
                          e.stopPropagation()
                          e.currentTarget.releasePointerCapture(e.pointerId)
                          const dx = e.clientX - drag.x0
                          const dy = e.clientY - drag.y0
                          setDrag(null)
                          // Sub-threshold press+release: treat as a click, not
                          // a drag — open the visit instead of persisting.
                          if (Math.abs(dx) <= DRAG_THRESHOLD_PX && Math.abs(dy) <= DRAG_THRESHOLD_PX) {
                            suppressClickRef.current = v.id
                            onOpen(v.id)
                            return
                          }
                          // A completed move-drag must NOT also open the visit:
                          // a real browser fires a native `click` after
                          // mousedown+mouseup on the same element regardless of
                          // movement, and the block tracks the pointer so the
                          // cursor is still over it → onClick would run onOpen
                          // right after the move. Suppress that one click.
                          // (jsdom doesn't synthesize the follow-on click, so
                          // the move test doesn't observe this, but real input
                          // does — mirror the resize handle's unconditional
                          // suppress.)
                          suppressClickRef.current = v.id
                          const duration = endMin - startMin
                          const newStart = clampMin(yToMin(top + dy))
                          const newEnd = Math.min(newStart + duration, HOUR_END * 60)
                          // Best-effort day-switch: only when in week view, and
                          // only if the origin column's width is measurable
                          // (real layout) — otherwise stay on the origin day
                          // rather than guess. dx is 0 for a purely-vertical
                          // drag, so this is a no-op in that (and the tested)
                          // case regardless of column width.
                          let newDayKey = dk
                          if (cols.length > 1) {
                            const originIdx = cols.findIndex((c) => c.dk === dk)
                            const width = colRefs.current[dk]?.getBoundingClientRect().width || 0
                            if (originIdx >= 0 && width > 0) {
                              const newIdx = Math.min(cols.length - 1, Math.max(0, originIdx + Math.round(dx / width)))
                              newDayKey = cols[newIdx].dk
                            }
                          }
                          updateMut.mutate({ id: v.id, patch: { planned_date: newDayKey, planned_time: minToTime(newStart), planned_end_time: minToTime(newEnd) }, queryKey })
                        }}
                        onPointerCancel={(e) => {
                          if (!drag || drag.mode !== 'move' || drag.visit.id !== v.id) return
                          e.stopPropagation()
                          if (e.currentTarget.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
                          setDrag(null)
                        }}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (suppressClickRef.current === v.id) { suppressClickRef.current = null; return }
                          onOpen(v.id)
                        }}
                        style={{ top: previewTop, height }}
                        // touch-none while THIS block is mid-move so a touch
                        // drag isn't hijacked as page-scroll (which would
                        // pointercancel the gesture).
                        className={cn('absolute left-0.5 right-0.5 overflow-hidden rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold leading-tight shadow-sm', cfg.bg, cfg.text, movingThis && 'touch-none')}
                      >
                        <span className="block truncate">{`${start.slice(0, 5)} ${v.client_name}`}</span>
                        <span className="block truncate text-[9px] font-normal opacity-80">{VISIT_TYPE_LABELS[v.visit_type] ?? v.visit_type}</span>
                        {/* Bottom-edge resize handle — stopPropagation keeps a
                            press here from also starting the button's own
                            'move' drag. */}
                        <div
                          data-testid={`fs-resize-${v.id}`}
                          onPointerDown={(e) => {
                            if (e.button !== 0 && e.pointerType === 'mouse') return
                            e.stopPropagation()
                            e.currentTarget.setPointerCapture(e.pointerId)
                            setDragErr(null)
                            setDrag({ mode: 'resize', visit: v, col: dk, y0: e.clientY, y1: e.clientY })
                          }}
                          onPointerMove={(e) => {
                            if (!drag || drag.mode !== 'resize' || drag.visit.id !== v.id) return
                            e.stopPropagation()
                            setDrag({ ...drag, y1: e.clientY })
                          }}
                          onPointerUp={(e) => {
                            if (!drag || drag.mode !== 'resize' || drag.visit.id !== v.id) return
                            e.stopPropagation()
                            e.currentTarget.releasePointerCapture(e.pointerId)
                            const dy = e.clientY - drag.y0
                            setDrag(null)
                            // A resize-handle press never opens the visit.
                            suppressClickRef.current = v.id
                            if (Math.abs(dy) <= DRAG_THRESHOLD_PX) return
                            const newEnd = clampMin(Math.max(startMin + SNAP_MIN, yToMin(bottomOriginal + dy)))
                            updateMut.mutate({ id: v.id, patch: { planned_end_time: minToTime(newEnd) }, queryKey })
                          }}
                          onPointerCancel={(e) => {
                            if (!drag || drag.mode !== 'resize' || drag.visit.id !== v.id) return
                            e.stopPropagation()
                            if (e.currentTarget.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
                            setDrag(null)
                          }}
                          // Same touch-none reasoning as the block body, but
                          // scoped to an active resize of THIS block.
                          className={cn('absolute inset-x-0 bottom-0 h-1.5 cursor-ns-resize', resizingThis && 'touch-none')}
                        />
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      </div>
      {dragErr && <p className="px-1 text-xs text-destructive">{dragErr}</p>}
    </div>
  )
}
