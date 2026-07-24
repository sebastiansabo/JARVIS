import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronLeft, ChevronRight, Send, Save, CalendarClock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { eval360Reports, type TeamReportHeader } from '@/api/evaluation360'
import { ReportView } from './ReportView'

const MIN = 300
const MAX = 1500

export default function TeamReports() {
  const [reportId, setReportId] = useState<number | null>(null)
  const q = useQuery({ queryKey: ['eval360-team-reports'], queryFn: () => eval360Reports.teamReports() })
  const reports = q.data?.reports ?? []

  if (reportId != null) return <Calibration reportId={reportId} onBack={() => setReportId(null)} />
  if (q.isLoading) return <div className="space-y-2">{[0, 1].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
  if (!reports.length) {
    return <p className="py-16 text-center text-sm text-muted-foreground">Nu ai rapoarte de echipă de calibrat.</p>
  }

  return (
    <div className="rounded-xl border divide-y">
      {reports.map((r: TeamReportHeader) => (
        <button key={r.id} onClick={() => setReportId(r.id)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted/50">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{r.employee_name}</p>
            <p className="text-xs text-muted-foreground">{r.cycle_name}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {r.needs_summary_backfill && <Badge variant="outline" className="text-red-600 border-red-200">Necesită rezumat</Badge>}
            {r.has_summary
              ? <Badge variant="secondary" className="text-green-600">Rezumat</Badge>
              : <Badge variant="outline" className="text-amber-600 border-amber-200">Fără rezumat</Badge>}
            {r.debrief_scheduled && <Badge variant="secondary" className="text-green-600">Debrief</Badge>}
            {r.released && <Badge variant="secondary">Publicat</Badge>}
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </div>
        </button>
      ))}
    </div>
  )
}

function Calibration({ reportId, onBack }: { reportId: number; onBack: () => void }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['eval360-manager-report', reportId], queryFn: () => eval360Reports.managerReport(reportId) })
  const report = q.data?.report
  const [summary, setSummary] = useState('')
  const [debriefAt, setDebriefAt] = useState('')

  useEffect(() => { if (report?.manager_summary) setSummary(report.manager_summary) }, [report])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['eval360-manager-report', reportId] })
    qc.invalidateQueries({ queryKey: ['eval360-team-reports'] })
  }
  const errMsg = (e: unknown) => e && typeof e === 'object' && 'data' in e ? String((e as { data?: { error?: string } }).data?.error ?? 'Eroare') : 'Eroare'
  const saveM = useMutation({
    mutationFn: () => eval360Reports.setSummary(reportId, summary),
    onSuccess: () => { toast.success('Rezumat salvat'); invalidate() },
    onError: (e: unknown) => toast.error(errMsg(e)),
  })
  const debriefM = useMutation({
    mutationFn: () => eval360Reports.scheduleDebrief(reportId, debriefAt || undefined),
    onSuccess: () => { toast.success('Debrief programat'); invalidate() },
    onError: (e: unknown) => toast.error(errMsg(e)),
  })
  const releaseM = useMutation({
    mutationFn: () => eval360Reports.managerRelease(reportId),
    onSuccess: () => { toast.success('Raport publicat'); invalidate(); onBack() },
    onError: (e: unknown) => toast.error(errMsg(e)),
  })

  if (q.isLoading) return <Skeleton className="h-72 w-full" />
  if (q.isError || !report) return <p className="py-12 text-center text-sm text-muted-foreground">Raportul nu este disponibil.</p>

  const released = !!report.released_at
  const len = summary.trim().length
  const summaryValid = len >= MIN && len <= MAX
  // Release gate mirrors the server (spec §5.5): saved valid summary + scheduled debrief.
  const summarySaved = !!report.manager_summary && report.manager_summary.trim().length >= MIN && report.manager_summary.trim().length <= MAX
  const debriefScheduled = !!report.debrief_scheduled_at
  const missing = [
    !summarySaved && 'salvează rezumatul (300–1500)',
    !debriefScheduled && 'programează un debrief',
  ].filter(Boolean) as string[]

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Calibrare echipă
      </button>

      <ReportView report={report} />

      {/* Manager summary (required 300–1500) */}
      <Card><CardContent className="py-4 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">Rezumatul managerului</p>
          <span className={cn('text-xs tabular-nums', summaryValid ? 'text-muted-foreground' : 'text-amber-600')}>{len}/{MAX}</span>
        </div>
        <Textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={6}
          disabled={released}
          placeholder="Context pentru conversația 1-la-1 (300–1500 caractere) — niciodată o modificare a scorurilor."
        />
        {!released && (
          <div className="flex justify-end">
            <Button size="sm" variant="outline" disabled={!summaryValid || saveM.isPending} onClick={() => saveM.mutate()}>
              <Save className="h-4 w-4 mr-1" /> Salvează rezumatul
            </Button>
          </div>
        )}
      </CardContent></Card>

      {/* Debrief scheduling (manager-gated release requires it) */}
      {!released && (
        <Card><CardContent className="py-4 space-y-2">
          <p className="text-sm font-semibold">Debrief</p>
          {debriefScheduled ? (
            <p className="text-sm text-green-600">
              Debrief programat: {new Date(report.debrief_scheduled_at as string).toLocaleString('ro-RO')}
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="datetime-local"
                value={debriefAt}
                onChange={(e) => setDebriefAt(e.target.value)}
                className="rounded-md border bg-background px-2 py-1 text-sm"
              />
              <Button size="sm" variant="outline" disabled={!debriefAt || debriefM.isPending} onClick={() => debriefM.mutate()}>
                <CalendarClock className="h-4 w-4 mr-1" /> Programează debrief
              </Button>
            </div>
          )}
        </CardContent></Card>
      )}

      {/* Release (manager-gated: requires a saved summary + a scheduled debrief) */}
      {released ? (
        <p className="text-sm text-green-600">Raport publicat către angajat.</p>
      ) : (
        <div className="flex flex-col items-end gap-1">
          {missing.length > 0 && (
            <span className="text-xs text-amber-600">Înainte de publicare: {missing.join(' · ')}</span>
          )}
          <Button disabled={missing.length > 0 || releaseM.isPending} onClick={() => releaseM.mutate()}>
            <Send className="h-4 w-4 mr-1" /> Publică raportul
          </Button>
        </div>
      )}
    </div>
  )
}
