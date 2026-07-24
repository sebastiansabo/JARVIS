import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend,
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, ReferenceLine, Tooltip, CartesianGrid, LabelList,
} from 'recharts'
import { EyeOff } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { RELATIONSHIP_LABEL, JOHARI_LABEL, type Report, type CompetencyAgg } from '@/api/evaluation360'

const JOHARI_COLOR: Record<string, string> = {
  confirmed_strength: '#16a34a',  // top-right: self high, others high
  blind_spot: '#d97706',          // bottom-right: self high, others low
  hidden_strength: '#2563eb',     // top-left: self low, others high
  agreed_growth: '#dc2626',       // bottom-left: self low, others low
}

/** The shared body of a 360 report (radar · gaps · Johari · hidden notices ·
 *  manager summary). Chrome (back / acknowledge / release) is added by callers.
 *  `showManagerSummary` is false in calibration, where the manager's editor owns
 *  that section (avoids rendering the summary twice). */
export function ReportView({ report, showManagerSummary = true }: { report: Report; showManagerSummary?: boolean }) {
  const agg = report.aggregates_by_relationship
  const comps = agg?.competencies ?? []
  const radarData = comps.map((c) => ({
    competency: c.competency_name ?? `#${c.competency_id}`,
    self: c.self,
    others: c.others,
  }))
  const byJohari = (key: string) => comps.filter((c) => c.johari === key)
  const johariPoints = comps
    .filter((c) => c.self != null && c.others != null)
    .map((c) => ({ name: c.competency_name ?? `#${c.competency_id}`, self: c.self as number, others: c.others as number, johari: c.johari }))

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      {agg?.hidden_relationships?.length > 0 && (
        <Card><CardContent className="flex items-start gap-2 py-3 text-sm text-muted-foreground">
          <EyeOff className="h-4 w-4 mt-0.5 shrink-0" />
          <span>Defalcarea pe {agg.hidden_relationships.map((r) => RELATIONSHIP_LABEL[r] ?? r).join(', ')} este ascunsă — sub 3 răspunsuri (anonimat păstrat).</span>
        </CardContent></Card>
      )}

      {/* Radar + gaps sit side by side on desktop so the chart fills a proportionate
          column instead of a huge, mostly-empty card. */}
      <div className={cn('grid items-start gap-4', radarData.length >= 3 && 'lg:grid-cols-2')}>
        {radarData.length >= 3 && (
          <Card><CardContent className="py-4">
            <p className="text-sm font-semibold mb-2">Autoevaluare vs. ceilalți</p>
            <div className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData} outerRadius="70%">
                  <PolarGrid />
                  <PolarAngleAxis dataKey="competency" tick={{ fontSize: 11 }} />
                  <PolarRadiusAxis domain={[1, 5]} tickCount={5} angle={90} tick={{ fontSize: 10 }} />
                  <Radar name="Eu" dataKey="self" stroke="#2563eb" strokeWidth={2} fill="#3b82f6" fillOpacity={0.35} />
                  <Radar name={`Ceilalți (n=${agg?.others_n ?? 0})`} dataKey="others" stroke="#16a34a" strokeWidth={2} fill="#22c55e" fillOpacity={0.35} />
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
      </div>

      {/* Johari scatter — the product's core insight: self × others, split at 3.5 */}
      {johariPoints.length >= 1 && (
        <Card><CardContent className="py-4">
          <p className="text-sm font-semibold mb-1">Fereastra Johari — autoevaluare × ceilalți</p>
          <p className="text-xs text-muted-foreground mb-3">Fiecare punct = o competență. Punctele oarbe (te vezi mai bine decât te văd ceilalți) sunt evidențiate.</p>
          <JohariScatter points={johariPoints} />
        </CardContent></Card>
      )}

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

      {showManagerSummary && report.manager_summary && (
        <Card><CardContent className="py-4">
          <p className="text-sm font-semibold mb-1">Rezumatul managerului</p>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{report.manager_summary}</p>
        </CardContent></Card>
      )}
    </div>
  )
}

interface JohariPoint { name: string; self: number; others: number; johari: string | null }

function JohariScatter({ points }: { points: JohariPoint[] }) {
  return (
    <div className="relative h-96">
      {/* quadrant corner labels (x = self, y = others) */}
      <span className="pointer-events-none absolute left-10 top-1 z-10 text-[10px] font-semibold uppercase tracking-wide text-blue-600">Puncte forte ascunse</span>
      <span className="pointer-events-none absolute right-1 top-1 z-10 text-[10px] font-semibold uppercase tracking-wide text-green-600">Puncte forte confirmate</span>
      <span className="pointer-events-none absolute left-10 bottom-10 z-10 text-[10px] font-semibold uppercase tracking-wide text-red-600">Zone de dezvoltare</span>
      <span className="pointer-events-none absolute right-1 bottom-10 z-10 text-[10px] font-semibold uppercase tracking-wide text-amber-600">Puncte oarbe</span>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 18, right: 18, bottom: 26, left: 6 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" dataKey="self" domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} tick={{ fontSize: 10 }}
            label={{ value: 'Autoevaluare (eu)', position: 'insideBottom', offset: -14, fontSize: 11 }} />
          <YAxis type="number" dataKey="others" domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} tick={{ fontSize: 10 }}
            label={{ value: 'Ceilalți', angle: -90, position: 'insideLeft', fontSize: 11 }} />
          <ZAxis range={[70, 70]} />
          <ReferenceLine x={3.5} stroke="#94a3b8" strokeDasharray="4 4" />
          <ReferenceLine y={3.5} stroke="#94a3b8" strokeDasharray="4 4" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} content={<JohariTooltip />} />
          <Scatter
            data={points}
            shape={(p: { cx?: number; cy?: number; payload?: JohariPoint }) => {
              const blind = p.payload?.johari === 'blind_spot'
              return <circle cx={p.cx} cy={p.cy} r={blind ? 8 : 5.5}
                fill={JOHARI_COLOR[p.payload?.johari ?? ''] ?? '#64748b'} stroke="#fff" strokeWidth={1.5} />
            }}
          >
            <LabelList dataKey="name" position="top" style={{ fontSize: 9 }} className="fill-foreground" />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

function JohariTooltip({ active, payload }: { active?: boolean; payload?: { payload: JohariPoint }[] }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded-md border bg-background px-2 py-1 text-xs shadow-sm">
      <p className="font-semibold">{p.name}</p>
      <p className="text-muted-foreground">eu {p.self} · ceilalți {p.others}</p>
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
