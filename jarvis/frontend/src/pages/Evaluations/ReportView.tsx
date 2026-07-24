import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend,
} from 'recharts'
import { EyeOff } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { RELATIONSHIP_LABEL, JOHARI_LABEL, type Report, type CompetencyAgg } from '@/api/evaluation360'

/** The shared body of a 360 report (radar · gaps · Johari · hidden notices ·
 *  manager summary). Chrome (back / acknowledge / release) is added by callers. */
export function ReportView({ report }: { report: Report }) {
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
      {agg?.hidden_relationships?.length > 0 && (
        <Card><CardContent className="flex items-start gap-2 py-3 text-sm text-muted-foreground">
          <EyeOff className="h-4 w-4 mt-0.5 shrink-0" />
          <span>Defalcarea pe {agg.hidden_relationships.map((r) => RELATIONSHIP_LABEL[r] ?? r).join(', ')} este ascunsă — sub 3 răspunsuri (anonimat păstrat).</span>
        </CardContent></Card>
      )}

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
                <Radar name={`Ceilalți (n=${agg?.others_n ?? 0})`} dataKey="others" stroke="#22c55e" fill="#22c55e" fillOpacity={0.2} />
                <Legend />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </CardContent></Card>
      )}

      <Card><CardContent className="py-4">
        <p className="text-sm font-semibold mb-3">Diferența autoevaluare — ceilalți</p>
        <div className="space-y-2">{comps.map((c) => <GapRow key={c.competency_id} c={c} />)}</div>
      </CardContent></Card>

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
                <ul className="space-y-0.5">{items.map((c) => <li key={c.competency_id} className="text-sm">{c.competency_name ?? `#${c.competency_id}`}</li>)}</ul>
              ) : <p className="text-xs text-muted-foreground">—</p>}
            </CardContent></Card>
          )
        })}
      </div>

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
        <span className="text-muted-foreground">ceilalți {c.others ?? '—'}{c.others_n ? ` (n=${c.others_n})` : ''}</span>
        <Badge variant="outline" className={cn('tabular-nums', flagged ? 'text-amber-600 border-amber-200' : 'text-muted-foreground')}>
          {gap == null ? '—' : `${gap > 0 ? '+' : ''}${gap}`}
        </Badge>
      </div>
    </div>
  )
}
