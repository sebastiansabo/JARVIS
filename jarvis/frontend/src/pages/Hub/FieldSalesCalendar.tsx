import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { fieldSalesApi, type FSVisit } from '@/api/fieldSales'
import { STATUS_CONFIG, VISIT_TYPE_LABELS } from '@/pages/Hub/HubFieldSalesPanel'

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

/**
 * Month-only calendar for the Hub Field Sales panel — a web port of
 * DrivingCalendar's month grid (day/week views and the foiParcurs vehicle
 * join are dropped; visits carry everything needed for display already).
 * Shows the signed-in KAM's own visits (fieldSalesApi.getMyVisits) grouped
 * by planned_date; tapping a listed visit opens the shared detail overlay
 * via `onOpen`.
 */
export default function FieldSalesCalendar({ onOpen }: { onOpen: (visitId: number) => void }) {
  const [anchor, setAnchor] = useState<Date>(() => new Date())
  const [picked, setPicked] = useState<string | null>(null)

  const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const gridStart = startOfWeek(monthStart)
  const gridStartKey = keyOf(gridStart)
  const monthCells = useMemo(() => Array.from({ length: 42 }, (_, i) => addDays(gridStart, i)), [gridStartKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading, isError } = useQuery({
    queryKey: ['field-sales-cal', gridStartKey],
    queryFn: () => fieldSalesApi.getMyVisits(gridStartKey, keyOf(addDays(gridStart, 41))),
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

  const go = (dir: 1 | -1) => { setAnchor((a) => addMonths(a, dir)); setPicked(null) }
  const goToday = () => { setAnchor(new Date()); setPicked(null) }

  return (
    <div className="space-y-3">
      {/* Period navigation */}
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => go(-1)} className="flex h-9 w-9 items-center justify-center rounded-full bg-muted transition-colors hover:bg-muted/70"><ChevronLeft className="h-5 w-5" /></button>
        <p className="flex-1 text-center text-sm font-semibold capitalize">{anchor.toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })}</p>
        <button type="button" onClick={() => go(1)} className="flex h-9 w-9 items-center justify-center rounded-full bg-muted transition-colors hover:bg-muted/70"><ChevronRight className="h-5 w-5" /></button>
        <button type="button" onClick={goToday} className="rounded-full bg-muted px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-muted/70">Azi</button>
      </div>

      {isLoading ? (
        <div className="space-y-2.5">{[...Array(3)].map((_, i) => <div key={i} className="h-16 animate-pulse rounded-2xl bg-muted" />)}</div>
      ) : isError ? (
        <p className="py-8 text-center text-sm text-destructive">Nu s-a putut încărca calendarul.</p>
      ) : (
        <>
          <div className="rounded-2xl border border-border/60 bg-card p-2">
            <div className="grid grid-cols-7">
              {WEEKDAY_LABELS.map((w) => <div key={w} className="py-1 text-center text-[10px] font-semibold text-muted-foreground">{w}</div>)}
              {monthCells.map((d) => {
                const k = keyOf(d)
                const inMonth = d.getMonth() === anchor.getMonth()
                const dayVisits = byDay.get(k) ?? []
                return (
                  <button
                    key={k}
                    type="button"
                    data-testid={`day-${k}`}
                    onClick={() => setPicked(k)}
                    className={cn(
                      'relative flex aspect-square flex-col items-center justify-center gap-0.5 rounded-lg text-sm',
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
                  </button>
                )
              })}
            </div>
          </div>

          <div className="space-y-2">
            <p className="px-1 text-xs font-semibold uppercase capitalize tracking-wide text-muted-foreground">{dayLabel(activeKey)}</p>
            {activeVisits.length === 0 ? (
              <p className="px-1 py-4 text-center text-sm text-muted-foreground">Nicio vizita in aceasta zi</p>
            ) : (
              <div className="space-y-2">
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
