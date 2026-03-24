import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Pencil, AlertTriangle, AlertCircle, TrendingUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { marketingApi } from '@/api/marketing'
import type { MktProject } from '@/types/marketing'
import { ApprovalWidget } from '@/components/shared/ApprovalWidget'
import { RichTextEditor, RichTextDisplay } from '@/components/shared/RichTextEditor'
import { OkrCard } from './OkrCard'
import { statusColors, fmt, fmtDate } from './utils'

// ── Donut Chart for Budget Breakdown ──

const DONUT_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#ec4899', '#f97316', '#14b8a6', '#6366f1',
]

function BudgetDonutChart({ lines, currency }: { lines: { channel: string; planned: number; spent: number; gross: number; credits: number }[]; currency: string }) {
  if (lines.length === 0) return null
  const total = lines.reduce((s, l) => s + l.planned, 0)
  if (total <= 0) return null

  const size = 160
  const cx = size / 2
  const cy = size / 2
  const r = 55
  const strokeWidth = 24

  let cumulative = 0
  const slices = lines.map((l, i) => {
    const pct = l.planned / total
    const startAngle = cumulative * 2 * Math.PI - Math.PI / 2
    cumulative += pct
    const endAngle = cumulative * 2 * Math.PI - Math.PI / 2
    const largeArc = pct > 0.5 ? 1 : 0
    const x1 = cx + r * Math.cos(startAngle)
    const y1 = cy + r * Math.sin(startAngle)
    const x2 = cx + r * Math.cos(endAngle)
    const y2 = cy + r * Math.sin(endAngle)
    return {
      ...l, pct, color: DONUT_COLORS[i % DONUT_COLORS.length],
      d: pct >= 0.999
        ? `M ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx + r - 0.001} ${cy}`
        : `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`,
    }
  })

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <h3 className="font-semibold text-sm">Budget Allocation</h3>
      <div className="flex items-center gap-6">
        <TooltipProvider delayDuration={150}>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
            {slices.map((s, i) => (
              <Tooltip key={i}>
                <TooltipTrigger asChild>
                  <path
                    d={s.d}
                    fill="none"
                    stroke={s.color}
                    strokeWidth={strokeWidth}
                    strokeLinecap="butt"
                    className="cursor-pointer transition-opacity hover:opacity-80"
                  />
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  <div className="font-medium">{s.channel.replace('_', ' ')}</div>
                  <div>Planned: {fmt(s.planned, currency)}</div>
                  <div>Gross Spent: {fmt(s.gross, currency)}</div>
                  {s.credits > 0 && <div className="text-green-600">Credits: {fmt(s.credits, currency)}</div>}
                  <div>Net: {fmt(s.spent, currency)}</div>
                  <div>{Math.round(s.pct * 100)}% of budget</div>
                </TooltipContent>
              </Tooltip>
            ))}
            <text x={cx} y={cy - 6} textAnchor="middle" className="fill-foreground text-sm font-bold">{fmt(total, currency)}</text>
            <text x={cx} y={cy + 10} textAnchor="middle" className="fill-muted-foreground text-[10px]">Total Budget</text>
          </svg>
        </TooltipProvider>
        <div className="flex-1 space-y-1.5 min-w-0">
          {slices.map((s, i) => {
            const exec = s.planned > 0 ? Math.max(0, Math.round((s.spent / s.planned) * 100)) : 0
            return (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                <span className="truncate flex-1">{s.channel.replace('_', ' ')}</span>
                <span className="tabular-nums text-muted-foreground shrink-0">{fmt(s.planned, currency)}</span>
                <span className="tabular-nums text-muted-foreground shrink-0 w-8 text-right">{exec}%</span>
              </div>
            )
          })}
        </div>
      </div>
      {/* Stacked bar: execution by channel */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>Execution by Channel</span>
        </div>
        {slices.map((s, i) => {
          const exec = s.planned > 0 ? Math.min(100, Math.max(0, Math.round((s.spent / s.planned) * 100))) : 0
          return (
            <div key={i} className="flex items-center gap-2">
              <span className="text-[10px] w-20 truncate text-muted-foreground">{s.channel.replace('_', ' ')}</span>
              <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                <div className="h-full rounded-full" style={{ width: `${exec}%`, backgroundColor: s.color, opacity: 0.8 }} />
              </div>
              <span className="text-[10px] tabular-nums text-muted-foreground w-16 text-right">
                {fmt(s.spent, currency)}
                {s.credits > 0 && <span className="text-green-600 ml-1">(-{fmt(s.credits, currency)})</span>}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function KpiVarianceBadge({ kpiId, isLowerBetter }: { kpiId: number; isLowerBetter: boolean }) {
  const { data } = useQuery({
    queryKey: ['mkt-kpi-snapshots', kpiId],
    queryFn: () => marketingApi.getKpiSnapshots(kpiId, 2),
  })
  const snaps = data?.snapshots ?? []
  if (snaps.length < 2) return null
  const variance = snaps[0].value - snaps[1].value
  if (variance === 0) return null
  const favorable = isLowerBetter ? variance < 0 : variance > 0
  return (
    <span className={cn(
      'text-[10px] font-semibold tabular-nums px-1 py-0.5 rounded-full',
      favorable
        ? 'text-green-700 dark:text-green-400 bg-green-100 dark:bg-green-950/40'
        : 'text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-950/40',
    )}>
      {variance > 0 ? '+' : ''}{variance.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
    </span>
  )
}

export function OverviewTab({ project }: { project: MktProject }) {
  const queryClient = useQueryClient()
  const budget = typeof project.total_budget === 'string' ? parseFloat(project.total_budget as string) : (project.total_budget ?? 0)
  const spent = typeof project.total_spent === 'string' ? parseFloat(project.total_spent as string) : (project.total_spent ?? 0)
  const eventCost = typeof project.event_cost === 'string' ? parseFloat(project.event_cost as string) : (project.event_cost ?? 0)
  const totalCredits = typeof project.total_credits === 'string' ? parseFloat(project.total_credits as string) : (project.total_credits ?? 0)
  const budgetSpent = spent - eventCost               // net from budget lines (debits - credits)
  const grossSpent = budgetSpent + totalCredits         // actual outflows (debits only, for breakdown)
  const netCost = spent                                 // real net = debits - credits + events
  const remaining = budget - netCost                    // how much budget is left
  const execution = budget ? Math.max(0, Math.round((netCost / budget) * 100)) : 0  // net cost efficiency

  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState(project.description ?? '')
  const [editingObj, setEditingObj] = useState(false)
  const [objDraft, setObjDraft] = useState(project.objective ?? '')
  const [editingAud, setEditingAud] = useState(false)
  const [audDraft, setAudDraft] = useState(project.target_audience ?? '')
  const [editingRef, setEditingRef] = useState(false)
  const [refDraft, setRefDraft] = useState(project.external_ref ?? '')

  const { data: kpisData } = useQuery({
    queryKey: ['mkt-project-kpis', project.id],
    queryFn: () => marketingApi.getProjectKpis(project.id),
  })

  const { data: budgetLinesData } = useQuery({
    queryKey: ['mkt-budget-lines', project.id],
    queryFn: () => marketingApi.getBudgetLines(project.id),
  })
  const budgetLines = (budgetLinesData?.budget_lines ?? []).map((l) => {
    const net = Number(l.spent_amount) || 0
    const credits = Number(l.credit_amount) || 0
    return {
      channel: l.channel,
      planned: Number(l.planned_amount) || 0,
      spent: net,
      credits,
      gross: net + credits, // actual debits (outflows)
    }
  }).filter((l) => l.planned > 0)
  const overviewKpis = (kpisData?.kpis ?? []).filter((k) => k.show_on_overview)

  const saveMut = useMutation({
    mutationFn: (desc: string) => marketingApi.updateProject(project.id, { description: desc }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project', project.id] })
      setEditingDesc(false)
    },
  })

  const saveFieldMut = useMutation({
    mutationFn: (fields: Partial<MktProject>) => marketingApi.updateProject(project.id, fields),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project', project.id] })
      setEditingObj(false)
      setEditingAud(false)
      setEditingRef(false)
    },
  })

  const kpiStatusColors: Record<string, string> = {
    no_data: 'text-gray-500',
    on_track: 'text-green-600',
    at_risk: 'text-yellow-600',
    behind: 'text-red-600',
    exceeded: 'text-emerald-600',
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left column: details */}
      <div className="lg:col-span-2 space-y-6">
        {/* Budget summary */}
        <div className="rounded-lg border p-4 space-y-3">
          <h3 className="font-semibold text-sm">Budget</h3>
          {/* Top-level KPIs */}
          <div className={`grid gap-4 text-center ${(eventCost > 0 && totalCredits > 0) ? 'grid-cols-5' : (eventCost > 0 || totalCredits > 0) ? 'grid-cols-4' : 'grid-cols-3'}`}>
            <div>
              <div className="text-lg font-bold">{fmt(budget, project.currency)}</div>
              <div className="text-xs text-muted-foreground">Total Budget</div>
            </div>
            <div>
              <div className={`text-lg font-bold ${netCost < 0 ? 'text-green-600' : ''}`}>{fmt(netCost, project.currency)}</div>
              <div className="text-xs text-muted-foreground">Net Cost</div>
            </div>
            {totalCredits > 0 && (
              <div>
                <div className="text-lg font-bold text-green-600">{fmt(totalCredits, project.currency)}</div>
                <div className="text-xs text-muted-foreground">Credits / Sponsorships</div>
              </div>
            )}
            {eventCost > 0 && (
              <div>
                <div className="text-lg font-bold">{fmt(eventCost, project.currency)}</div>
                <div className="text-xs text-muted-foreground">Event Costs</div>
              </div>
            )}
            <div>
              <div className={`text-lg font-bold ${execution > 90 ? 'text-red-500' : execution > 70 ? 'text-yellow-500' : ''}`}>{execution}%</div>
              <div className="text-xs text-muted-foreground">Execution</div>
            </div>
          </div>
          {/* Execution progress bar */}
          <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full ${execution > 90 ? 'bg-red-500' : execution > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
              style={{ width: `${Math.min(execution, 100)}%` }}
            />
          </div>

          {/* Budget Execution breakdown */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 rounded-md bg-muted/40 p-3">
            <div className="space-y-0.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Gross Spending</div>
              <div className="text-sm font-semibold tabular-nums">{fmt(grossSpent, project.currency)}</div>
            </div>
            {totalCredits > 0 && (
              <div className="space-y-0.5">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Credits / Sponsorships</div>
                <div className="text-sm font-semibold tabular-nums text-green-600">{fmt(totalCredits, project.currency)}</div>
              </div>
            )}
            <div className="space-y-0.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Net Cost</div>
              <div className={`text-sm font-semibold tabular-nums ${netCost < 0 ? 'text-green-600' : ''}`}>
                {netCost < 0 ? `${fmt(Math.abs(netCost), project.currency)} surplus` : fmt(netCost, project.currency)}
              </div>
            </div>
            <div className="space-y-0.5">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Remaining</div>
              <div className={`text-sm font-semibold tabular-nums ${remaining > budget ? 'text-green-600' : remaining < 0 ? 'text-red-600' : ''}`}>
                {fmt(remaining, project.currency)}
              </div>
            </div>
          </div>

          {/* Budget Alerts — based on net cost (after credits) */}
          {budget > 0 && execution >= 100 && (
            <div className="flex items-center gap-2 rounded-md border border-red-300 bg-red-50 dark:bg-red-950/20 dark:border-red-700 p-2.5 text-sm">
              <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
              <span className="text-red-800 dark:text-red-200 font-medium">Budget exceeded — net cost {fmt(netCost, project.currency)} of {fmt(budget, project.currency)} ({execution}%)</span>
            </div>
          )}
          {budget > 0 && execution >= 90 && execution < 100 && (
            <div className="flex items-center gap-2 rounded-md border border-orange-300 bg-orange-50 dark:bg-orange-950/20 dark:border-orange-700 p-2.5 text-sm">
              <AlertTriangle className="h-4 w-4 text-orange-600 shrink-0" />
              <span className="text-orange-800 dark:text-orange-200">Budget nearly exhausted — {fmt(remaining, project.currency)} remaining ({execution}%)</span>
            </div>
          )}
          {budget > 0 && execution >= 70 && execution < 90 && (
            <div className="flex items-center gap-2 rounded-md border border-yellow-300 bg-yellow-50 dark:bg-yellow-950/20 dark:border-yellow-700 p-2.5 text-sm">
              <TrendingUp className="h-4 w-4 text-yellow-600 shrink-0" />
              <span className="text-yellow-800 dark:text-yellow-200">High spend rate — {fmt(remaining, project.currency)} remaining ({execution}%)</span>
            </div>
          )}

          {/* Per-channel alerts — based on net cost per channel */}
          {budgetLines.filter((l) => l.planned > 0 && (l.spent / l.planned) >= 0.9).length > 0 && (
            <div className="space-y-1.5">
              {budgetLines.filter((l) => l.planned > 0 && (l.spent / l.planned) >= 0.9).map((l) => {
                const chExec = Math.round((l.spent / l.planned) * 100)
                return (
                  <div key={l.channel} className="flex items-center gap-2 text-xs text-muted-foreground">
                    {chExec >= 100 ? (
                      <AlertCircle className="h-3 w-3 text-red-500 shrink-0" />
                    ) : (
                      <AlertTriangle className="h-3 w-3 text-orange-500 shrink-0" />
                    )}
                    <span>
                      <span className="font-medium capitalize">{l.channel.replace('_', ' ')}</span>: {chExec}% net cost
                      ({fmt(l.spent, project.currency)} / {fmt(l.planned, project.currency)})
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Budget Donut Chart */}
        {budgetLines.length > 0 && (
          <BudgetDonutChart lines={budgetLines} currency={project.currency} />
        )}

        {/* KPI Overview — only KPIs marked show_on_overview */}
        {overviewKpis.length > 0 && (
          <div className="rounded-lg border p-4 space-y-3">
            <h3 className="font-semibold text-sm">Key Metrics</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {overviewKpis.map((k) => {
                const target = Number(k.target_value) || 0
                const agg = k.aggregation || 'latest'
                const current = agg === 'average' ? (Number(k.average_value) || Number(k.current_value) || 0)
                  : agg === 'cumulative' ? (Number(k.cumulative_value) || Number(k.current_value) || 0)
                  : (Number(k.latest_value) || Number(k.current_value) || 0)
                const isLowerBetter = k.direction === 'lower'
                const pct = target
                  ? Math.round(isLowerBetter ? (target / Math.max(current, 0.01)) * 100 : (current / target) * 100)
                  : 0
                return (
                  <div key={k.id} className="rounded-lg border p-3 space-y-1">
                    <div className="text-xs text-muted-foreground truncate">{k.kpi_name}</div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-lg font-bold tabular-nums">
                        {current.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                        {k.unit === 'percentage' ? '%' : k.unit === 'currency' ? ` ${k.currency || 'RON'}` : ''}
                      </span>
                      {target > 0 && (
                        <span className="text-xs text-muted-foreground">/ {target.toLocaleString('ro-RO')}</span>
                      )}
                    </div>
                    <KpiVarianceBadge kpiId={k.id} isLowerBetter={isLowerBetter} />
                    {target > 0 && (
                      <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full ${pct >= 100 ? 'bg-green-500' : pct >= 70 ? 'bg-blue-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`}
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                    )}
                    <div className={`text-[10px] font-medium ${kpiStatusColors[k.status] ?? ''}`}>
                      {k.status.replace('_', ' ')}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* OKR Card */}
        <OkrCard projectId={project.id} kpis={kpisData?.kpis ?? []} />

        {/* Project Description — editable */}
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">Project Description</h3>
            {!editingDesc && (
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => { setDescDraft(project.description ?? ''); setEditingDesc(true) }}>
                <Pencil className="h-3 w-3 mr-1" /> Edit
              </Button>
            )}
          </div>
          {editingDesc ? (
            <div className="space-y-2">
              <RichTextEditor
                content={descDraft}
                onChange={setDescDraft}
                placeholder="Add project details, goals, scope, notes..."
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditingDesc(false)}>Cancel</Button>
                <Button size="sm" disabled={saveMut.isPending} onClick={() => saveMut.mutate(descDraft)}>
                  {saveMut.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          ) : (
            project.description && project.description !== '<p></p>' ? (
              <RichTextDisplay content={project.description} className="text-sm" />
            ) : (
              <p className="text-sm text-muted-foreground">No description yet. Click Edit to add details.</p>
            )
          )}
        </div>

        {/* Objective — always visible, editable */}
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">Objective *</h3>
            {!editingObj && (
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => { setObjDraft(project.objective ?? ''); setEditingObj(true) }}>
                <Pencil className="h-3 w-3 mr-1" /> Edit
              </Button>
            )}
          </div>
          {editingObj ? (
            <div className="space-y-2">
              <Textarea
                value={objDraft}
                onChange={(e) => setObjDraft(e.target.value)}
                placeholder="What does success look like?"
                rows={3}
                className="text-sm"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditingObj(false)}>Cancel</Button>
                <Button size="sm" disabled={saveFieldMut.isPending} onClick={() => saveFieldMut.mutate({ objective: objDraft } as Partial<MktProject>)}>
                  {saveFieldMut.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {project.objective || 'No objective set. Click Edit to add one.'}
            </p>
          )}
        </div>

        {/* Target Audience — always visible, editable */}
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">Target Audience *</h3>
            {!editingAud && (
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => { setAudDraft(project.target_audience ?? ''); setEditingAud(true) }}>
                <Pencil className="h-3 w-3 mr-1" /> Edit
              </Button>
            )}
          </div>
          {editingAud ? (
            <div className="space-y-2">
              <Input
                value={audDraft}
                onChange={(e) => setAudDraft(e.target.value)}
                placeholder="e.g., Males 25-45, urban, car enthusiasts"
                className="text-sm"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditingAud(false)}>Cancel</Button>
                <Button size="sm" disabled={saveFieldMut.isPending} onClick={() => saveFieldMut.mutate({ target_audience: audDraft } as Partial<MktProject>)}>
                  {saveFieldMut.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {project.target_audience || 'No target audience set. Click Edit to add one.'}
            </p>
          )}
        </div>
      </div>

      {/* Right column: metadata */}
      <div className="space-y-4">
        <div className="rounded-lg border p-4 space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Status</span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[project.status] ?? ''}`}>
              {(project.status ?? '').replace('_', ' ')}
            </span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Type</span>
            <span className="capitalize">{(project.project_type ?? '').replace('_', ' ')}</span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Start Date</span>
            <span>{fmtDate(project.start_date)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">End Date</span>
            <span>{fmtDate(project.end_date)}</span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Owner</span>
            <span>{project.owner_name ?? '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Created</span>
            <span>{fmtDate(project.created_at)}</span>
          </div>
          <Separator />
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">External Ref</span>
              {!editingRef && (
                <Button variant="ghost" size="sm" className="h-6 px-1.5 text-xs" onClick={() => { setRefDraft(project.external_ref ?? ''); setEditingRef(true) }}>
                  <Pencil className="h-3 w-3" />
                </Button>
              )}
            </div>
            {editingRef ? (
              <div className="space-y-1.5">
                <Input
                  value={refDraft}
                  onChange={(e) => setRefDraft(e.target.value)}
                  placeholder="PO number, agency ref, etc."
                  className="text-sm h-8"
                />
                <div className="flex justify-end gap-1.5">
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setEditingRef(false)}>Cancel</Button>
                  <Button size="sm" className="h-7 text-xs" disabled={saveFieldMut.isPending} onClick={() => saveFieldMut.mutate({ external_ref: refDraft } as Partial<MktProject>)}>
                    {saveFieldMut.isPending ? 'Saving...' : 'Save'}
                  </Button>
                </div>
              </div>
            ) : (
              <span className="text-sm">{project.external_ref || '—'}</span>
            )}
          </div>
        </div>

        {/* Channel Mix */}
        {project.channel_mix?.length > 0 && (
          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="font-semibold text-sm">Channels</h3>
            <div className="flex flex-wrap gap-1.5">
              {project.channel_mix.map((ch) => (
                <Badge key={ch} variant="secondary" className="text-xs">
                  {ch.replace('_', ' ')}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Team preview */}
        {project.members && project.members.length > 0 && (
          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="font-semibold text-sm">Team ({project.members.length})</h3>
            <div className="space-y-1">
              {project.members.slice(0, 5).map((m) => (
                <div key={m.id} className="flex items-center justify-between text-sm">
                  <span>{m.user_name}</span>
                  <Badge variant="outline" className="text-xs">{m.role}</Badge>
                </div>
              ))}
              {project.members.length > 5 && (
                <span className="text-xs text-muted-foreground">+{project.members.length - 5} more</span>
              )}
            </div>
          </div>
        )}

        {/* Approval Status */}
        <div className="rounded-lg border p-4">
          <ApprovalWidget
            entityType="mkt_project"
            entityId={project.id}
            showApproverPicker
            onSubmit={async ({ approverId }) => {
              await marketingApi.submitApproval(project.id, approverId)
            }}
          />
        </div>
      </div>
    </div>
  )
}
