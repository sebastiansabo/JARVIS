import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn, usePersistedState, useIsMobile } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FoiContract } from '@/types/foiParcurs'
import { sessionStatus, carColor, internalComment } from './sessionStatus'
import { naiveDate } from '@/lib/naiveDate'
import TimeGrid, { type TimeGridEvent } from '@/pages/Hub/TimeGrid'
import SessionDetailModal from '@/pages/Hub/SessionDetailModal'
import SessionTypeChooser from './SessionTypeChooser'
import MonthCalendar from './MonthCalendar'

type CalView = 'month' | 'week' | 'day'
const VIEW_OPTIONS: readonly [CalView, string][] = [['day', 'Zi'], ['week', 'Săptămână'], ['month', 'Lună']]

function dayKey(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function addDays(d: Date, n: number): Date { const x = new Date(d); x.setDate(x.getDate() + n); return x }
function startOfWeek(d: Date): Date { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x }
function minsOfDay(iso?: string | null): number | null {
  const d = naiveDate(iso)
  return d ? d.getHours() * 60 + d.getMinutes() : null
}

/** Calendar of planned/live/finished TD sessions, keyed on departure_datetime.
 *  Month renders the classic 42-cell grid; Week/Day render the shared
 *  <TimeGrid> (07:00–21:00) so the desktop matches the Hub / Field Sales look —
 *  clicking a block opens the same details dialog, and dragging/clicking empty
 *  grid space starts a new session prefilled at that slot. Data reuses the same
 *  ['foi-contracts-all', companyId, monthKey] query as SessionsTab (filtered
 *  client-side), so switching Sesiuni Driving ↔ Calendar doesn't refetch. */
export function CalendarTab({ companyId, brand }: { companyId: number; brand: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  // Persisted (survives navigating to the new-TD form and back) with Week default.
  const [view, setView] = usePersistedState<CalView>('fp-cal-view', 'week')
  const [cursor, setCursor] = useState(() => new Date())
  const [selected, setSelected] = useState<FoiContract | null>(null)
  const [carFilter, setCarFilter] = useState<string>('') // '' = all cars, else a vin
  // Slot-add (drag/click empty grid space) opens the Client/Intern chooser
  // before navigating, instead of always assuming a client test drive.
  const [slotChooser, setSlotChooser] = useState<{ departure: string; ret: string } | null>(null)
  const [weekOffset, setWeekOffset] = useState(0) // rolling 7-day window: slide by ±1 day

  // Fetch the visible month's range (± a week to cover the grid's leading/
  // trailing days, and any Week/Day view anchored in this month) so navigating
  // to PAST periods loads their (archived) sessions too — not just the
  // most-recently-created ones.
  const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  const rangeFrom = ymd(new Date(new Date(cursor.getFullYear(), cursor.getMonth(), 1).getTime() - 7 * 864e5))
  const rangeTo = ymd(new Date(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getTime() + 7 * 864e5))
  const monthKey = `${cursor.getFullYear()}-${cursor.getMonth()}`

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all', companyId, monthKey],
    queryFn: () =>
      foiParcursApi.getContracts({ company_id: companyId || undefined, route_type: 'TD', date_from: rangeFrom, date_to: rangeTo, per_page: 2000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(),
    staleTime: 30_000,
  })
  const vehiclesList = vehiclesData?.vehicles ?? []
  const vinBrand = new Map(vehiclesList.map((v) => [v.vin, v.brand]))
  const vinVehicle = new Map(vehiclesList.map((v) => [v.vin, v]))
  const carLabel = (vin: string) => {
    const v = vinVehicle.get(vin)
    return v ? [v.brand || v.mark, v.model].filter(Boolean).join(' ') : vin.slice(0, 8)
  }

  // Drag-to-reschedule (PLANNED only) — optimistic on the visible month's cache,
  // rolled back on error; backend re-guards status + past-date.
  const [moveErr, setMoveErr] = useState<string | null>(null)
  const contractsKey = ['foi-contracts-all', companyId, monthKey] as const
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
  const onMoveEvent = (id: number, dk: string, startTime: string, endTime: string) => {
    setMoveErr(null)
    rescheduleMut.mutate({ id, departure: `${dk}T${startTime}`, ret: `${dk}T${endTime}` })
  }
  // Month drag-to-day: keep the session's time, change only the date.
  const hhmm = (d: Date) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const rescheduleToDay = (id: number, targetKey: string) => {
    const c = byId.get(id)
    const dep = c && naiveDate(c.departure_datetime)
    if (!c || !dep) return
    if (dayKey(dep) === targetKey) return // dropped on same day — no-op
    const ret = naiveDate(c.return_datetime)
    onMoveEvent(id, targetKey, hhmm(dep), ret ? hhmm(ret) : hhmm(new Date(dep.getTime() + 3600000)))
  }

  const brandContracts = (data?.contracts ?? []).filter(
    (c) => c.route_type === 'TD' && c.departure_datetime && (!brand || vinBrand.get(c.vin) === brand),
  )
  const tdContracts = carFilter ? brandContracts.filter((c) => c.vin === carFilter) : brandContracts
  // Distinct cars (from the brand-filtered set, so the filter lists all cars).
  const carOptions = (() => {
    const seen = new Map<string, string>()
    for (const c of brandContracts) if (c.vin && !seen.has(c.vin)) seen.set(c.vin, carLabel(c.vin))
    return Array.from(seen, ([vin, label]) => ({ vin, label })).sort((a, b) => a.label.localeCompare(b.label))
  })()

  const byDay = useMemo(() => {
    const map = new Map<string, FoiContract[]>()
    for (const c of tdContracts) {
      const key = dayKey(naiveDate(c.departure_datetime)!)
      const list = map.get(key) ?? []
      list.push(c)
      map.set(key, list)
    }
    for (const list of map.values()) list.sort((a, b) => (a.departure_datetime || '').localeCompare(b.departure_datetime || ''))
    return map
  }, [tdContracts])
  const byId = useMemo(() => new Map(tdContracts.map((c) => [c.id, c] as const)), [tdContracts])

  // Week/Day columns + their time-grid events. Week is a rolling 7-day window
  // (weekOffset in days) so the arrows / edge-drag slide it a day at a time.
  const weekDays = useIsMobile() ? 3 : 7
  const weekStart = addDays(startOfWeek(cursor), weekOffset)
  const dayCols = view === 'day' ? [cursor] : view === 'week' ? Array.from({ length: weekDays }, (_, i) => addDays(weekStart, i)) : []
  // Sessions whose [departure, return] span intersects the visible window, so a
  // multi-day session that started earlier still shows on the days it covers.
  const rangeStart = dayCols.length ? dayKey(dayCols[0]) : ''
  const rangeEnd = dayCols.length ? dayKey(dayCols[dayCols.length - 1]) : ''
  const events: TimeGridEvent[] = view === 'month'
    ? []
    : tdContracts.flatMap((c): TimeGridEvent[] => {
        const dep = dayKey(naiveDate(c.departure_datetime)!)
        const retKey = naiveDate(c.return_datetime) ? dayKey(naiveDate(c.return_datetime)!) : undefined
        const spanEnd = retKey && retKey > dep ? retKey : dep
        if (dep > rangeEnd || spanEnd < rangeStart) return []
        return [{
          id: c.id,
          dayKey: dep,
          endDayKey: retKey, // multi-day span (return day)
          startMin: minsOfDay(c.departure_datetime),
          endMin: minsOfDay(c.return_datetime),
          color: carColor(c.vin), // colour by car
          groupKey: c.vin || undefined, // same-car overlap (interlaced) detection
          // Internal sessions have no client — the bold title is the driver
          // (advisor_name), and their comment takes the secondary line below.
          title: c.is_internal ? (c.advisor_name || carLabel(c.vin)) : (c.client_name || carLabel(c.vin)),
          subtitle: carLabel(c.vin),
          meta: c.is_internal ? (internalComment(c) ?? undefined) : undefined,
          draggable: sessionStatus(c).key === 'planificat', // only planned sessions reschedule
        }]
      })

  const go = (dir: 1 | -1) => {
    if (view === 'week') setWeekOffset((o) => o + dir) // slide the 7-day window one day
    else if (view === 'day') setCursor(addDays(cursor, dir))
    else setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + dir, 1))
  }

  let periodLabel: string
  if (view === 'day') {
    periodLabel = cursor.toLocaleDateString('ro-RO', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })
  } else if (view === 'week') {
    const we = addDays(weekStart, weekDays - 1)
    const weM = we.toLocaleDateString('ro-RO', { month: 'long' })
    periodLabel = weekStart.getMonth() === we.getMonth()
      ? `${weekStart.getDate()} – ${we.getDate()} ${weM}`
      : `${weekStart.getDate()} ${weekStart.toLocaleDateString('ro-RO', { month: 'long' })} – ${we.getDate()} ${weM}`
  } else {
    periodLabel = cursor.toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => go(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => { setCursor(new Date()); setWeekOffset(0) }}>Azi</Button>
          <Button variant="outline" size="icon" onClick={() => go(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <h3 className="text-base font-semibold capitalize ml-2">{periodLabel}</h3>
          {isLoading && <span className="text-xs text-muted-foreground">Se încarcă...</span>}
        </div>
        {/* Car filter (only when >1 car has sessions) */}
        {carOptions.length > 1 && (
          <Select value={carFilter || 'all'} onValueChange={(v) => setCarFilter(v === 'all' ? '' : v)}>
            <SelectTrigger className="h-9 w-44 text-sm" aria-label="Filtrează după mașină"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toate mașinile</SelectItem>
              {carOptions.map((o) => <SelectItem key={o.vin} value={o.vin}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        {/* View switcher — same segmented control as the Hub / Field Sales calendars. */}
        <div className="flex h-9 gap-0.5 rounded-lg bg-muted p-0.5">
          {VIEW_OPTIONS.map(([v, label]) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={cn('rounded-md px-3 text-sm font-medium transition-colors', view === v ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground')}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {view === 'month' ? (
        <MonthCalendar
          monthDate={cursor}
          byDay={byDay}
          vinVehicle={vinVehicle}
          onOpenDetail={setSelected}
          onAdd={(departure, ret) => setSlotChooser({ departure, ret })}
          onRescheduleToDay={rescheduleToDay}
          dayTestIdPrefix="fp-day"
        />
      ) : (
        <div className="space-y-1">
          {moveErr && <p className="px-1 text-xs text-destructive">{moveErr}</p>}
          <TimeGrid
            dayCols={dayCols}
            events={events}
            onEventClick={(id) => { const c = byId.get(id); if (c) setSelected(c) }}
            onSlotAdd={(departure, ret) => setSlotChooser({ departure, ret })}
            onMove={onMoveEvent}
            pxPerHour={72}
          />
        </div>
      )}

      {selected && (
        <SessionDetailModal
          session={selected}
          vehicle={vinVehicle.get(selected.vin)}
          onClose={() => setSelected(null)}
          onActivate={() => { const { id } = selected; setSelected(null); navigate(`/app/foi-parcurs/test-drive?activate=${id}`) }}
          onReturn={() => { const { id } = selected; setSelected(null); navigate(`/app/foi-parcurs/test-drive/${id}/return`) }}
        />
      )}

      <SessionTypeChooser
        open={!!slotChooser}
        onOpenChange={(o) => { if (!o) setSlotChooser(null) }}
        onPick={(type) => {
          if (!slotChooser) return
          const { departure, ret } = slotChooser
          setSlotChooser(null)
          navigate(type === 'client'
            ? `/app/foi-parcurs/test-drive?departure=${departure}&return=${ret}`
            : `/app/foi-parcurs/internal?departure=${departure}&return=${ret}`)
        }}
      />
    </div>
  )
}
