import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import {
  Plus, Trash2, DollarSign, Target, Link2, RefreshCw, BarChart3, Eye,
  Sparkles,
} from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import type { MktProjectKpi, KpiBenchmarks } from '@/types/marketing'
import { fmt, fmtDatetime } from './utils'

// ── MiniSparkline ──

function MiniSparkline({ values, className }: { values: number[]; className?: string }) {
  if (values.length < 2) return null
  const h = 24
  const w = 60
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w
    const y = h - ((v - min) / range) * (h - 4) - 2
    return `${x},${y}`
  })
  return (
    <svg width={w} height={h} className={className} viewBox={`0 0 ${w} ${h}`}>
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// ── HistoryChart ──

function HistoryChart({ values }: { values: { value: number; date: string }[] }) {
  if (values.length < 2) return <span className="text-sm text-muted-foreground">Not enough data for chart</span>
  const w = 400
  const h = 120
  const pad = { t: 10, b: 20, l: 40, r: 10 }
  const iw = w - pad.l - pad.r
  const ih = h - pad.t - pad.b
  const nums = values.map((v) => v.value)
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const range = max - min || 1
  const pts = values.map((v, i) => ({
    x: pad.l + (i / (values.length - 1)) * iw,
    y: pad.t + ih - ((v.value - min) / range) * ih,
  }))
  const line = pts.map((p) => `${p.x},${p.y}`).join(' ')
  const fill = `${pts[0].x},${pad.t + ih} ${line} ${pts[pts.length - 1].x},${pad.t + ih}`

  const ySteps = [min, min + range * 0.5, max]

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="text-foreground">
      {ySteps.map((v, i) => {
        const y = pad.t + ih - ((v - min) / range) * ih
        return (
          <g key={i}>
            <line x1={pad.l} x2={w - pad.r} y1={y} y2={y} stroke="currentColor" strokeOpacity={0.1} />
            <text x={pad.l - 4} y={y + 3} textAnchor="end" className="fill-muted-foreground" fontSize={9}>
              {v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)}
            </text>
          </g>
        )
      })}
      <polygon points={fill} fill="currentColor" fillOpacity={0.08} className="text-blue-500" />
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="text-blue-500" />
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill="currentColor" className="text-blue-500" />
      ))}
      <text x={pad.l} y={h - 2} className="fill-muted-foreground" fontSize={9}>
        {new Date(values[0].date).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' })}
      </text>
      <text x={w - pad.r} y={h - 2} textAnchor="end" className="fill-muted-foreground" fontSize={9}>
        {new Date(values[values.length - 1].date).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' })}
      </text>
    </svg>
  )
}

// ── KpiCard ──

function KpiCard({ kpi: k, statusColors, onRecord, onHistory, onDelete, onLinkSources, onSync, isSyncing, formula, benchmarks, onToggleOverview }: {
  kpi: MktProjectKpi; statusColors: Record<string, string>
  onRecord: () => void; onHistory: () => void; onDelete: () => void
  onLinkSources: () => void; onSync: () => void; isSyncing: boolean
  formula?: string | null
  benchmarks?: KpiBenchmarks | null
  onToggleOverview: () => void
}) {
  const { data: snapsData } = useQuery({
    queryKey: ['mkt-kpi-snapshots', k.id],
    queryFn: () => marketingApi.getKpiSnapshots(k.id, 10),
  })
  const sparkValues = [...(snapsData?.snapshots ?? [])].reverse().map((s) => s.value)

  const { data: blData } = useQuery({
    queryKey: ['mkt-kpi-budget-lines', k.id],
    queryFn: () => marketingApi.getKpiBudgetLines(k.id),
  })
  const linkedBLCount = blData?.budget_lines?.length ?? 0

  const { data: depData } = useQuery({
    queryKey: ['mkt-kpi-dependencies', k.id],
    queryFn: () => marketingApi.getKpiDependencies(k.id),
  })
  const linkedDepCount = depData?.dependencies?.length ?? 0
  const hasLinks = linkedBLCount > 0 || linkedDepCount > 0

  const target = Number(k.target_value) || 0
  const current = Number(k.current_value) || 0
  const isLowerBetter = k.direction === 'lower'
  const pct = target
    ? Math.round(isLowerBetter ? (target / Math.max(current, 0.01)) * 100 : (current / target) * 100)
    : 0
  const warn = Number(k.threshold_warning) || 0
  const crit = Number(k.threshold_critical) || 0
  const isWarning = isLowerBetter
    ? (warn > 0 && current >= warn && (crit <= 0 || current < crit))
    : (warn > 0 && current <= warn && current > crit)
  const isCritical = isLowerBetter
    ? (crit > 0 && current >= crit)
    : (crit > 0 && current <= crit)

  return (
    <div className={cn(
      'rounded-lg border p-4 space-y-3',
      isCritical && 'border-red-300 dark:border-red-800 bg-red-50/50 dark:bg-red-950/20',
      isWarning && !isCritical && 'border-yellow-300 dark:border-yellow-800 bg-yellow-50/50 dark:bg-yellow-950/20',
    )}>
      <div className="flex items-start justify-between">
        <div>
          <div className="font-medium text-sm">{k.kpi_name}</div>
          {formula && <div className="font-mono text-[10px] text-muted-foreground">{formula}</div>}
          {k.channel && <div className="text-xs text-muted-foreground">{k.channel}</div>}
        </div>
        <div className="flex items-center gap-1">
          {hasLinks && (
            <Badge variant="outline" className="text-[10px] h-5 px-1.5">auto</Badge>
          )}
          <span className={`text-xs font-medium ${statusColors[k.status] ?? ''}`}>
            {k.status.replace('_', ' ')}
          </span>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onDelete}>
            <Trash2 className="h-3 w-3 text-muted-foreground" />
          </Button>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold tabular-nums">
            {current.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}{k.unit === 'percentage' ? '%' : k.unit === 'currency' ? ` ${k.currency || 'RON'}` : ''}
          </span>
          {target > 0 && <span className="text-sm text-muted-foreground">
            / {target.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}{k.unit === 'percentage' ? '%' : k.unit === 'currency' ? ` ${k.currency || 'RON'}` : k.unit === 'ratio' ? '' : ` ${k.unit}`}
          </span>}
        </div>
        {sparkValues.length >= 2 && (
          <MiniSparkline
            values={sparkValues}
            className={cn(
              'text-blue-500 dark:text-blue-400',
              isCritical && 'text-red-500 dark:text-red-400',
              isWarning && !isCritical && 'text-yellow-500 dark:text-yellow-400',
            )}
          />
        )}
      </div>
      {target > 0 && (
        <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
          <div
            className={`h-full rounded-full ${pct >= 100 ? 'bg-green-500' : pct >= 70 ? 'bg-blue-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      )}
      {(isWarning || isCritical) && (
        <div className={`text-xs font-medium ${isCritical ? 'text-red-600' : 'text-yellow-600'}`}>
          {isCritical
            ? (isLowerBetter ? 'Above critical threshold' : 'Below critical threshold')
            : (isLowerBetter ? 'Above warning threshold' : 'Below warning threshold')}
        </div>
      )}
      {benchmarks?.segments?.[0] && current > 0 && (() => {
        const seg = benchmarks.segments[0]
        const isLower = k.direction === 'lower'
        const isExcellent = isLower ? current <= seg.excellent : current >= seg.excellent
        const isGood = isLower ? current <= seg.good : current >= seg.good
        const isAvg = isLower ? current <= seg.average : current >= seg.average
        const color = isExcellent ? 'text-green-600 dark:text-green-400'
          : isGood ? 'text-blue-600 dark:text-blue-400'
          : isAvg ? 'text-muted-foreground'
          : 'text-orange-600 dark:text-orange-400'
        const label = isExcellent ? 'Excellent' : isGood ? 'Good' : isAvg ? 'Average' : 'Below avg'
        return (
          <div className="flex items-center gap-2 text-[11px]">
            <span className="text-muted-foreground">Benchmark:</span>
            <span className={`font-medium ${color}`}>{label}</span>
            <span className="text-muted-foreground opacity-60">
              (avg {seg.average} · good {seg.good} · exc {seg.excellent})
            </span>
          </div>
        )
      })()}
      {hasLinks && (
        <div className="flex flex-wrap gap-1 cursor-pointer" onClick={onLinkSources}>
          {linkedBLCount > 0 && (
            <Badge variant="outline" className="text-[10px] h-5">
              <DollarSign className="h-3 w-3 mr-0.5" /> {linkedBLCount} budget line{linkedBLCount > 1 ? 's' : ''}
            </Badge>
          )}
          {(depData?.dependencies ?? []).map((d) => (
            <Badge key={d.depends_on_kpi_id} variant="outline" className="text-[10px] h-5">
              <Target className="h-3 w-3 mr-0.5" /> {d.dep_kpi_name} <span className="opacity-60 ml-0.5">({d.role})</span>
            </Badge>
          ))}
        </div>
      )}
      <div className="flex gap-1.5">
        <Button variant="outline" size="sm" className="flex-1 text-xs h-7" onClick={onRecord}>
          Record
        </Button>
        <Button variant="ghost" size="sm" className="text-xs h-7 px-2" onClick={onLinkSources} title="Link sources">
          <Link2 className="h-3.5 w-3.5" />
        </Button>
        {hasLinks && (
          <Button variant="ghost" size="sm" className="text-xs h-7 px-2" onClick={onSync} disabled={isSyncing} title="Sync from linked sources">
            <RefreshCw className={cn('h-3.5 w-3.5', isSyncing && 'animate-spin')} />
          </Button>
        )}
        <Button variant="ghost" size="sm" className="text-xs h-7 px-2" onClick={onHistory} title="History">
          <BarChart3 className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className={cn('text-xs h-7 px-2', k.show_on_overview && 'text-blue-600 dark:text-blue-400')}
          onClick={onToggleOverview}
          title={k.show_on_overview ? 'Hide from overview' : 'Show on overview'}
        >
          <Eye className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}

// ── KpisTab (main export) ──

export function KpisTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [addDefId, setAddDefId] = useState('')
  const [addTarget, setAddTarget] = useState('')
  const [addCurrency, setAddCurrency] = useState('RON')
  const [snapKpiId, setSnapKpiId] = useState<number | null>(null)
  const [snapValue, setSnapValue] = useState('')
  const [historyKpiId, setHistoryKpiId] = useState<number | null>(null)
  const [linkSourcesKpiId, setLinkSourcesKpiId] = useState<number | null>(null)

  const { data } = useQuery({
    queryKey: ['mkt-project-kpis', projectId],
    queryFn: () => marketingApi.getProjectKpis(projectId),
  })
  const kpis = data?.kpis ?? []

  const { data: budgetData } = useQuery({
    queryKey: ['mkt-budget-lines', projectId],
    queryFn: () => marketingApi.getBudgetLines(projectId),
  })
  const budgetLines = budgetData?.budget_lines ?? []

  const { data: defsData } = useQuery({
    queryKey: ['mkt-kpi-definitions'],
    queryFn: () => marketingApi.getKpiDefinitions(),
    enabled: showAdd || !!linkSourcesKpiId || kpis.length > 0,
  })
  const definitions = defsData?.definitions ?? []

  const { data: snapshotsData } = useQuery({
    queryKey: ['mkt-kpi-snapshots', historyKpiId],
    queryFn: () => marketingApi.getKpiSnapshots(historyKpiId!, 50),
    enabled: !!historyKpiId,
  })
  const snapshots = snapshotsData?.snapshots ?? []

  const { data: kpiBLData } = useQuery({
    queryKey: ['mkt-kpi-budget-lines', linkSourcesKpiId],
    queryFn: () => marketingApi.getKpiBudgetLines(linkSourcesKpiId!),
    enabled: !!linkSourcesKpiId,
  })
  const linkedBudgetLines = kpiBLData?.budget_lines ?? []
  const linkedBLIds = new Set(linkedBudgetLines.map((l) => l.budget_line_id))

  const { data: kpiDepData } = useQuery({
    queryKey: ['mkt-kpi-dependencies', linkSourcesKpiId],
    queryFn: () => marketingApi.getKpiDependencies(linkSourcesKpiId!),
    enabled: !!linkSourcesKpiId,
  })
  const linkedDeps = kpiDepData?.dependencies ?? []
  const linkedDepIds = new Set(linkedDeps.map((d) => d.depends_on_kpi_id))

  const addMut = useMutation({
    mutationFn: () => {
      const def = definitions.find((d) => String(d.id) === addDefId)
      return marketingApi.addProjectKpi(projectId, {
        kpi_definition_id: Number(addDefId),
        target_value: Number(addTarget) || null,
        ...(def?.unit === 'currency' ? { currency: addCurrency } : {}),
      } as Partial<MktProjectKpi>)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] })
      setShowAdd(false)
      setAddDefId('')
      setAddTarget('')
      setAddCurrency('RON')
    },
  })

  const snapMut = useMutation({
    mutationFn: () => marketingApi.addKpiSnapshot(projectId, snapKpiId!, {
      value: Number(snapValue),
      source: 'manual',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-snapshots'] })
      setSnapKpiId(null)
      setSnapValue('')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (kpiId: number) => marketingApi.deleteProjectKpi(projectId, kpiId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] }),
  })

  const linkBLMut = useMutation({
    mutationFn: ({ lineId, role }: { lineId: number; role: string }) =>
      marketingApi.linkKpiBudgetLine(linkSourcesKpiId!, lineId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-budget-lines', linkSourcesKpiId] })
    },
  })

  const unlinkBLMut = useMutation({
    mutationFn: (lineId: number) => marketingApi.unlinkKpiBudgetLine(linkSourcesKpiId!, lineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-budget-lines', linkSourcesKpiId] })
    },
  })

  const linkDepMut = useMutation({
    mutationFn: ({ depId, role }: { depId: number; role: string }) =>
      marketingApi.linkKpiDependency(linkSourcesKpiId!, depId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-dependencies', linkSourcesKpiId] })
    },
  })

  const unlinkDepMut = useMutation({
    mutationFn: (depId: number) => marketingApi.unlinkKpiDependency(linkSourcesKpiId!, depId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-dependencies', linkSourcesKpiId] })
    },
  })

  const syncMut = useMutation({
    mutationFn: (kpiId: number) => marketingApi.syncKpi(kpiId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-snapshots'] })
    },
  })

  const syncAllMut = useMutation({
    mutationFn: () => marketingApi.syncAllKpis(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-snapshots'] })
    },
  })

  const toggleOverviewMut = useMutation({
    mutationFn: ({ kpiId, show }: { kpiId: number; show: boolean }) =>
      marketingApi.updateProjectKpi(projectId, kpiId, { show_on_overview: show }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] }),
  })

  const benchmarkMut = useMutation({
    mutationFn: (defId: number) => marketingApi.generateBenchmarks(defId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions'] })
    },
  })

  const kpiStatusColors: Record<string, string> = {
    on_track: 'text-green-600', exceeded: 'text-blue-600',
    at_risk: 'text-yellow-600', behind: 'text-red-600', no_data: 'text-gray-400',
  }

  const historyKpi = kpis.find((k) => k.id === historyKpiId)

  return (
    <div className="space-y-4">
      <div className="flex justify-end gap-2">
        {kpis.length > 0 && (
          <Button size="sm" variant="outline" onClick={() => syncAllMut.mutate()} disabled={syncAllMut.isPending}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${syncAllMut.isPending ? 'animate-spin' : ''}`} /> Refresh All
          </Button>
        )}
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Add KPI
        </Button>
      </div>

      {kpis.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No KPIs configured.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {kpis.map((k) => {
            const def = definitions.find((d) => d.id === k.kpi_definition_id)
            return (
              <KpiCard
                key={k.id}
                kpi={k}
                statusColors={kpiStatusColors}
                formula={def?.formula}
                benchmarks={def?.benchmarks}
                onRecord={() => { setSnapKpiId(k.id); setSnapValue('') }}
                onHistory={() => setHistoryKpiId(k.id)}
                onDelete={() => deleteMut.mutate(k.id)}
                onLinkSources={() => setLinkSourcesKpiId(k.id)}
                onSync={() => syncMut.mutate(k.id)}
                isSyncing={syncMut.isPending}
                onToggleOverview={() => toggleOverviewMut.mutate({ kpiId: k.id, show: !k.show_on_overview })}
              />
            )
          })}
        </div>
      )}

      {/* Add KPI Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-sm" aria-describedby={undefined}>
          <DialogHeader><DialogTitle>Add KPI</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>KPI Definition *</Label>
              <Select value={addDefId} onValueChange={setAddDefId}>
                <SelectTrigger><SelectValue placeholder="Select KPI" /></SelectTrigger>
                <SelectContent>
                  {definitions.map((d) => (
                    <SelectItem key={d.id} value={String(d.id)}>{d.name} ({d.unit})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Target Value {addDefId && (() => {
                const def = definitions.find((d) => String(d.id) === addDefId)
                if (!def) return null
                const labels: Record<string, string> = { percentage: '(%)', ratio: '(ratio)', number: '' }
                if (def.unit === 'currency') return <span className="text-xs text-muted-foreground">({addCurrency})</span>
                return <span className="text-xs text-muted-foreground">{labels[def.unit] || `(${def.unit})`}</span>
              })()}</Label>
              <div className="flex gap-2">
                <Input type="number" className="flex-1" value={addTarget} onChange={(e) => setAddTarget(e.target.value)}
                  placeholder={(() => {
                    const def = definitions.find((d) => String(d.id) === addDefId)
                    const ph: Record<string, string> = { currency: '0.00', percentage: '0-100', ratio: '0.00', number: '0' }
                    return def ? ph[def.unit] || '0' : '0'
                  })()} />
                {addDefId && definitions.find((d) => String(d.id) === addDefId)?.unit === 'currency' && (
                  <Select value={addCurrency} onValueChange={setAddCurrency}>
                    <SelectTrigger className="w-[90px]"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="RON">RON</SelectItem>
                      <SelectItem value="EUR">EUR</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
            {addDefId && (() => {
              const def = definitions.find((d) => String(d.id) === addDefId)
              const segs = def?.benchmarks?.segments
              if (segs?.length) return (
                <div className="rounded-md border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/20 p-2.5 space-y-1.5">
                  <div className="text-xs font-medium text-blue-700 dark:text-blue-300">Industry Benchmarks (Romania)</div>
                  {segs.map((s, i) => (
                    <div key={i} className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                      <span className="font-medium">{s.name}:</span>
                      <span>avg {s.average.toLocaleString('ro-RO')}</span>
                      <span className="opacity-40">·</span>
                      <span className="text-blue-600 dark:text-blue-400">good {s.good.toLocaleString('ro-RO')}</span>
                      <span className="opacity-40">·</span>
                      <span className="text-green-600 dark:text-green-400">exc {s.excellent.toLocaleString('ro-RO')}</span>
                    </div>
                  ))}
                </div>
              )
              return (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-full text-xs"
                  disabled={benchmarkMut.isPending}
                  onClick={() => benchmarkMut.mutate(Number(addDefId))}
                >
                  <Sparkles className={cn('h-3.5 w-3.5 mr-1.5', benchmarkMut.isPending && 'animate-spin')} />
                  {benchmarkMut.isPending ? 'Generating benchmarks...' : 'Suggest target with AI'}
                </Button>
              )
            })()}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button disabled={!addDefId || addMut.isPending} onClick={() => addMut.mutate()}>
                {addMut.isPending ? 'Adding...' : 'Add'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Record Snapshot Dialog */}
      <Dialog open={!!snapKpiId} onOpenChange={(open) => { if (!open) setSnapKpiId(null) }}>
        <DialogContent className="max-w-sm" aria-describedby={undefined}>
          <DialogHeader><DialogTitle>Record KPI Value</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Value *</Label>
              <Input type="number" value={snapValue} onChange={(e) => setSnapValue(e.target.value)} autoFocus />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setSnapKpiId(null)}>Cancel</Button>
              <Button disabled={!snapValue || snapMut.isPending} onClick={() => snapMut.mutate()}>
                {snapMut.isPending ? 'Saving...' : 'Record'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Snapshot History Dialog */}
      <Dialog open={!!historyKpiId} onOpenChange={(open) => { if (!open) setHistoryKpiId(null) }}>
        <DialogContent className="max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>{historyKpi?.kpi_name ?? 'KPI'} — History</DialogTitle>
          </DialogHeader>
          {snapshots.length === 0 ? (
            <div className="text-center py-6 text-muted-foreground text-sm">No snapshots recorded yet.</div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-lg border p-4 flex items-center justify-center">
                <HistoryChart values={[...snapshots].reverse().map((s) => ({ value: s.value, date: s.recorded_at }))} />
              </div>
              <div className="rounded-md border max-h-64 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead className="text-right">Value</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>By</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {snapshots.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="text-sm">{fmtDatetime(s.recorded_at)}</TableCell>
                        <TableCell className="text-right text-sm tabular-nums font-medium">
                          {Number(s.value).toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs">{s.source}</Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">{s.recorded_by_name ?? '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Unified Link Sources Dialog */}
      <Dialog open={!!linkSourcesKpiId} onOpenChange={(open) => { if (!open) setLinkSourcesKpiId(null) }}>
        <DialogContent className="max-w-lg" aria-describedby={undefined}>
          {(() => {
            const editKpi = kpis.find((k) => k.id === linkSourcesKpiId)
            const def = editKpi ? definitions.find((d) => d.id === editKpi.kpi_definition_id) : null
            const vars = def?.variables?.length ? def.variables : ['input']
            const availableBL = budgetLines.filter((bl) => !linkedBLIds.has(bl.id))
            const availableKpis = kpis.filter((k) => k.id !== linkSourcesKpiId && !linkedDepIds.has(k.id))
            return (
              <>
                <DialogHeader>
                  <DialogTitle>{editKpi?.kpi_name ?? 'KPI'} — Link Sources</DialogTitle>
                  {def?.formula && <p className="text-sm text-muted-foreground font-mono">{def.formula}</p>}
                </DialogHeader>
                <div className="space-y-4 max-h-[60vh] overflow-y-auto">
                  {vars.map((varName) => {
                    const varBLs = linkedBudgetLines.filter((l) => l.role === varName)
                    const varDeps = linkedDeps.filter((d) => d.role === varName)
                    const hasSources = varBLs.length > 0 || varDeps.length > 0
                    return (
                      <div key={varName} className="rounded-lg border p-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm font-semibold">{varName}</span>
                            {hasSources
                              ? <Badge variant="default" className="text-[10px] h-4 px-1.5">linked</Badge>
                              : <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-muted-foreground">unlinked</Badge>}
                          </div>
                        </div>
                        {varBLs.map((l) => (
                          <div key={`bl-${l.budget_line_id}`} className="flex items-center justify-between rounded-md bg-muted/50 px-2.5 py-1.5">
                            <div className="flex items-center gap-2 text-sm">
                              <DollarSign className="h-3.5 w-3.5 text-muted-foreground" />
                              <span>{(l.channel ?? '').replace('_', ' ')}</span>
                              <span className="text-xs tabular-nums text-muted-foreground">({fmt(l.spent_amount, l.currency)})</span>
                            </div>
                            <button className="hover:text-destructive" onClick={() => unlinkBLMut.mutate(l.budget_line_id)}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ))}
                        {varDeps.map((d) => (
                          <div key={`dep-${d.depends_on_kpi_id}`} className="flex items-center justify-between rounded-md bg-muted/50 px-2.5 py-1.5">
                            <div className="flex items-center gap-2 text-sm">
                              <Target className="h-3.5 w-3.5 text-muted-foreground" />
                              <span>{d.dep_kpi_name}</span>
                              <span className="text-xs tabular-nums text-muted-foreground">({Number(d.dep_current_value || 0).toLocaleString('ro-RO')})</span>
                            </div>
                            <button className="hover:text-destructive" onClick={() => unlinkDepMut.mutate(d.depends_on_kpi_id)}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ))}
                        <Popover>
                          <PopoverTrigger asChild>
                            <Button variant="outline" size="sm" className="w-full text-xs h-7">
                              <Plus className="h-3 w-3 mr-1" /> Add source
                            </Button>
                          </PopoverTrigger>
                          <PopoverContent className="w-80 p-0" align="start">
                            <div className="max-h-64 overflow-y-auto">
                              {availableBL.length > 0 && (
                                <div className="p-2">
                                  <div className="text-xs font-medium text-muted-foreground px-2 pb-1">Budget Lines</div>
                                  {availableBL.map((bl) => (
                                    <div
                                      key={bl.id}
                                      className="flex items-center justify-between rounded-md px-2 py-1.5 cursor-pointer hover:bg-muted/50 text-sm"
                                      onClick={() => linkBLMut.mutate({ lineId: bl.id, role: varName })}
                                    >
                                      <div className="flex items-center gap-1.5">
                                        <DollarSign className="h-3.5 w-3.5 text-muted-foreground" />
                                        {(bl.channel ?? '').replace('_', ' ')}
                                      </div>
                                      <span className="text-xs tabular-nums text-muted-foreground">{fmt(bl.spent_amount, bl.currency)}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                              {availableBL.length > 0 && availableKpis.length > 0 && <Separator />}
                              {availableKpis.length > 0 && (
                                <div className="p-2">
                                  <div className="text-xs font-medium text-muted-foreground px-2 pb-1">Project KPIs</div>
                                  {availableKpis.map((pk) => (
                                    <div
                                      key={pk.id}
                                      className="flex items-center justify-between rounded-md px-2 py-1.5 cursor-pointer hover:bg-muted/50 text-sm"
                                      onClick={() => linkDepMut.mutate({ depId: pk.id, role: varName })}
                                    >
                                      <div className="flex items-center gap-1.5">
                                        <Target className="h-3.5 w-3.5 text-muted-foreground" />
                                        {pk.kpi_name}
                                      </div>
                                      <span className="text-xs tabular-nums text-muted-foreground">{Number(pk.current_value || 0).toLocaleString('ro-RO')}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                              {availableBL.length === 0 && availableKpis.length === 0 && (
                                <div className="p-4 text-center text-sm text-muted-foreground">No sources available</div>
                              )}
                            </div>
                          </PopoverContent>
                        </Popover>
                      </div>
                    )
                  })}
                </div>
                <div className="flex justify-end">
                  <Button variant="outline" onClick={() => setLinkSourcesKpiId(null)}>Done</Button>
                </div>
              </>
            )
          })()}
        </DialogContent>
      </Dialog>
    </div>
  )
}
