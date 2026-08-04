import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Clock, AlertTriangle, CalendarDays, ChevronRight, MapPin } from 'lucide-react'
import { cn } from '@/lib/utils'
import { fieldSalesApi, type FSVisit } from '@/api/fieldSales'
import { VisitDetailDialog } from '@/pages/FieldSales/VisitDetailDialog'

const VISIT_TYPE_LABELS: Record<string, string> = {
  fleet_review: 'Revizuire flota', renewal_discussion: 'Discutie reinnoire',
  test_drive_followup: 'Follow-up test drive', service_followup: 'Follow-up service',
  new_acquisition: 'Achizitie noua', contract_negotiation: 'Negociere contract',
  prospecting: 'Prospectare', general: 'General',
}
const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
  planned: { label: 'PLANIFICATA', bg: 'bg-blue-100 dark:bg-blue-900/40', text: 'text-blue-700 dark:text-blue-300' },
  in_progress: { label: 'IN CURS', bg: 'bg-orange-100 dark:bg-orange-900/40', text: 'text-orange-700 dark:text-orange-300' },
  completed: { label: 'FINALIZATA', bg: 'bg-green-100 dark:bg-green-900/40', text: 'text-green-700 dark:text-green-300' },
  no_show: { label: 'NEPREZENTAT', bg: 'bg-red-100 dark:bg-red-900/40', text: 'text-red-700 dark:text-red-300' },
  rescheduled: { label: 'REPROGRAMATA', bg: 'bg-purple-100 dark:bg-purple-900/40', text: 'text-purple-700 dark:text-purple-300' },
  partial: { label: 'PARTIALA', bg: 'bg-amber-100 dark:bg-amber-900/40', text: 'text-amber-700 dark:text-amber-300' },
}
const todayStr = () => new Date().toISOString().split('T')[0]

function VisitCard({ visit, onOpen, onCheckIn, onFinalize, actionPending }: {
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

type Overlay = null | { kind: 'add' } | { kind: 'detail'; id: number }
  | { kind: 'note'; id: number } | { kind: 'client360'; clientId: number }

export default function HubFieldSalesPanel() {
  const date = todayStr()
  const [overlay, setOverlay] = useState<Overlay>(null)
  const { data, isLoading, isError } = useQuery({
    queryKey: ['field-sales-visits', date],
    queryFn: () => fieldSalesApi.getTodayVisits(date),
  })
  const visits = data?.visits ?? []
  const planned = visits.filter(v => v.status === 'planned').length
  const inProgress = visits.filter(v => v.status === 'in_progress').length
  const completed = visits.filter(v => v.status === 'completed').length

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h2 className="text-xl font-bold">Vizite</h2><p className="text-sm text-muted-foreground">Azi</p></div>
        <button onClick={() => setOverlay({ kind: 'add' })} className="rounded-xl bg-teal-600 px-3 py-2.5 text-sm font-semibold text-white active:bg-teal-700">
          <span className="flex items-center gap-1"><Plus className="h-4 w-4" />Adauga</span>
        </button>
      </div>

      {visits.length > 0 && (
        <div className="flex gap-2">
          <div className="flex-1 rounded-xl bg-blue-50 dark:bg-blue-900/20 p-3 text-center"><p className="text-lg font-bold text-blue-700 dark:text-blue-300">{planned}</p><p className="text-[10px] font-medium uppercase text-blue-600/70">Planificate</p></div>
          <div className="flex-1 rounded-xl bg-orange-50 dark:bg-orange-900/20 p-3 text-center"><p className="text-lg font-bold text-orange-700 dark:text-orange-300">{inProgress}</p><p className="text-[10px] font-medium uppercase text-orange-600/70">In curs</p></div>
          <div className="flex-1 rounded-xl bg-green-50 dark:bg-green-900/20 p-3 text-center"><p className="text-lg font-bold text-green-700 dark:text-green-300">{completed}</p><p className="text-[10px] font-medium uppercase text-green-600/70">Finalizate</p></div>
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

      {!isLoading && !isError && visits.length > 0 && (
        <div className="space-y-3">
          {visits.map(v => (
            <VisitCard key={v.id} visit={v} actionPending={false}
              onOpen={() => setOverlay({ kind: 'detail', id: v.id })}
              onCheckIn={() => { /* Task 5 */ }}
              onFinalize={() => setOverlay({ kind: 'note', id: v.id })} />
          ))}
        </div>
      )}

      {/* Detail overlay (reuse existing dialog) */}
      <VisitDetailDialog
        visitId={overlay?.kind === 'detail' ? overlay.id : null}
        open={overlay?.kind === 'detail'}
        onOpenChange={(o) => { if (!o) setOverlay(null) }}
      />
    </div>
  )
}
