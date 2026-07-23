import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend,
} from 'recharts'
import { toast } from 'sonner'
import { ChevronLeft, ChevronRight, EyeOff, CheckCircle2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import {
  eval360Reports, RELATIONSHIP_LABEL, JOHARI_LABEL,
  type ReportHeader, type CompetencyAgg,
} from '@/api/evaluation360'

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

  const agg = report.aggregates_by_relationship
  const comps = agg?.competencies ?? []
  const radarData = comps.map((c) => ({
    competency: c.competency_name ?? `#${c.competency_id}`,
    self: c.self,
    others: c.others,
  }))
  const byJohari = (key: string) => comps.filter((c) => c.johari === key)

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

      {/* Hidden-category notices */}
      {agg?.hidden_relationships?.length > 0 && (
        <Card><CardContent className="flex items-start gap-2 py-3 text-sm text-muted-foreground">
          <EyeOff className="h-4 w-4 mt-0.5 shrink-0" />
          <span>Defalcarea pe {agg.hidden_relationships.map((r) => RELATIONSHIP_LABEL[r] ?? r).join(', ')} este ascunsă — sub 3 răspunsuri (anonimat păstrat).</span>
        </CardContent></Card>
      )}

      {/* Radar: self vs others */}
      {radarData.length >= 3 && (
        <Card><CardContent className="py-4">
          <p className="text-sm font-semibold mb-2">Autoevaluare vs. ceilalți</p>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData} outerRadius="72%">
                <PolarGrid />
                <PolarAngleAxis dataKey="competency" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis domain={[1, 5]} tick={{ fontSize: 10 }} />
                <Radar name="Eu" dataKey="self" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} />
                <Radar name="Ceilalți" dataKey="others" stroke="#22c55e" fill="#22c55e" fillOpacity={0.2} />
                <Legend />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </CardContent></Card>
      )}

      {/* Gap chips */}
      <Card><CardContent className="py-4">
        <p className="text-sm font-semibold mb-3">Diferența autoevaluare — ceilalți</p>
        <div className="space-y-2">
          {comps.map((c) => <GapRow key={c.competency_id} c={c} />)}
        </div>
      </CardContent></Card>

      {/* Johari quadrants */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {(['confirmed_strength', 'blind_spot', 'hidden_strength', 'agreed_growth'] as const).map((key) => {
          const items = byJohari(key)
          return (
            <Card key={key}><CardContent className="py-3">
              <p className={cn('text-xs font-semibold uppercase tracking-wide mb-1.5',
                key === 'confirmed_strength' ? 'text-green-600'
                  : key === 'blind_spot' ? 'text-amber-600'
                    : key === 'hidden_strength' ? 'text-blue-600' : 'text-red-600')}>
                {JOHARI_LABEL[key]}
              </p>
              {items.length ? (
                <ul className="space-y-0.5">
                  {items.map((c) => <li key={c.competency_id} className="text-sm">{c.competency_name ?? `#${c.competency_id}`}</li>)}
                </ul>
              ) : <p className="text-xs text-muted-foreground">—</p>}
            </CardContent></Card>
          )
        })}
      </div>

      {/* Manager summary */}
      {report.manager_summary && (
        <Card><CardContent className="py-4">
          <p className="text-sm font-semibold mb-1">Rezumatul managerului</p>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{report.manager_summary}</p>
        </CardContent></Card>
      )}
    </div>
  )
}

function GapRow({ c }: { c: CompetencyAgg }) {
  const gap = c.gap
  const flagged = gap != null && Math.abs(gap) >= 1.0
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="min-w-0 truncate text-sm">{c.competency_name ?? `#${c.competency_id}`}</span>
      <div className="flex items-center gap-3 shrink-0 text-sm tabular-nums">
        <span className="text-muted-foreground">eu {c.self ?? '—'}</span>
        <span className="text-muted-foreground">ceilalți {c.others ?? '—'}</span>
        <Badge variant="outline" className={cn('tabular-nums', flagged ? 'text-amber-600 border-amber-200' : 'text-muted-foreground')}>
          {gap == null ? '—' : `${gap > 0 ? '+' : ''}${gap}`}
        </Badge>
      </div>
    </div>
  )
}
