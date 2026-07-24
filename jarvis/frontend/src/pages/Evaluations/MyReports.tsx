import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronLeft, ChevronRight, CheckCircle2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuthStore } from '@/stores/authStore'
import { eval360Reports, type ReportHeader } from '@/api/evaluation360'
import { ReportView } from './ReportView'
import { DevPlan } from './DevPlan'

export default function MyReports() {
  const [cycleId, setCycleId] = useState<number | null>(null)
  const q = useQuery({ queryKey: ['eval360-my-reports'], queryFn: () => eval360Reports.myReports() })
  const reports = q.data?.reports ?? []

  if (cycleId != null) return <ReportDetail cycleId={cycleId} onBack={() => setCycleId(null)} />

  if (q.isLoading) return <div className="space-y-2">{[0, 1].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
  if (!reports.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted"><CheckCircle2 className="h-7 w-7 text-muted-foreground/50" /></div>
        <p className="text-sm font-medium">Niciun raport disponibil încă</p>
        <p className="text-sm text-muted-foreground">Rapoartele apar aici după ce sunt publicate.</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border divide-y">
      {reports.map((r: ReportHeader) => (
        <button key={r.id} onClick={() => setCycleId(r.cycle_id)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted/50">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{r.cycle_name}</p>
            <p className="text-xs text-muted-foreground">Publicat {r.released_at?.slice(0, 10)}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {r.acknowledged_at
              ? <Badge variant="secondary" className="text-green-600">Confirmat</Badge>
              : <Badge variant="outline" className="text-amber-600 border-amber-200">Necitit</Badge>}
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </div>
        </button>
      ))}
    </div>
  )
}

function ReportDetail({ cycleId, onBack }: { cycleId: number; onBack: () => void }) {
  const qc = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id)
  const q = useQuery({ queryKey: ['eval360-report', cycleId], queryFn: () => eval360Reports.myReport(cycleId) })
  const report = q.data?.report

  const ackM = useMutation({
    mutationFn: (id: number) => eval360Reports.acknowledge(id),
    onSuccess: () => {
      toast.success('Raport confirmat')
      qc.invalidateQueries({ queryKey: ['eval360-report', cycleId] })
      qc.invalidateQueries({ queryKey: ['eval360-my-reports'] })
    },
  })

  if (q.isLoading) return <Skeleton className="h-72 w-full" />
  if (q.isError || !report) return <p className="py-12 text-center text-sm text-muted-foreground">Raportul nu este disponibil.</p>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
          <ChevronLeft className="h-4 w-4" /> Rapoartele mele
        </button>
        {!report.acknowledged_at && (
          <Button size="sm" disabled={ackM.isPending} onClick={() => ackM.mutate(report.id)}>
            <CheckCircle2 className="h-4 w-4 mr-1" /> Confirm primirea
          </Button>
        )}
      </div>
      <ReportView report={report} />
      {userId && (
        <DevPlan
          cycleId={report.cycle_id}
          employeeId={userId}
          competencies={(report.aggregates_by_relationship?.competencies ?? []).map((c) => ({ id: c.competency_id, name: c.competency_name ?? `#${c.competency_id}` }))}
        />
      )}
    </div>
  )
}
