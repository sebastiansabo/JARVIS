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
// yToMin / minToY scale by the pxPerHour prop, so they live inside the component.
/** "6 aug." — short ro-RO date for multi-day span labels. */
function fmtDayShort(key: string): string {
  const d = new Date(`${key}T00:00:00`)
  return isNaN(d.getTime()) ? key : d.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })
}
// Keep a value inside the visible window — a captured pointer keeps reporting
// coordinates after leaving the column, so an off-grid drag would otherwise
// yield negative/past-21:00 minutes → malformed times.
function clampMin(min: number): number { return Math.max(HOUR_START * 60, Math.min(HOUR_END * 60, min)) }

export interface TimeGridEvent {
  id: number
  dayKey: string
  /** Return day ("YYYY-MM-DD") for a multi-day session; defaults to dayKey.
   *  When later than dayKey, the block spans each day between them (departure
   *  day: startMin→grid-bottom, middle days: full, return day: top→endMin). */
  endDayKey?: string
  /** Minutes-of-day; null → untimed (rendered in the all-day band). */
  startMin: number | null
  endMin: number | null
  /** Tailwind classes for the block background + text, e.g. "bg-blue-100 text-blue-700". */
  color: string
  title: string
  subtitle?: string
  /** Optional third info line (e.g. "VIN: ...123456") — small, non-bold, under
   *  the title/subtitle in both day blocks and week bars. */
  meta?: string
  /** Grouping key (the car's VIN). Two events with the SAME groupKey whose time
   *  ranges overlap on the same day are "interlaced" — the same car double-booked
   *  — and get a red hachured overlap marker. */
  groupKey?: string
  /** When true (and onMove is provided), the block can be dragged to a new
   *  time/day. Callers set this only for records that may be rescheduled.
   *  Multi-day events are not draggable (reschedule via the form instead). */
  draggable?: boolean
}

// One day's slice of an event (a multi-day event yields one per day it covers).
interface Segment { ev: TimeGridEvent; s: number; e: number; isStart: boolean }
// A cluster of overlapping segments; `s`/`e` are the cluster's bounds in minutes.
interface Cluster { items: Segment[]; s: number; e: number }

// Sweep-line grouping of a day's already-sliced segments: sort by start, extend
// the running cluster while the next segment starts before its current max-end.
function clusterSegments(segs: Segment[]): Cluster[] {
  const sorted = [...segs].sort((a, b) => a.s - b.s || a.e - b.e)
  const clusters: Cluster[] = []
  for (const t of sorted) {
    const last = clusters[clusters.length - 1]
    if (last && t.s < last.e) { last.items.push(t); last.e = Math.max(last.e, t.e) }
    else clusters.push({ items: [t], s: t.s, e: t.e })
  }
  return clusters
}

// Only 'create' remains from FSTimeGrid's three drag modes — no move/resize.
// Google-Calendar-style create in the Day-view hour grid, tracked by an
// ABSOLUTE day key + minutes. `start*` is where the drag began, `end*` is where
// the pointer is now; departure/return are their (day, time) min/max.
type CreateDrag = { startKey: string; startMin: number; endKey: string; endMin: number }

export default function TimeGrid({ dayCols, events, onEventClick, onSlotAdd, onMove, pxPerHour = PX_PER_HOUR }: {
  dayCols: Date[]
  events: TimeGridEvent[]
  onEventClick: (id: number) => void
  /** Create a session for a dragged range (Day-view hour grid) or a clicked day
   *  cell (Week view). `departure`/`ret` are "YYYY-MM-DDTHH:MM" strings. */
  onSlotAdd?: (departure: string, ret: string) => void
  /** Called when a draggable block is dropped at a new day/time (duration
   *  preserved). Only fired for events with draggable:true. */
  onMove?: (id: number, dayKey: string, startTime: string, endTime: string) => void
  /** Vertical scale (px per hour). Desktop foi-parcurs passes a taller value so
   *  the two-line blocks (time+name / vehicle) don't clip; defaults to a compact 48. */
  pxPerHour?: number
}) {
  const [drag, setDrag] = useState<CreateDrag | null>(null)
  const gridRef = useRef<HTMLDivElement | null>(null) // stable columns wrapper — holds the drag's pointer capture across week changes
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

  // Vertical scale helpers, bound to the pxPerHour prop.
  const minToY = (min: number) => ((min - HOUR_START * 60) / 60) * pxPerHour
  const yToMin = (y: number) => snap(HOUR_START * 60 + (y / pxPerHour) * 60)

  const hours = Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, i) => HOUR_START + i)
  const gridHeight = (HOUR_END - HOUR_START) * pxPerHour
  const todayKey = keyOf(new Date())
  const isWeek = dayCols.length > 1
  // Column count is responsive (callers pass 3 on phones, 7 on desktop), so the
  // grid just fills the container — no forced-width horizontal scroll.
  const gridColsClass = dayCols.length >= 7 ? 'grid-cols-7'
    : dayCols.length === 3 ? 'grid-cols-3'
    : dayCols.length === 2 ? 'grid-cols-2' : 'grid-cols-1'
  const cardMinW = 'min-w-0'
  // Hour gutter stays pinned while the week scrolls horizontally so the time
  // labels never scroll out of view.
  const gutter = 'sticky left-0 z-20 w-10 shrink-0 bg-card'

  // Hourly grid holds only SINGLE-day timed sessions; multi-day sessions render
  // as spanning bars in the top band (event-calendar style), and untimed
  // (no start time) sessions sit in that band on their own day.
  const cols = dayCols.map((d) => {
    const dk = keyOf(d)
    const timed: Segment[] = []
    const untimed: TimeGridEvent[] = []
    for (const ev of events) {
      if (ev.startMin == null) { if (ev.dayKey === dk) untimed.push(ev); continue }
      if (ev.endDayKey && ev.endDayKey > ev.dayKey) continue // multi-day → top band
      if (ev.dayKey !== dk) continue
      const s = clampMin(ev.startMin)
      const e = clampMin(Math.max(ev.endMin ?? ev.startMin + 60, s + SNAP_MIN))
      timed.push({ ev, s, e, isStart: true })
    }
    return { d, dk, timed, untimed }
  })
  const hasAnyUntimed = cols.some((c) => c.untimed.length > 0)
  // The left gutter only earns its 40px when it holds something: the Day-view
  // hour labels, or the "Fără oră" tag when untimed sessions exist. In Week view
  // (no hour grid, no untimed) it's dead space that shoves the days right — drop
  // it so the bars use the full width.
  const showGutter = !isWeek || hasAnyUntimed

  // Multi-day sessions → horizontal bars spanning their visible day columns,
  // greedily packed into rows so overlapping spans stack.
  const dayKeys = cols.map((c) => c.dk)
  const firstKey = dayKeys[0] ?? ''
  const lastKey = dayKeys[dayKeys.length - 1] ?? ''
  // Week view renders EVERY timed session as a bar (single-day bars span one
  // column); Day view keeps its hourly grid and only bars the multi-day ones.
  const bars = events
    .filter((ev) => ev.startMin != null && (isWeek || (ev.endDayKey && ev.endDayKey > ev.dayKey)))
    .map((ev) => {
      const endKey = ev.endDayKey && ev.endDayKey > ev.dayKey ? ev.endDayKey : ev.dayKey
      return {
        ev,
        sc: ev.dayKey < firstKey ? 0 : dayKeys.indexOf(ev.dayKey),
        ec: endKey > lastKey ? dayKeys.length - 1 : dayKeys.indexOf(endKey),
        // Past working hours (08:00–18:00): flag so it can be marked.
        late: ev.startMin! < WORK_START * 60 || (ev.endMin != null && ev.endMin > WORK_END * 60),
      }
    })
    .filter((b) => b.sc >= 0 && b.ec >= 0 && b.sc <= b.ec)
    // Chronological within a day: start column, then departure time, then span
    // end / id. Without the startMin tiebreak, same-day bars kept their incoming
    // (created_at) order and rendered out of time order.
    .sort((a, b) => a.sc - b.sc || a.ev.startMin! - b.ev.startMin! || a.ec - b.ec || a.ev.id - b.ev.id)
  const barRows: { ev: TimeGridEvent; sc: number; ec: number; late: boolean }[][] = []
  for (const bar of bars) {
    const row = barRows.find((r) => r[r.length - 1].ec < bar.sc)
    if (row) row.push(bar); else barRows.push([bar])
  }

  // Interlaced sessions: same car (groupKey) on the SAME single day whose time
  // ranges overlap → the car is double-booked. For each such bar record its own
  // overlap sub-interval + a shared window (the conflicting bars' extent) so a
  // red hachure can be drawn at the same x across every bar in the group.
  // Same car (groupKey) on the SAME day → number its sessions chronologically
  // S1, S2, … Sx (starting session of the day first) so they can be referred to
  // by code. Sessions whose time ranges overlap are "Suprapus cu Sx" (the car is
  // double-booked): record each one's overlap sub-interval + the codes it
  // collides with + a shared window (the conflicting members' extent) so a red
  // hachure can be drawn at the same x across every one of them.
  const barEnd = (ev: TimeGridEvent) => clampMin(Math.max(ev.endMin ?? ev.startMin! + 60, ev.startMin! + SNAP_MIN))
  const codeNum = (c: string) => parseInt(c.slice(1), 10)
  const seriesCode = new Map<number, string>()    // ev.id → "S2"
  const overlapWith = new Map<number, string[]>() // ev.id → ["S1","S3"] it overlaps
  const conflict = new Map<number, { oS: number; oE: number; gS: number; gE: number }>()
  const carGroups = new Map<string, TimeGridEvent[]>()
  for (const ev of events) {
    if (ev.startMin == null || !ev.groupKey) continue
    const k = `${ev.dayKey}|${ev.groupKey}`
    const arr = carGroups.get(k); if (arr) arr.push(ev); else carGroups.set(k, [ev])
  }
  for (const list of carGroups.values()) {
    if (list.length < 2) continue // codes only matter when a car has ≥2 sessions that day
    list.sort((a, b) => a.startMin! - b.startMin! || a.id - b.id)
    const code = new Map<number, string>()
    list.forEach((ev, i) => { const c = `S${i + 1}`; code.set(ev.id, c); seriesCode.set(ev.id, c) })
    const ov = new Map<number, { oS: number; oE: number }>()
    for (const ev of list) {
      const bs = ev.startMin!, be = barEnd(ev)
      let oS = Infinity, oE = -Infinity; const codes: string[] = []
      for (const o of list) {
        if (o === ev) continue
        const s = Math.max(bs, o.startMin!), e = Math.min(be, barEnd(o))
        if (e > s) { oS = Math.min(oS, s); oE = Math.max(oE, e); codes.push(code.get(o.id)!) }
      }
      if (oE > oS) { ov.set(ev.id, { oS, oE }); overlapWith.set(ev.id, codes.sort((a, b) => codeNum(a) - codeNum(b))) }
    }
    if (!ov.size) continue
    const conf = list.filter((ev) => ov.has(ev.id))
    const gS = Math.min(...conf.map((ev) => ev.startMin!))
    const gE = Math.max(...conf.map((ev) => barEnd(ev)))
    for (const ev of conf) conflict.set(ev.id, { ...ov.get(ev.id)!, gS, gE })
  }
  // Bold diagonal red/white stripes marking the double-booked interval (white
  // gaps keep the hachure legible on top of the pastel car-coloured bar).
  const HACHURE = 'repeating-linear-gradient(45deg, rgba(220,38,38,0.95) 0, rgba(220,38,38,0.95) 3px, rgba(255,255,255,0.55) 3px, rgba(255,255,255,0.55) 6px)'

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
          {showGutter && <div className={gutter} />}
          <div className={cn('grid flex-1 gap-1', gridColsClass)}>
            {cols.map(({ d, dk }) => (
              <p key={dk} className={cn('truncate text-center text-[10px] font-semibold uppercase text-muted-foreground', dk === todayKey && 'text-primary')}>
                {d.toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit' })}
              </p>
            ))}
          </div>
        </div>

        {/* Top band — multi-day sessions as spanning bars (packed into rows) +
            untimed ("Fără oră") sessions on their own day. */}
        {(isWeek || hasAnyUntimed || barRows.length > 0) && (
          <div data-testid="tg-allday-band" className="flex gap-1">
            {showGutter && (
              <div className={cn(gutter, 'flex items-start justify-end pr-1 pt-0.5')}>
                {hasAnyUntimed && <span className="text-[9px] font-semibold uppercase leading-tight tracking-wide text-muted-foreground">Fără oră</span>}
              </div>
            )}
            <div className="relative min-w-0 flex-1">
              {/* Week: weekend-tinted day columns behind the session bars; click
                  empty space to add a session on that day. */}
              {isWeek && (
                <div className={cn('absolute inset-0 grid gap-1', gridColsClass)}>
                  {cols.map(({ d, dk }) => {
                    const weekend = d.getDay() === 0 || d.getDay() === 6
                    return (
                      <button
                        key={dk}
                        type="button"
                        data-testid={`tg-col-${dk}`}
                        onClick={() => onSlotAdd?.(`${dk}T09:00`, `${dk}T10:00`)}
                        className={cn('rounded-lg', weekend ? 'bg-zinc-200/50 dark:bg-red-950/30' : 'bg-muted/20', onSlotAdd && 'cursor-pointer')}
                      />
                    )
                  })}
                </div>
              )}
              <div className={cn('relative space-y-2', isWeek && 'pointer-events-none min-h-[200px] py-1')}>
              {/* Session bars — each spans its day column(s) via grid placement;
                  a red left edge + ⚠ marks a TD that runs outside 08:00–18:00. */}
              {barRows.map((row, ri) => (
                <div key={ri} className={cn('grid gap-1', gridColsClass)}>
                  {row.map((bar) => {
                    const isMulti = !!(bar.ev.endDayKey && bar.ev.endDayKey > bar.ev.dayKey)
                    const start = minToTime(bar.ev.startMin!)
                    const end = bar.ev.endMin != null ? minToTime(clampMin(bar.ev.endMin)) : ''
                    // Multi-day: show the full date range ("6 aug 11:30 → 9 aug 14:30")
                    // so the bar reads as spanning several days — not a same-day slot
                    // that got exiled to the band. Same-day bars keep the plain "–".
                    const timeLabel = !end ? start
                      : isMulti ? `${fmtDayShort(bar.ev.dayKey)} ${start} → ${fmtDayShort(bar.ev.endDayKey!)} ${end}`
                      : `${start}–${end}`
                    // Car name first (truncated), then client. CSS truncate limits length to the bar width.
                    const label = `${timeLabel} ${bar.ev.subtitle ? `${bar.ev.subtitle} · ` : ''}${bar.ev.title}`
                    const ci = conflict.get(bar.ev.id) // interlaced (same car, overlapping) → hachure the overlap
                    const code = seriesCode.get(bar.ev.id)   // "S1"…"Sx" (same-car day series)
                    const ovl = overlapWith.get(bar.ev.id)   // codes this session is "Suprapus cu"
                    const bs = bar.ev.startMin!, be = barEnd(bar.ev)
                    const W = ci ? Math.max(ci.gE - ci.gS, 1) : 1
                    return (
                      <button
                        key={bar.ev.id}
                        type="button"
                        data-testid={`tg-block-${bar.ev.id}`}
                        onClick={() => onEventClick(bar.ev.id)}
                        style={{ gridColumnStart: bar.sc + 1, gridColumnEnd: bar.ec + 2 }}
                        className={cn('pointer-events-auto min-w-0 whitespace-normal break-words rounded-md px-2 py-1 text-left text-[11px] font-semibold leading-snug shadow-sm', bar.ev.color, bar.late && 'border-l-4 border-red-500', ci && 'ring-2 ring-red-500')}
                        title={`${code ? `${code} · ` : ''}${label}${bar.late ? ' · în afara programului (08–18)' : ''}${ovl ? ` · Suprapus cu ${ovl.join(', ')}` : ''}`}
                      >
                        {/* time (small) → client (bold, own line) → car → VIN. */}
                        <span className="block text-[10px] font-normal opacity-80">
                          {code && <span data-testid={`tg-code-${bar.ev.id}`} className="mr-1 inline-block rounded bg-foreground/15 px-1 text-[10px] font-bold tabular-nums">{code}</span>}
                          {isMulti && <span data-testid={`tg-multiday-${bar.ev.id}`} className="mr-1 inline-block rounded bg-foreground/15 px-1 text-[9px] font-bold uppercase tracking-wide">multi-zi</span>}
                          {bar.late && <span className="mr-0.5 text-red-600" aria-hidden>⚠</span>}{timeLabel}
                        </span>
                        <span data-testid={`tg-title-${bar.ev.id}`} className="block">{bar.ev.title}</span>
                        {bar.ev.subtitle && <span className="block text-[10px] font-normal opacity-80">{bar.ev.subtitle}</span>}
                        {bar.ev.meta && <span data-testid={`tg-meta-${bar.ev.id}`} className="block text-[9px] font-normal opacity-70">{bar.ev.meta}</span>}
                        {ovl && <span data-testid={`tg-overlap-${bar.ev.id}`} className="mt-0.5 block text-[10px] font-bold text-red-600 dark:text-red-400">Suprapus cu {ovl.join(', ')}</span>}
                        {ci && (
                          <span data-testid={`tg-conflict-${bar.ev.id}`} className="relative mt-1 block h-2.5 w-full overflow-hidden rounded-full bg-background/80 ring-1 ring-red-500/40" aria-hidden>
                            {/* This session's own span (context), then the double-booked slice hachured red. */}
                            <span className="absolute inset-y-0 rounded-full bg-foreground/40" style={{ left: `${((bs - ci.gS) / W) * 100}%`, width: `${((be - bs) / W) * 100}%` }} />
                            <span className="absolute inset-y-0" style={{ left: `${((ci.oS - ci.gS) / W) * 100}%`, width: `${((ci.oE - ci.oS) / W) * 100}%`, backgroundImage: HACHURE }} />
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              ))}
              {/* Untimed single-day sessions. */}
              {hasAnyUntimed && (
                <div className={cn('grid gap-1', gridColsClass)}>
                  {cols.map(({ dk, untimed }) => (
                    <div key={dk} className="min-w-0 space-y-0.5">
                      {untimed.map((ev) => (
                        <button
                          key={ev.id}
                          type="button"
                          data-testid={`tg-block-${ev.id}`}
                          onClick={() => onEventClick(ev.id)}
                          className={cn('pointer-events-auto block w-full truncate rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold', ev.color)}
                        >
                          {ev.title}
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              )}
              </div>
            </div>
          </div>
        )}

        {/* Hour-grid (Day view only — Week uses the bars above). */}
        {!isWeek && (
        <div data-testid="tg-hourgrid" className="flex gap-1">
          <div className={gutter}>
            {hours.map((h) => (
              <div key={h} className="relative" style={{ height: pxPerHour }}>
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
                  {clusterSegments(timed).map((cl) => {
                    const top = minToY(cl.s)
                    // −2px so consecutive (back-to-back half/hour) blocks keep a
                    // visible gap instead of abutting into one solid band.
                    const height = Math.max(minToY(cl.e) - top - 2, 16)
                    if (cl.items.length === 1) {
                      const seg = cl.items[0]
                      const ev = seg.ev
                      const isMultiDay = !!(ev.endDayKey && ev.endDayKey > ev.dayKey)
                      const canMove = !!(ev.draggable && onMove && !isMultiDay) // multi-day: reschedule via form
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
                          {/* time (small) → client (bold, own line) → car → VIN,
                              each on its own line so the name reads clearly. */}
                          <span className="block truncate text-[10px] font-normal opacity-80">
                            {seriesCode.get(ev.id) && <span data-testid={`tg-code-${ev.id}`} className="mr-1 rounded bg-foreground/15 px-1 text-[9px] font-bold tabular-nums">{seriesCode.get(ev.id)}</span>}
                            {minToTime(ev.startMin!)}{ev.endMin != null ? `–${minToTime(clampMin(ev.endMin))}` : ''}
                          </span>
                          <span data-testid={`tg-title-${ev.id}`} className="block truncate">{ev.title}</span>
                          {overlapWith.get(ev.id) && <span data-testid={`tg-overlap-${ev.id}`} className="block truncate text-[9px] font-bold text-red-600 dark:text-red-400">Suprapus cu {overlapWith.get(ev.id)!.join(', ')}</span>}
                          {ev.subtitle && <span className="block truncate text-[9px] font-normal opacity-80">{ev.subtitle}</span>}
                          {ev.meta && <span data-testid={`tg-meta-${ev.id}`} className="block truncate text-[9px] font-normal opacity-70">{ev.meta}</span>}
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
                        <span className="block truncate">{seriesCode.get(first.id) ? `${seriesCode.get(first.id)} ` : ''}{`${minToTime(first.startMin!)} ${first.title}`}</span>
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
        )}
      </div>

      {/* Cluster list — sessions sharing an overlapping slot. */}
      {openCluster && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3"
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
                    <span className="flex items-center gap-1.5">
                      {seriesCode.get(ev.id) && <span className="shrink-0 rounded bg-foreground/15 px-1 text-[10px] font-bold tabular-nums">{seriesCode.get(ev.id)}</span>}
                      <span className="truncate text-sm font-semibold">{ev.title}</span>
                    </span>
                    {ev.subtitle && <span className="block truncate text-xs text-muted-foreground">{ev.subtitle}</span>}
                    {overlapWith.get(ev.id) && <span className="block text-xs font-bold text-red-600 dark:text-red-400">Suprapus cu {overlapWith.get(ev.id)!.join(', ')}</span>}
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
