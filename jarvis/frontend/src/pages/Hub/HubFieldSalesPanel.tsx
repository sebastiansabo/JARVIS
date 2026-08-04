import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Clock, AlertTriangle, CalendarDays, ChevronRight, MapPin, X, Search } from 'lucide-react'
import { cn, usePersistedState } from '@/lib/utils'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { fieldSalesApi, type FSVisit, type FSClientSearch } from '@/api/fieldSales'
import { VisitDetailDialog } from '@/pages/FieldSales/VisitDetailDialog'
import NoteCaptureModal from '@/pages/FieldSales/NoteCaptureModal'
import ClientCard360 from '@/pages/FieldSales/ClientCard360'
import FieldSalesCalendar from '@/pages/Hub/FieldSalesCalendar'

export const VISIT_TYPE_LABELS: Record<string, string> = {
  fleet_review: 'Revizuire flota', renewal_discussion: 'Discutie reinnoire',
  test_drive_followup: 'Follow-up test drive', service_followup: 'Follow-up service',
  new_acquisition: 'Achizitie noua', contract_negotiation: 'Negociere contract',
  prospecting: 'Prospectare', general: 'General',
}
export const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string; dot: string }> = {
  planned: { label: 'PLANIFICATA', bg: 'bg-blue-100 dark:bg-blue-900/40', text: 'text-blue-700 dark:text-blue-300', dot: 'bg-blue-500' },
  in_progress: { label: 'IN CURS', bg: 'bg-orange-100 dark:bg-orange-900/40', text: 'text-orange-700 dark:text-orange-300', dot: 'bg-orange-500' },
  completed: { label: 'FINALIZATA', bg: 'bg-green-100 dark:bg-green-900/40', text: 'text-green-700 dark:text-green-300', dot: 'bg-green-500' },
  no_show: { label: 'NEPREZENTAT', bg: 'bg-red-100 dark:bg-red-900/40', text: 'text-red-700 dark:text-red-300', dot: 'bg-red-500' },
  rescheduled: { label: 'REPROGRAMATA', bg: 'bg-purple-100 dark:bg-purple-900/40', text: 'text-purple-700 dark:text-purple-300', dot: 'bg-purple-500' },
  partial: { label: 'PARTIALA', bg: 'bg-amber-100 dark:bg-amber-900/40', text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500' },
}
const todayStr = () => new Date().toISOString().split('T')[0]

// Shift a "YYYY-MM-DD" date string by `days` (no time component involved, so
// no timezone/naiveDate handling is needed — unlike DrivingCalendar's fields).
function addDaysStr(base: string, days: number): string {
  const d = new Date(`${base}T00:00:00`)
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function upcomingDateLabel(dateStr: string): string {
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit', month: 'short' })
}
// Default a chosen start time's implied end time to start+1h (capped at
// 23:59) — used to prefill Sfarsit in AddVisitForm when only a start time
// has been picked.
function addHour(t: string): string {
  const [h, m] = t.split(':').map(Number)
  const total = Math.min(h * 60 + m + 60, 23 * 60 + 59)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

export function VisitCard({ visit, onOpen, onCheckIn, onFinalize, actionPending }: {
  visit: FSVisit; onOpen: () => void; onCheckIn: () => void; onFinalize: () => void; actionPending: boolean
}) {
  const cfg = STATUS_CONFIG[visit.status] ?? STATUS_CONFIG.planned
  const showRenewal = (visit.renewal_score ?? 0) > 60
  return (
    <div onClick={onOpen} className="rounded-2xl bg-card border p-4 active:scale-[0.98] transition-transform cursor-pointer">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold truncate">{visit.client_name}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{VISIT_TYPE_LABELS[visit.visit_type] ?? visit.visit_type}</p>
        </div>
        <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide', cfg.bg, cfg.text)}>{cfg.label}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mb-3">
        {visit.planned_time && <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{visit.planned_time.slice(0,5)}</span>}
        {showRenewal && <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium"><AlertTriangle className="h-3.5 w-3.5" />Reinnoire {visit.renewal_score}%</span>}
      </div>
      {visit.goals && <p className="text-xs text-muted-foreground line-clamp-2 mb-3">{visit.goals}</p>}
      <div className="flex items-center justify-between">
        {visit.status === 'planned' && (
          <button onClick={(e) => { e.stopPropagation(); onCheckIn() }} disabled={actionPending}
            className="rounded-xl bg-teal-600 px-3 py-2.5 text-sm font-semibold text-white active:bg-teal-700 transition-colors disabled:opacity-50">
            <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4" />CHECK-IN</span>
          </button>
        )}
        {visit.status === 'in_progress' && (
          <button onClick={(e) => { e.stopPropagation(); onFinalize() }} disabled={actionPending}
            className="rounded-xl bg-orange-600 px-3 py-2.5 text-sm font-semibold text-white active:bg-orange-700 transition-colors disabled:opacity-50">
            Finalizeaza
          </button>
        )}
        {visit.status === 'completed' && <span className="text-xs text-green-600 dark:text-green-400 font-medium">Vizita finalizata</span>}
        <ChevronRight className="h-4 w-4 text-muted-foreground ml-auto" />
      </div>
    </div>
  )
}

// iOS-style fixed-inset sheet, ported from HubDrivingPanel — full-screen on
// phones, a centered floating card on desktop. Reused by every overlay kind.
function OverlaySheet({ onClose, children, wide }: { onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm">
      <div className={cn(
        'mx-auto min-h-full w-full bg-background shadow-2xl sm:my-8 sm:min-h-0 sm:rounded-2xl',
        // min-w only kicks in at >=1120px so it can never exceed max-w-[1120px] —
        // viewports 1024–1119px (e.g. iPad landscape) just fill width, no overflow.
        wide ? 'max-w-[1120px] min-[1120px]:min-w-[1080px]' : 'max-w-2xl',
      )}>
        <div className="sticky top-0 z-10 flex items-center justify-end border-b bg-background/95 p-2 backdrop-blur sm:rounded-t-2xl">
          <button onClick={onClose} className="rounded-full p-2 hover:bg-muted"><X className="h-5 w-5" /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

function AddVisitForm({ initialDate, initialTime, initialEndTime, onDone, onCancel }: {
  initialDate?: string; initialTime?: string; initialEndTime?: string; onDone: () => void; onCancel: () => void
}) {
  const [query, setQuery] = useState('')
  const [selectedClient, setSelectedClient] = useState<FSClientSearch | null>(null)
  const [showResults, setShowResults] = useState(false)
  const [visitDate, setVisitDate] = useState(initialDate ?? todayStr())
  const [time, setTime] = useState(initialTime ?? '')
  const [endTime, setEndTime] = useState(initialEndTime ?? '')
  const [visitType, setVisitType] = useState('general')
  const [goals, setGoals] = useState('')

  const { data: searchData, isLoading: searching } = useQuery({
    queryKey: ['fs-client-search', query],
    queryFn: () => fieldSalesApi.searchClients(query),
    enabled: query.length >= 2,
  })
  const results = searchData?.clients ?? []

  const createVisit = useMutation({
    mutationFn: fieldSalesApi.createVisit,
    onSuccess: () => onDone(),
  })

  const handleSelectClient = (client: FSClientSearch) => {
    setSelectedClient(client)
    setQuery(client.display_name)
    setShowResults(false)
  }

  const handleSubmit = () => {
    if (!selectedClient) return
    createVisit.mutate({
      client_id: selectedClient.id,
      planned_date: visitDate,
      planned_time: time || undefined,
      planned_end_time: endTime || undefined,
      visit_type: visitType,
      goals: goals || undefined,
    })
  }

  const err = createVisit.error as { data?: { error?: string } } | null

  return (
    <div className="space-y-4 p-4 pb-8">
      <h3 className="text-lg font-bold">Adauga vizita</h3>

      <div>
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 block">Client *</label>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelectedClient(null); setShowResults(true) }}
            onFocus={() => query.length >= 2 && setShowResults(true)}
            placeholder="Cauta client dupa nume sau CUI..."
            className="h-11 w-full rounded-xl border border-border bg-background pl-9 pr-9 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-teal-600/40"
          />
          {query && (
            <button
              onClick={() => { setQuery(''); setSelectedClient(null); setShowResults(false) }}
              className="absolute right-3 top-1/2 -translate-y-1/2"
            >
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          )}
        </div>
        {showResults && query.length >= 2 && (
          <div className="mt-1 max-h-48 overflow-y-auto rounded-xl border border-border bg-card shadow-lg">
            {searching && (
              <div className="flex items-center justify-center py-4">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
              </div>
            )}
            {!searching && results.length === 0 && (
              <p className="px-3 py-3 text-xs text-muted-foreground">Niciun client gasit</p>
            )}
            {!searching && results.map((c) => (
              <button
                key={c.id}
                onClick={() => handleSelectClient(c)}
                className="w-full text-left px-3 py-2.5 hover:bg-secondary active:bg-secondary transition-colors border-b border-border/50 last:border-0"
              >
                <p className="text-sm font-medium">{c.display_name}</p>
                <p className="text-xs text-muted-foreground">
                  {c.client_type === 'company' ? 'Firma' : 'Persoana fizica'}
                  {c.city ? ` - ${c.city}` : ''}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 block">Data vizitei</label>
        <input
          type="date"
          value={visitDate}
          onChange={(e) => setVisitDate(e.target.value)}
          className="h-11 w-full rounded-xl border border-border bg-background px-3 text-base focus:outline-none focus:ring-2 focus:ring-teal-600/40"
        />
      </div>

      <div>
        <label htmlFor="add-visit-time" className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 block">Ora (optional)</label>
        <input
          id="add-visit-time"
          type="time"
          value={time}
          onChange={(e) => {
            const newTime = e.target.value
            setTime(newTime)
            // Prefill a sensible default end time when none was chosen yet, or
            // the current end no longer makes sense after the start moved past it.
            if (newTime && (!endTime || endTime <= newTime)) {
              setEndTime(addHour(newTime))
            }
          }}
          className="h-11 w-full rounded-xl border border-border bg-background px-3 text-base focus:outline-none focus:ring-2 focus:ring-teal-600/40"
        />
      </div>

      <div>
        <label htmlFor="add-visit-end-time" className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 block">Sfarsit (optional)</label>
        <input
          id="add-visit-end-time"
          type="time"
          value={endTime}
          onChange={(e) => setEndTime(e.target.value)}
          className="h-11 w-full rounded-xl border border-border bg-background px-3 text-base focus:outline-none focus:ring-2 focus:ring-teal-600/40"
        />
      </div>

      <div>
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 block">Tip vizita</label>
        <select
          value={visitType}
          onChange={(e) => setVisitType(e.target.value)}
          className="h-11 w-full rounded-xl border border-border bg-background px-3 text-base focus:outline-none focus:ring-2 focus:ring-teal-600/40 appearance-none"
        >
          {Object.entries(VISIT_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5 block">Obiective (optional)</label>
        <textarea
          value={goals}
          onChange={(e) => setGoals(e.target.value)}
          placeholder="Obiectivele vizitei..."
          rows={3}
          className="w-full rounded-xl border border-border bg-background py-2.5 px-3 text-base placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-2 focus:ring-teal-600/40"
        />
      </div>

      <div className="flex gap-2">
        <button onClick={onCancel} className="h-11 flex-1 rounded-xl border border-border text-base font-semibold active:bg-muted">
          Anuleaza
        </button>
        <button
          onClick={handleSubmit}
          disabled={!selectedClient || createVisit.isPending}
          className={cn(
            'h-11 flex-1 rounded-xl text-base font-semibold text-white transition-colors',
            selectedClient && !createVisit.isPending ? 'bg-teal-600 active:bg-teal-700' : 'bg-muted-foreground/40 cursor-not-allowed',
          )}
        >
          {createVisit.isPending ? 'Se salveaza...' : 'Salveaza vizita'}
        </button>
      </div>

      {createVisit.isError && (
        <p className="text-xs text-destructive text-center">{err?.data?.error ?? 'Eroare la salvarea vizitei'}</p>
      )}
    </div>
  )
}

type Overlay = null | { kind: 'add'; date?: string; time?: string; endTime?: string } | { kind: 'detail'; id: number }
  | { kind: 'note'; id: number } | { kind: 'client360'; clientId: number; clientName?: string }
type PanelTab = 'today' | 'calendar'

export default function HubFieldSalesPanel() {
  const date = todayStr()
  const upcomingFrom = addDaysStr(date, 1)
  const upcomingTo = addDaysStr(date, 30)
  const [tab, setTab] = usePersistedState<PanelTab>('hub-fs-tab', 'today')
  const [overlay, setOverlay] = useState<Overlay>(null)
  const queryClient = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['field-sales-visits', date],
    queryFn: () => fieldSalesApi.getTodayVisits(date),
  })
  const visits = data?.visits ?? []
  const planned = visits.filter(v => v.status === 'planned').length
  const inProgress = visits.filter(v => v.status === 'in_progress').length
  const completed = visits.filter(v => v.status === 'completed').length

  const { data: upcomingData } = useQuery({
    queryKey: ['field-sales-mine', upcomingFrom, upcomingTo],
    queryFn: () => fieldSalesApi.getMyVisits(upcomingFrom, upcomingTo),
  })
  const upcoming = (upcomingData?.visits ?? []).filter(v => v.status === 'planned' || v.status === 'in_progress')

  const invalidateVisitLists = () => {
    queryClient.invalidateQueries({ queryKey: ['field-sales-visits', date] })
    queryClient.invalidateQueries({ queryKey: ['field-sales-mine', upcomingFrom, upcomingTo] })
    queryClient.invalidateQueries({ queryKey: ['field-sales-cal'] })
  }

  // Tracks the visit currently acquiring geolocation for check-in. getCoords()
  // awaits up to a 5s geolocation timeout (or an open permission prompt)
  // BEFORE checkinMut.mutate() is called, so checkinMut.isPending alone can't
  // guard against rapid repeat taps during that window — this closes the gap.
  const [checkingInId, setCheckingInId] = useState<number | null>(null)

  const checkinMut = useMutation({
    mutationFn: ({ id, coords }: { id: number; coords: { lat?: number; lng?: number } }) => fieldSalesApi.checkin(id, coords),
    onSuccess: (_res, vars) => {
      invalidateVisitLists()
      setOverlay({ kind: 'detail', id: vars.id })
    },
    onSettled: () => setCheckingInId(null),
  })
  const checkinErr = checkinMut.error as { data?: { error?: string } } | null

  function getCoords(): Promise<{ lat?: number; lng?: number }> {
    return new Promise((resolve) => {
      if (!('geolocation' in navigator)) return resolve({})
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => resolve({}),
        { timeout: 5000 },
      )
    })
  }

  const handleCheckIn = async (visit: FSVisit) => {
    if (checkingInId !== null) return
    setCheckingInId(visit.id)
    const coords = await getCoords()
    checkinMut.mutate({ id: visit.id, coords })
  }

  return (
    <div className="space-y-4">
      <Tabs value={tab} onValueChange={(v) => setTab(v as PanelTab)}>
        <TabsList>
          <TabsTrigger value="today">Azi</TabsTrigger>
          <TabsTrigger value="calendar">Calendar</TabsTrigger>
        </TabsList>
      </Tabs>

      {tab === 'today' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div><h2 className="text-xl font-bold">Vizite</h2><p className="text-sm text-muted-foreground">Azi</p></div>
            <button onClick={() => setOverlay({ kind: 'add' })} className="rounded-xl bg-teal-600 px-3 py-2.5 text-sm font-semibold text-white active:bg-teal-700">
              <span className="flex items-center gap-1"><Plus className="h-4 w-4" />Adauga</span>
            </button>
          </div>

          {visits.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-xl bg-blue-50 dark:bg-blue-900/20 p-3 text-center"><p className="text-lg font-bold text-blue-700 dark:text-blue-300">{planned}</p><p className="text-[10px] font-medium uppercase text-blue-600/70">Planificate</p></div>
              <div className="rounded-xl bg-orange-50 dark:bg-orange-900/20 p-3 text-center"><p className="text-lg font-bold text-orange-700 dark:text-orange-300">{inProgress}</p><p className="text-[10px] font-medium uppercase text-orange-600/70">In curs</p></div>
              <div className="rounded-xl bg-green-50 dark:bg-green-900/20 p-3 text-center"><p className="text-lg font-bold text-green-700 dark:text-green-300">{completed}</p><p className="text-[10px] font-medium uppercase text-green-600/70">Finalizate</p></div>
            </div>
          )}

          {isLoading && <div className="flex justify-center py-16"><div className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" /></div>}
          {isError && <p className="py-16 text-center text-sm text-muted-foreground">Nu s-au putut incarca vizitele</p>}
          {!isLoading && !isError && visits.length === 0 && (
            <div className="flex flex-col items-center py-16">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted/50 mb-4"><CalendarDays className="h-8 w-8 text-muted-foreground" /></div>
              <p className="text-base font-semibold mb-1">Nicio vizita planificata</p>
              <p className="text-sm text-muted-foreground text-center max-w-[240px]">Adauga o vizita noua pentru a incepe planificarea zilei</p>
            </div>
          )}

          {checkinMut.isError && (
            <p className="text-xs text-destructive text-center">{checkinErr?.data?.error ?? 'Eroare la check-in'}</p>
          )}

          {!isLoading && !isError && visits.length > 0 && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {visits.map(v => (
                <VisitCard key={v.id} visit={v} actionPending={checkingInId === v.id || checkinMut.isPending}
                  onOpen={() => setOverlay({ kind: 'detail', id: v.id })}
                  onCheckIn={() => handleCheckIn(v)}
                  onFinalize={() => setOverlay({ kind: 'note', id: v.id })} />
              ))}
            </div>
          )}

          {upcoming.length > 0 && (
            <div className="space-y-3 pt-2">
              <h3 className="text-sm font-semibold text-muted-foreground">Vizite viitoare (30 zile)</h3>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {upcoming.map(v => (
                  <div key={v.id}>
                    <p className="mb-1 px-1 text-xs font-medium capitalize text-muted-foreground">{upcomingDateLabel(v.planned_date)}</p>
                    <VisitCard visit={v} actionPending={checkingInId === v.id || checkinMut.isPending}
                      onOpen={() => setOverlay({ kind: 'detail', id: v.id })}
                      onCheckIn={() => handleCheckIn(v)}
                      onFinalize={() => setOverlay({ kind: 'note', id: v.id })} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'calendar' && (
        <FieldSalesCalendar
          onOpen={(id) => setOverlay({ kind: 'detail', id })}
          onAdd={(date, time, endTime) => setOverlay({ kind: 'add', date, time, endTime })}
        />
      )}

      {/* Detail overlay (reuse existing dialog). VisitDetailDialog's own
          updateMutation only invalidates its own detail query + the manager
          overview, not the Hub's lists — so refresh those here on close, or
          an in-dialog edit (status/date/type/outcome) leaves the today list,
          stat tiles, upcoming list and calendar showing stale data. */}
      <VisitDetailDialog
        visitId={overlay?.kind === 'detail' ? overlay.id : null}
        open={overlay?.kind === 'detail'}
        onOpenChange={(o) => { if (!o) { setOverlay(null); invalidateVisitLists() } }}
        onOpenClient360={(clientId, clientName) => setOverlay({ kind: 'client360', clientId, clientName })}
      />

      {overlay?.kind === 'client360' && (
        <OverlaySheet wide onClose={() => setOverlay(null)}>
          <ClientCard360 clientId={overlay.clientId} clientName={overlay.clientName} />
        </OverlaySheet>
      )}

      {overlay?.kind === 'add' && (
        <OverlaySheet onClose={() => setOverlay(null)}>
          <AddVisitForm
            initialDate={overlay.date}
            initialTime={overlay.time}
            initialEndTime={overlay.endTime}
            onDone={() => { invalidateVisitLists(); setOverlay(null) }}
            onCancel={() => setOverlay(null)}
          />
        </OverlaySheet>
      )}

      {/* Note-capture / finalize-with-AI-structured-note overlay. The /note
          endpoint completes the visit server-side, so saving here IS the
          finalize action triggered by the card's "Finalizeaza" button. */}
      {overlay?.kind === 'note' && (() => {
        const v = visits.find(x => x.id === overlay.id) ?? upcoming.find(x => x.id === overlay.id)
        return (
          <OverlaySheet onClose={() => setOverlay(null)}>
            <NoteCaptureModal
              visitId={overlay.id}
              clientId={v?.client_id ?? 0}
              onDone={() => { invalidateVisitLists(); setOverlay(null) }}
              onCancel={() => setOverlay(null)}
            />
          </OverlaySheet>
        )
      })()}
    </div>
  )
}
