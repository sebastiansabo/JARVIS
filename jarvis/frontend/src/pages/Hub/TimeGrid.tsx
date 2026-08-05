import { useRef, useState } from 'react'
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
// above the hour-grid (never inside a day column, so it can't push that
// column's hour lines down and break cross-column alignment).

const HOUR_START = 7
const HOUR_END = 21
const PX_PER_HOUR = 48
const SNAP_MIN = 30
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
}

// Only 'create' remains from FSTimeGrid's three drag modes — no move/resize.
type CreateDrag = { col: string; y0: number; y1: number }

export default function TimeGrid({ dayCols, events, onEventClick, onSlotAdd }: {
  dayCols: Date[]
  events: TimeGridEvent[]
  onEventClick: (id: number) => void
  onSlotAdd?: (dayKey: string, startTime: string, endTime: string) => void
}) {
  const [drag, setDrag] = useState<CreateDrag | null>(null)
  // Suppress the one native click a real browser synthesizes right after a
  // pointerup on a block, so a create-drag ending over a block can't also open
  // it. jsdom never synthesizes that follow-on click, so it's untested but
  // matters for real input.
  const suppressClickRef = useRef<number | null>(null)

  const hours = Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, i) => HOUR_START + i)
  const gridHeight = (HOUR_END - HOUR_START) * PX_PER_HOUR
  const todayKey = keyOf(new Date())
  const gridColsClass = dayCols.length > 1 ? 'grid-cols-7' : 'grid-cols-1'

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

        {/* Shared all-day band for untimed events — one flex row so every cell
            shares a uniform height; rendered only when some day has one. */}
        {hasAnyUntimed && (
          <div data-testid="tg-allday-band" className="flex gap-1">
            <div className="flex w-10 shrink-0 items-start justify-end pr-1 pt-0.5">
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
          <div className="w-10 shrink-0">
            {hours.map((h) => (
              <div key={h} className="relative" style={{ height: PX_PER_HOUR }}>
                <span className="absolute -top-2 right-1 text-[10px] font-medium text-muted-foreground">{`${pad(h)}:00`}</span>
              </div>
            ))}
          </div>
          <div className={cn('grid flex-1 gap-1', gridColsClass)}>
            {cols.map(({ dk, timed }) => {
              const dragging = drag?.col === dk
              const selTop = dragging ? minToY(clampMin(yToMin(Math.min(drag!.y0, drag!.y1)))) : 0
              const selBottom = dragging ? minToY(clampMin(yToMin(Math.max(drag!.y0, drag!.y1)))) : 0
              return (
                <div
                  key={dk}
                  data-testid={`tg-col-${dk}`}
                  className={cn('relative min-w-0 rounded-lg bg-muted/30', onSlotAdd && 'cursor-pointer', dragging && 'touch-none')}
                  style={{ height: gridHeight }}
                  onPointerDown={(e) => {
                    if (!onSlotAdd) return
                    if (e.button !== 0 && e.pointerType === 'mouse') return
                    const rect = e.currentTarget.getBoundingClientRect()
                    const y0 = e.clientY - rect.top
                    e.currentTarget.setPointerCapture(e.pointerId)
                    setDrag({ col: dk, y0, y1: y0 })
                  }}
                  onPointerMove={(e) => {
                    if (!drag || drag.col !== dk) return
                    const rect = e.currentTarget.getBoundingClientRect()
                    setDrag({ col: dk, y0: drag.y0, y1: e.clientY - rect.top })
                  }}
                  onPointerUp={(e) => {
                    if (!onSlotAdd || !drag || drag.col !== dk) return
                    e.currentTarget.releasePointerCapture(e.pointerId)
                    const a = clampMin(yToMin(Math.min(drag.y0, drag.y1)))
                    let b = clampMin(yToMin(Math.max(drag.y0, drag.y1)))
                    if (b - a < SNAP_MIN) b = clampMin(a + 60) // plain click → 1h default
                    let startMin = a
                    if (b - startMin < SNAP_MIN) startMin = clampMin(b - 60) // clamped against 21:00
                    setDrag(null)
                    onSlotAdd(dk, minToTime(startMin), minToTime(b))
                  }}
                  onPointerCancel={(e) => {
                    if (!drag || drag.col !== dk) return
                    if (e.currentTarget.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
                    setDrag(null)
                  }}
                >
                  {hours.slice(0, -1).map((h) => (
                    <div key={h} className="absolute inset-x-0 border-t border-border/30" style={{ top: minToY(h * 60) }} />
                  ))}
                  {dragging && (
                    <div
                      data-testid="tg-drag-selection"
                      className="pointer-events-none absolute inset-x-0.5 rounded-md border border-primary/50 bg-primary/20"
                      style={{ top: selTop, height: Math.max(selBottom - selTop, 4) }}
                    />
                  )}
                  {timed.map((ev) => {
                    const startMin = clampMin(ev.startMin!)
                    const endMin = clampMin(Math.max(ev.endMin ?? startMin + 60, startMin + SNAP_MIN))
                    const top = minToY(startMin)
                    const height = Math.max(minToY(endMin) - top, 18)
                    return (
                      <button
                        key={ev.id}
                        type="button"
                        data-testid={`tg-block-${ev.id}`}
                        onClick={() => {
                          if (suppressClickRef.current === ev.id) { suppressClickRef.current = null; return }
                          onEventClick(ev.id)
                        }}
                        style={{ top, height }}
                        className={cn('absolute left-0.5 right-0.5 overflow-hidden rounded-md px-1.5 py-0.5 text-left text-[11px] font-semibold leading-tight shadow-sm', ev.color)}
                      >
                        <span className="block truncate">{`${minToTime(ev.startMin!)} ${ev.title}`}</span>
                        {ev.subtitle && <span className="block truncate text-[9px] font-normal opacity-80">{ev.subtitle}</span>}
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
