import { useRef, useState } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

// Reusable Week/Day time-grid extracted from FieldSalesCalendar's FSTimeGrid.
// This is the READ-SAFE variant: it renders positioned event blocks and
// supports click-to-open + click/drag-on-empty-space-to-add, but deliberately
// omits drag-to-move / drag-to-resize so a stray drag can never rewrite an
// existing record's times. Callers own the event→geometry mapping (compute
// startMin/endMin + a color) and the add/open side effects.
//
// Geometry: a fixed 07:00–21:00 window at 48px/hour; empty-slot interactions
// snap to 30 min. `startMin`/`endMin` are minutes-of-day; a null `startMin`
// makes the event "untimed" → it lives in the shared "Fără oră" all-day band
// above the hour-grid. Events whose time ranges overlap in a day column are
// COLLAPSED into one "cluster" block (a stack showing a count); tapping it
// opens a list of the individual sessions. Red lines mark the 08:00–18:00
// working-hours interval.

const HOUR_START = 7
const HOUR_END = 19
const WORK_START = 8
const WORK_END = 18
const PX_PER_HOUR = 48
const SNAP_MIN = 30
// Pointer movement (px) below which a press+release on a draggable block is a
// click (open), not a move.
const DRAG_THRESHOLD_PX = 4
const pad = (n: number) => String(n).padStart(2, '0')

function keyOf(d: Date): string { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
function minToTime(min: number): string { return `${pad(Math.floor(min / 60))}:${pad(min % 60)}` }
function snap(min: number): number { return Math.round(min / SNAP_MIN) * SNAP_MIN }
function yToMin(y: number): number { return snap(HOUR_START * 60 + (y / PX_PER_HOUR) * 60) }
function minToY(min: number): number { return ((min - HOUR_START * 60) / 60) * PX_PER_HOUR }
// Keep a value inside the visible window — a captured pointer keeps reporting
// coordinates after leaving the column, so an off-grid drag would otherwise
// yield negative/past-21:00 minutes → malformed times.
function clampMin(min: number): number { return Math.max(HOUR_START * 60, Math.min(HOUR_END * 60, min)) }

export interface TimeGridEvent {
  id: number
  dayKey: string
  /** Minutes-of-day; null → untimed (rendered in the all-day band). */
  startMin: number | null
  endMin: number | null
  /** Tailwind classes for the block background + text, e.g. "bg-blue-100 text-blue-700". */
  color: string
  title: string
  subtitle?: string
  /** When true (and onMove is provided), the block can be dragged to a new
   *  time/day. Callers set this only for records that may be rescheduled. */
  draggable?: boolean
}

// A cluster of timed events whose ranges overlap; `s`/`e` are the cluster's
// effective (clamped) bounds in minutes.
interface Cluster { items: { ev: TimeGridEvent; s: number; e: number }[]; s: number; e: number }

// Sweep-line grouping: sort by effective start, extend the running cluster
// while the next event starts before the cluster's current max-end.
function clusterTimed(events: TimeGridEvent[]): Cluster[] {
  const withRange = events.map((ev) => {
    const s = clampMin(ev.startMin!)
    const e = clampMin(Math.max(ev.endMin ?? s + 60, s + SNAP_MIN))
    return { ev, s, e }
  }).sort((a, b) => a.s - b.s || a.e - b.e)
  const clusters: Cluster[] = []
  for (const t of withRange) {
    const last = clusters[clusters.length - 1]
    if (last && t.s < last.e) { last.items.push(t); last.e = Math.max(last.e, t.e) }
    else clusters.push({ items: [t], s: t.s, e: t.e })
  }
  return clusters
}

// Only 'create' remains from FSTimeGrid's three drag modes — no move/resize.
// Google-Calendar-style create, tracked by ABSOLUTE day keys + minutes (not
// column indices) so the range survives a week change: dragging to the grid
// edge auto-advances the week (onWeekShift) and the selection keeps extending —
// e.g. a Friday→next-Monday session. `start*` is where the drag began, `end*`
// is where the pointer is now; departure/return are their (day, time) min/max.
const EDGE_PX = 44 // pointer within this many px of the grid edge auto-advances the week
type CreateDrag = { startKey: string; startMin: number; endKey: string; endMin: number }

export default function TimeGrid({ dayCols, events, onEventClick, onSlotAdd, onMove, onWeekShift }: {
  dayCols: Date[]
  events: TimeGridEvent[]
  onEventClick: (id: number) => void
  /** Create a session for a dragged range. `departure`/`ret` are full
   *  "YYYY-MM-DDTHH:MM" strings; a drag spanning several day columns yields a
   *  multi-day range (departure on the earlier day, return on the later). */
  onSlotAdd?: (departure: string, ret: string) => void
  /** Called when a draggable block is dropped at a new day/time (duration
   *  preserved). Only fired for events with draggable:true. */
  onMove?: (id: number, dayKey: string, startTime: string, endTime: string) => void
  /** Advance/retreat the visible week (dir +1/−1) — invoked mid-create-drag
   *  when the pointer reaches the grid edge, so a range can span into the
   *  next/previous week. When omitted, no auto-advance happens. */
  onWeekShift?: (dir: 1 | -1) => void
}) {
  const [drag, setDrag] = useState<CreateDrag | null>(null)
  const gridRef = useRef<HTMLDivElement | null>(null) // stable columns wrapper — holds the drag's pointer capture across week changes
  const lastAdvanceRef = useRef(0)                    // throttle edge auto-advance
  // Active block move-drag (draggable events only). Carries raw client coords —
  // only the delta drives the math, and screen-space delta equals column-space
  // delta (columns don't resize mid-drag).
  const [move, setMove] = useState<{ ev: TimeGridEvent; col: string; x0: number; y0: number; x1: number; y1: number } | null>(null)
  // The list of sessions shown in the cluster popover (null = closed).
  const [openCluster, setOpenCluster] = useState<TimeGridEvent[] | null>(null)
  // Column DOM refs (keyed by day key) for the move day-switch heuristic.
  const colRefs = useRef<Record<string, HTMLDivElement | null>>({})
  // Suppresses the one native click a browser fires after a pointer-resolved
  // open/move on a draggable block.
  const suppressClickRef = useRef<number | null>(null)

  const hours = Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, i) => HOUR_START + i)
  const gridHeight = (HOUR_END - HOUR_START) * PX_PER_HOUR
  const todayKey = keyOf(new Date())
  const isWeek = dayCols.length > 1
  const gridColsClass = isWeek ? 'grid-cols-7' : 'grid-cols-1'
  // Mobile shows ~3 of the 7 week columns by widening the card past the
  // viewport (horizontal scroll reveals the rest of the week); desktop fits
  // all 7. Day view stays a single comfortable column.
  const cardMinW = isWeek ? 'min-w-[860px] sm:min-w-[560px]' : 'min-w-[320px]'
  // Hour gutter stays pinned while the week scrolls horizontally so the time
  // labels never scroll out of view.
  const gutter = 'sticky left-0 z-20 w-10 shrink-0 bg-card'

  const byDay = new Map<string, TimeGridEvent[]>()
  for (const ev of events) {
    const list = byDay.get(ev.dayKey) ?? []
    list.push(ev)
    byDay.set(ev.dayKey, list)
  }

  const cols = dayCols.map((d) => {
    const dk = keyOf(d)
    const dayEvents = byDay.get(dk) ?? []
    return { d, dk, timed: dayEvents.filter((e) => e.startMin != null), untimed: dayEvents.filter((e) => e.startMin == null) }
  })
  const hasAnyUntimed = cols.some((c) => c.untimed.length > 0)

  // Which day column a screen-x coordinate falls in (for cross-day create-drag).
  const columnAtX = (x: number): string | null => {
    for (const c of cols) {
      const r = colRefs.current[c.dk]?.getBoundingClientRect()
      if (r && r.width > 0 && x >= r.left && x <= r.right) return c.dk
    }
    return null
  }
  // Column top (all columns share it, so time is x-independent). Falls back to
  // the first visible column when the pointer is between/outside columns.
  const colTopAt = (x: number): number => {
    const k = columnAtX(x) ?? cols[0]?.dk
    const el = k ? colRefs.current[k] : null
    return el ? el.getBoundingClientRect().top : 0
  }

  // Departure/return of the active create-drag, ordered by (day, time) — keys
  // are "YYYY-MM-DD" so a plain string compare orders days correctly, and the
  // departure day may be off-screen (a previous week) after an auto-advance.
  const dragRange = () => {
    if (!drag) return null
    const startEarlier = drag.startKey < drag.endKey || (drag.startKey === drag.endKey && drag.startMin <= drag.endMin)
    return {
      depKey: startEarlier ? drag.startKey : drag.endKey, depMin: startEarlier ? drag.startMin : drag.endMin,
      retKey: startEarlier ? drag.endKey : drag.startKey, retMin: startEarlier ? drag.endMin : drag.startMin,
    }
  }

  // Selection band for one visible column while dragging (null = outside span).
  const selBand = (dk: string): { top: number; bottom: number } | null => {
    const r = dragRange()
    if (!r || dk < r.depKey || dk > r.retKey) return null
    if (r.depKey === r.retKey) return { top: minToY(Math.min(r.depMin, r.retMin)), bottom: minToY(Math.max(r.depMin, r.retMin)) }
    if (dk === r.depKey) return { top: minToY(r.depMin), bottom: gridHeight }
    if (dk === r.retKey) return { top: 0, bottom: minToY(r.retMin) }
    return { top: 0, bottom: gridHeight } // a fully-covered middle day
  }

  return (
    // touch-action:none on the whole grid while a create-drag is active, so a
    // sideways pull scrubs the selection instead of horizontally scrolling the
    // week (which would drift the drag / jump days).
    <div className="overflow-x-auto" style={drag ? { touchAction: 'none' } : undefined}>
      <div className={cn('flex flex-col gap-1 rounded-2xl border border-border/60 bg-card p-2', cardMinW)}>
        {/* Day-label header row (gutter spacer + one label per column). */}
        <div className="flex gap-1">
          <div className={gutter} />
          <div className={cn('grid flex-1 gap-1', gridColsClass)}>
            {cols.map(({ d, dk }) => (
              <p key={dk} className={cn('truncate text-center text-[10px] font-semibold uppercase text-muted-foreground', dk === todayKey && 'text-primary')}>
                {d.toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit' })}
              </p>
            ))}
          </div>
        </div>

        {/* Shared all-day band for untimed events. */}
        {hasAnyUntimed && (
          <div data-testid="tg-allday-band" className="flex gap-1">
            <div className={cn(gutter, 'flex items-start justify-end pr-1 pt-0.5')}>
              <span className="text-[9px] font-semibold uppercase leading-tight tracking-wide text-muted-foreground">Fără oră</span>
            </div>
            <div className={cn('grid flex-1 gap-1', gridColsClass)}>
              {cols.map(({ dk, untimed }) => (
                <div key={dk} className="min-w-0 space-y-0.5">
                  {untimed.map((ev) => (
                    <button
                      key={ev.id}
                      type="button"
                      data-testid={`tg-block-${ev.id}`}
                      onClick={() => onEventClick(ev.id)}
                      className={cn('block w-full truncate rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold', ev.color)}
                    >
                      {ev.title}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Hour-grid — gutter labels + one relative day column each. */}
        <div data-testid="tg-hourgrid" className="flex gap-1">
          <div className={gutter}>
            {hours.map((h) => (
              <div key={h} className="relative" style={{ height: PX_PER_HOUR }}>
                <span className="absolute -top-2 right-1 text-[10px] font-medium text-muted-foreground">{`${pad(h)}:00`}</span>
              </div>
            ))}
          </div>
          <div
            ref={gridRef}
            data-testid="tg-colgrid"
            className={cn('relative grid flex-1 gap-1', gridColsClass)}
            // Move/up/cancel live on this STABLE wrapper (not the columns) so the
            // pointer capture survives a week change, whose columns remount.
            onPointerMove={(e) => {
              if (!drag) return
              const endKey = columnAtX(e.clientX) ?? drag.endKey
              const endMin = clampMin(yToMin(e.clientY - colTopAt(e.clientX)))
              setDrag({ ...drag, endKey, endMin })
              // Auto-advance the week when the pointer nears the grid's edge.
              const rect = gridRef.current?.getBoundingClientRect()
              if (rect && rect.width > 0 && onWeekShift && Date.now() - lastAdvanceRef.current > 450) {
                if (e.clientX > rect.right - EDGE_PX) { lastAdvanceRef.current = Date.now(); onWeekShift(1) }
                else if (e.clientX < rect.left + EDGE_PX) { lastAdvanceRef.current = Date.now(); onWeekShift(-1) }
              }
            }}
            onPointerUp={(e) => {
              if (!onSlotAdd || !drag) return
              try { gridRef.current?.releasePointerCapture(e.pointerId) } catch { /* jsdom / no capture */ }
              const r = dragRange()!
              let depMin = r.depMin, retMin = r.retMin
              // Same-day plain click / sub-snap drag → 1h default slot.
              if (r.depKey === r.retKey && retMin - depMin < SNAP_MIN) {
                retMin = clampMin(depMin + 60)
                if (retMin - depMin < SNAP_MIN) depMin = clampMin(retMin - 60)
              }
              setDrag(null)
              onSlotAdd(`${r.depKey}T${minToTime(depMin)}`, `${r.retKey}T${minToTime(retMin)}`)
            }}
            onPointerCancel={() => setDrag(null)}
          >
            {cols.map(({ d, dk, timed }) => {
              const band = selBand(dk)
              const weekend = d.getDay() === 0 || d.getDay() === 6 // Sat/Sun
              return (
                <div
                  key={dk}
                  data-testid={`tg-col-${dk}`}
                  ref={(el) => { colRefs.current[dk] = el }}
                  // Weekends tinted: pale grey (light) / pale red (dark).
                  className={cn('relative min-w-0 snap-start rounded-lg', weekend ? 'bg-zinc-200/50 dark:bg-red-950/30' : 'bg-muted/30', onSlotAdd && 'cursor-pointer')}
                  style={{ height: gridHeight }}
                  onPointerDown={(e) => {
                    if (!onSlotAdd) return
                    if (e.button !== 0 && e.pointerType === 'mouse') return
                    const rect = e.currentTarget.getBoundingClientRect()
                    const startMin = clampMin(yToMin(e.clientY - rect.top))
                    lastAdvanceRef.current = 0
                    try { gridRef.current?.setPointerCapture(e.pointerId) } catch { /* jsdom / no capture */ }
                    setDrag({ startKey: dk, startMin, endKey: dk, endMin: startMin })
                  }}
                >
                  {hours.slice(0, -1).map((h) => (
                    <div key={h} className="absolute inset-x-0 border-t border-border/30" style={{ top: minToY(h * 60) }} />
                  ))}
                  {band && (
                    <div
                      data-testid="tg-drag-selection"
                      className="pointer-events-none absolute inset-x-0.5 rounded-md border border-primary/50 bg-primary/20"
                      style={{ top: band.top, height: Math.max(band.bottom - band.top, 4) }}
                    />
                  )}
                  {clusterTimed(timed).map((cl) => {
                    const top = minToY(cl.s)
                    const height = Math.max(minToY(cl.e) - top, 18)
                    if (cl.items.length === 1) {
                      const ev = cl.items[0].ev
                      const canMove = !!(ev.draggable && onMove)
                      const movingThis = move?.ev.id === ev.id
                      // Live preview offset while dragging this block.
                      let blockTop = top
                      if (movingThis) {
                        const dy = move!.y1 - move!.y0
                        const newStart = clampMin(yToMin(top + dy))
                        blockTop = minToY(newStart)
                      }
                      return (
                        <button
                          key={ev.id}
                          type="button"
                          data-testid={`tg-block-${ev.id}`}
                          // stopPropagation on the block's own pointer events so a
                          // press on a block never reaches the column's create-drag
                          // handlers (which would fire onSlotAdd on top of opening).
                          onPointerDown={(e) => {
                            e.stopPropagation()
                            if (!canMove) return
                            if (e.button !== 0 && e.pointerType === 'mouse') return
                            e.currentTarget.setPointerCapture(e.pointerId)
                            setMove({ ev, col: dk, x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY })
                          }}
                          onPointerMove={(e) => {
                            if (!move || move.ev.id !== ev.id) return
                            e.stopPropagation()
                            setMove({ ...move, x1: e.clientX, y1: e.clientY })
                          }}
                          onPointerUp={(e) => {
                            e.stopPropagation()
                            if (!move || move.ev.id !== ev.id) return
                            e.currentTarget.releasePointerCapture(e.pointerId)
                            const dx = e.clientX - move.x0
                            const dy = e.clientY - move.y0
                            setMove(null)
                            suppressClickRef.current = ev.id
                            if (Math.abs(dx) <= DRAG_THRESHOLD_PX && Math.abs(dy) <= DRAG_THRESHOLD_PX) {
                              onEventClick(ev.id) // sub-threshold → treat as a click
                              return
                            }
                            const sMin = clampMin(ev.startMin!)
                            const eMin = clampMin(Math.max(ev.endMin ?? sMin + 60, sMin + SNAP_MIN))
                            const duration = eMin - sMin
                            const newStart = clampMin(yToMin(minToY(sMin) + dy))
                            const newEnd = Math.min(newStart + duration, HOUR_END * 60)
                            // Best-effort day switch in week view (dx / column width).
                            let newDayKey = dk
                            if (dayCols.length > 1) {
                              const width = colRefs.current[dk]?.getBoundingClientRect().width || 0
                              const originIdx = cols.findIndex((c) => c.dk === dk)
                              if (width > 0 && originIdx >= 0) {
                                const newIdx = Math.min(cols.length - 1, Math.max(0, originIdx + Math.round(dx / width)))
                                newDayKey = cols[newIdx].dk
                              }
                            }
                            onMove!(ev.id, newDayKey, minToTime(newStart), minToTime(newEnd))
                          }}
                          onPointerCancel={(e) => {
                            if (!move || move.ev.id !== ev.id) return
                            e.stopPropagation()
                            if (e.currentTarget.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
                            setMove(null)
                          }}
                          onClick={() => {
                            if (suppressClickRef.current === ev.id) { suppressClickRef.current = null; return }
                            onEventClick(ev.id)
                          }}
                          style={{ top: blockTop, height }}
                          className={cn('absolute left-0.5 right-0.5 z-[1] overflow-hidden rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold leading-tight shadow-sm', ev.color, canMove && 'cursor-grab', movingThis && 'cursor-grabbing touch-none ring-2 ring-primary/50')}
                        >
                          <span className="block truncate">{`${minToTime(ev.startMin!)} ${ev.title}`}</span>
                          {ev.subtitle && <span className="block truncate text-[9px] font-normal opacity-80">{ev.subtitle}</span>}
                        </button>
                      )
                    }
                    // Cluster of ≥2 overlapping sessions → one stacked block.
                    const first = cl.items[0].ev
                    return (
                      <button
                        key={`cl-${first.id}`}
                        type="button"
                        data-testid={`tg-cluster-${first.id}`}
                        onPointerDown={(e) => e.stopPropagation()}
                        onPointerUp={(e) => e.stopPropagation()}
                        onClick={() => setOpenCluster(cl.items.map((i) => i.ev))}
                        style={{ top, height }}
                        className={cn('absolute left-0.5 right-0.5 z-[1] overflow-hidden rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold leading-tight shadow-sm', first.color)}
                      >
                        {/* stacked-card hint peeking above the block */}
                        <span aria-hidden className={cn('absolute -top-1 left-1.5 right-1.5 h-1.5 rounded-t-md opacity-60', first.color)} />
                        <span data-testid="tg-cluster-count" className="absolute right-1 top-1 rounded-full bg-background/80 px-1.5 text-[9px] font-bold text-foreground shadow-sm">{cl.items.length}</span>
                        <span className="block truncate">{`${minToTime(first.startMin!)} ${first.title}`}</span>
                        <span className="block truncate text-[9px] font-normal opacity-80">{`+${cl.items.length - 1} sesiuni`}</span>
                      </button>
                    )
                  })}
                </div>
              )
            })}
            {/* Working-hours interval markers (rendered above the columns). */}
            <div data-testid="tg-workline-start" className="pointer-events-none absolute inset-x-0 z-10 border-t-2 border-red-400/70" style={{ top: minToY(WORK_START * 60) }} />
            <div data-testid="tg-workline-end" className="pointer-events-none absolute inset-x-0 z-10 border-t-2 border-red-400/70" style={{ top: minToY(WORK_END * 60) }} />
          </div>
        </div>
      </div>

      {/* Cluster list — sessions sharing an overlapping slot. */}
      {openCluster && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-3 sm:items-center"
          onClick={() => setOpenCluster(null)}
        >
          <div
            data-testid="tg-cluster-list"
            className="w-full max-w-sm rounded-2xl bg-background p-3 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-semibold">{`${openCluster.length} sesiuni în acest interval`}</p>
              <button type="button" onClick={() => setOpenCluster(null)} className="flex h-7 w-7 items-center justify-center rounded-full bg-muted transition-colors hover:bg-muted/70">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-1.5">
              {openCluster.map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  data-testid={`tg-clusteritem-${ev.id}`}
                  onClick={() => { onEventClick(ev.id); setOpenCluster(null) }}
                  className="flex w-full items-center gap-3 rounded-xl border border-border/60 bg-card p-2.5 text-left transition-transform active:scale-[0.99]"
                >
                  <span className={cn('flex h-8 w-12 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold tabular-nums', ev.color)}>
                    {minToTime(ev.startMin!)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{ev.title}</span>
                    {ev.subtitle && <span className="block truncate text-xs text-muted-foreground">{ev.subtitle}</span>}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
