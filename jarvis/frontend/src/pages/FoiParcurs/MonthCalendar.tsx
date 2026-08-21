import { useEffect, useMemo, useState } from 'react'
import { Car, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { naiveDate } from '@/lib/naiveDate'
import { sessionStatus } from './sessionStatus'
import type { FoiContract, FpVehicle } from '@/types/foiParcurs'

const WEEKDAY_LABELS = ['Lu', 'Ma', 'Mi', 'Jo', 'Vi', 'Sâ', 'Du']
const pad = (n: number) => String(n).padStart(2, '0')
function keyOf(d: Date): string { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
function addDays(d: Date, n: number): Date { const x = new Date(d); x.setDate(x.getDate() + n); return x }
function startOfWeek(d: Date): Date { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x }

function dayLabel(key: string): string {
  return new Date(`${key}T00:00:00`).toLocaleDateString('ro-RO', { weekday: 'long', day: '2-digit', month: 'long' })
}
function fmtTime(d: Date): string { return d.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' }) }
function fmtDay(d: Date): string { return d.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' }) }

/** Full interval of a session — always rendered as a range so every row reads
 *  the same: "09:00 → 17:00" (same day), "4 sept. 09:00 → 6 sept. 18:00"
 *  (multi-day), or "4 sept. 19:45 → —" when the return isn't set yet (still out
 *  — the departure date makes a multi-day/ongoing drive read as one). */
function periodOf(c: FoiContract): string {
  const dep = naiveDate(c.departure_datetime)
  if (!dep) return '—'
  const ret = naiveDate(c.return_datetime)
  if (!ret) return `${fmtDay(dep)} ${fmtTime(dep)} → —`
  return keyOf(dep) === keyOf(ret)
    ? `${fmtTime(dep)} → ${fmtTime(ret)}`
    : `${fmtDay(dep)} ${fmtTime(dep)} → ${fmtDay(ret)} ${fmtTime(ret)}`
}

/** Day keys a session covers (departure day … return day, inclusive). */
function spanKeysOf(c: FoiContract): string[] {
  const dep = naiveDate(c.departure_datetime)
  if (!dep) return []
  const ret = naiveDate(c.return_datetime) ?? dep
  const keys: string[] = []
  let d = new Date(dep.getFullYear(), dep.getMonth(), dep.getDate())
  const end = new Date(ret.getFullYear(), ret.getMonth(), ret.getDate())
  while (d <= end) { keys.push(keyOf(d)); d = addDays(d, 1) }
  return keys
}

function carName(vehicle: FpVehicle | undefined, vin?: string | null): string {
  if (vehicle) return [vehicle.brand || vehicle.mark, vehicle.model].filter(Boolean).join(' ') || vehicle.registration_number || vin || '—'
  return vin || '—'
}

interface MonthCalendarProps {
  /** The displayed month (any day within it). */
  monthDate: Date
  /** Sessions bucketed by naive departure day key ("YYYY-MM-DD"). */
  byDay: Map<string, FoiContract[]>
  vinVehicle: Map<string, FpVehicle>
  /** Open a session's detail modal. */
  onOpenDetail: (c: FoiContract) => void
  /** Propose a new session for a dragged day range ("YYYY-MM-DDTHH:MM" ×2). */
  onAdd: (departure: string, ret: string) => void
  /** Drop a dragged session onto a day → reschedule it there (keeps its time). */
  onRescheduleToDay: (id: number, dayKey: string) => void
  /** Distinguishes the two hosts' day cells in tests ("dc-day" | "fp-day"). */
  dayTestIdPrefix: string
}

/**
 * Shared Month view for both driving calendars (Hub DrivingCalendar + desktop
 * CalendarTab): a mini month grid on the left and a day-list side panel on the
 * right. The list toggles between the selected day ("Ziua selectată") and the
 * whole month ("Toată luna", default). Each row shows the session's full period
 * and a detail button; clicking the row highlights the days it spans in the
 * grid. Drag across day cells proposes a new session; dropping a (planned)
 * session's row onto a day reschedules it — both delegated to the host.
 */
export default function MonthCalendar({ monthDate, byDay, vinVehicle, onOpenDetail, onAdd, onRescheduleToDay, dayTestIdPrefix }: MonthCalendarProps) {
  const todayKey = keyOf(new Date())
  const monthStart = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1)
  const cells = useMemo(() => {
    const gridStart = startOfWeek(monthStart)
    return Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  }, [monthStart.getTime()]) // eslint-disable-line react-hooks/exhaustive-deps

  // In-month day keys that actually have sessions (for the "Toată luna" list).
  const monthDayKeys = useMemo(
    () => cells.filter((d) => d.getMonth() === monthDate.getMonth()).map(keyOf),
    [cells, monthDate],
  )
  const daysWithSessions = useMemo(
    () => monthDayKeys.filter((k) => (byDay.get(k)?.length ?? 0) > 0),
    [monthDayKeys, byDay],
  )

  const monthKey = `${monthDate.getFullYear()}-${monthDate.getMonth()}`
  const [scope, setScope] = useState<'day' | 'month'>('month')
  const [pickedKey, setPickedKey] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // Month drag-to-select a date range → multi-day session (a..b unordered).
  const [monthDrag, setMonthDrag] = useState<{ a: string; b: string } | null>(null)
  const monthRange = monthDrag ? (monthDrag.a <= monthDrag.b ? [monthDrag.a, monthDrag.b] : [monthDrag.b, monthDrag.a]) : null
  const inMonthRange = (k: string) => !!monthRange && k >= monthRange[0] && k <= monthRange[1]

  // Reset the day selection + highlight when the month changes.
  useEffect(() => { setPickedKey(null); setSelectedId(null) }, [monthKey])

  const activeKey = pickedKey ?? (monthDayKeys.includes(todayKey) ? todayKey : monthDayKeys[0] ?? todayKey)

  // Day cells to highlight for the clicked session (its departure→return span).
  const selectedContract = useMemo(() => {
    if (selectedId == null) return null
    for (const list of byDay.values()) { const hit = list.find((c) => c.id === selectedId); if (hit) return hit }
    return null
  }, [selectedId, byDay])
  const highlightKeys = useMemo(() => new Set(selectedContract ? spanKeysOf(selectedContract) : []), [selectedContract])

  const selectDay = (k: string) => { setPickedKey(k); setScope('day') }
  const openSession = (c: FoiContract) => { setSelectedId(c.id) }

  const dayLists = scope === 'day' ? [activeKey] : daysWithSessions

  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
      {/* Mini month grid */}
      <div className="w-full rounded-2xl border border-border/60 bg-card p-2 lg:max-w-[600px]">
        <div className="grid grid-cols-7">
          {WEEKDAY_LABELS.map((w) => <div key={w} className="py-1 text-center text-[10px] font-semibold text-muted-foreground">{w}</div>)}
          {cells.map((d) => {
            const k = keyOf(d)
            const inMonth = d.getMonth() === monthDate.getMonth()
            const count = byDay.get(k)?.length ?? 0
            const weekend = d.getDay() === 0 || d.getDay() === 6
            return (
              <button
                key={k}
                type="button"
                data-testid={`${dayTestIdPrefix}-${k}`}
                onClick={() => selectDay(k)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); const id = Number(e.dataTransfer.getData('text/plain')); if (id) onRescheduleToDay(id, k) }}
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
                  highlightKeys.has(k) && 'bg-blue-500/25 ring-1 ring-blue-500/50',
                  k === activeKey && scope === 'day' && 'bg-primary/15 font-bold',
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

      {/* Day-list side panel */}
      <div className="w-full rounded-2xl border border-border/60 bg-card p-3 lg:flex-1">
        <div className="mb-2 flex h-9 gap-0.5 rounded-lg bg-muted p-0.5">
          {([['day', 'Ziua selectată'], ['month', 'Toată luna']] as const).map(([s, label]) => (
            <button
              key={s}
              type="button"
              onClick={() => setScope(s)}
              className={cn('flex-1 rounded-md text-[13px] font-medium transition-colors', scope === s ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground')}
            >
              {label}
            </button>
          ))}
        </div>

        {dayLists.length === 0 || dayLists.every((k) => (byDay.get(k)?.length ?? 0) === 0) ? (
          <p className="px-1 py-6 text-center text-sm text-muted-foreground">
            {scope === 'day' ? 'Nicio sesiune în această zi' : 'Nicio sesiune în această lună'}
          </p>
        ) : (
          <div className="max-h-[70vh] space-y-2.5 overflow-y-auto pr-1">
            {dayLists.map((k) => {
              const items = byDay.get(k) ?? []
              if (!items.length) return null
              return (
                <div key={k} className="space-y-1">
                  <p className="px-1 text-[11px] font-semibold uppercase capitalize tracking-wide text-muted-foreground">{dayLabel(k)}</p>
                  <div className="space-y-1">
                    {items.map((c) => (
                      <SessionRow
                        key={c.id}
                        contract={c}
                        vehicle={c.vin ? vinVehicle.get(c.vin) : undefined}
                        selected={c.id === selectedId}
                        onSelect={() => openSession(c)}
                        onDetail={() => onOpenDetail(c)}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function SessionRow({ contract: c, vehicle, selected, onSelect, onDetail }: {
  contract: FoiContract; vehicle?: FpVehicle; selected: boolean; onSelect: () => void; onDetail: () => void
}) {
  const ss = sessionStatus(c)
  const planned = ss.key === 'planificat'
  // Internal sessions have no client — the primary label is the driver.
  const primary = c.is_internal
    ? (c.advisor_name || '—')
    : (c.client_name || (c.client_id != null ? `Client #${c.client_id}` : '—'))
  return (
    <div
      role="button"
      tabIndex={0}
      draggable={planned}
      onDragStart={(e) => { e.dataTransfer.setData('text/plain', String(c.id)); e.dataTransfer.effectAllowed = 'move' }}
      onClick={onSelect}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } }}
      title={planned ? 'Trage pe o zi din calendar pentru a reprograma' : undefined}
      className={cn(
        'flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left transition-colors',
        selected ? 'border-blue-500/60 ring-1 ring-blue-500/50 bg-blue-500/5' : 'border-border/60 bg-card hover:bg-muted/40',
        planned && 'cursor-grab',
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] font-semibold">{primary}</span>
          <span className={cn('shrink-0 rounded-full px-1.5 py-0 text-[9px] font-semibold uppercase tracking-wide', ss.badgeClass)}>{ss.label}</span>
        </div>
        <div className="flex items-center gap-2.5 truncate text-[11px] text-muted-foreground">
          <span className="flex min-w-0 items-center gap-1 truncate">
            <Car className="h-3 w-3 shrink-0" />
            <span className="truncate">{carName(vehicle, c.vin)}</span>
          </span>
          <span className="shrink-0 tabular-nums">{periodOf(c)}</span>
        </div>
      </div>
      <button
        type="button"
        aria-label="Detalii sesiune"
        onClick={(e) => { e.stopPropagation(); onDetail() }}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  )
}
