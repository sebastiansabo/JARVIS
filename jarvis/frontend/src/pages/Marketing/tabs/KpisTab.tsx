import { useState, useEffect, useRef } from 'react'
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
import { Textarea } from '@/components/ui/textarea'
import {
  Plus, Trash2, DollarSign, Target, Link2, RefreshCw, BarChart3, Eye,
  Sparkles, Pencil, UserCheck, ShoppingCart, Search,
} from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import type { MktProjectKpi, KpiBenchmarks, MktKpiDealSource } from '@/types/marketing'
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

// ── SourcePicker (searchable dropdown for Add Source) ──

function SourcePicker({ varDeals, availableBL, availableKpis, onLinkBL, onLinkDep, onLinkDealMetric }: {
  varDeals: MktKpiDealSource[]
  availableBL: { id: number; channel: string; spent_amount: number; currency: string }[]
  availableKpis: MktProjectKpi[]
  onLinkBL: (lineId: number) => void
  onLinkDep: (depId: number) => void
  onLinkDealMetric: (metric: string) => void
}) {
  const [q, setQ] = useState('')
  const lq = q.toLowerCase()

  const dealMetricLabels: Record<string, string> = { count: 'Deal Count', sum_revenue: 'Total Revenue', sum_profit: 'Total Profit', avg_price: 'Avg Price' }
  const dealMetrics = (['count', 'sum_revenue', 'sum_profit', 'avg_price'] as const)
    .filter((m) => !varDeals.some((ds) => ds.metric === m))

  const filteredBL = availableBL.filter((bl) => !lq || (bl.channel ?? '').toLowerCase().includes(lq))
  const filteredKpis = availableKpis.filter((pk) => !lq || (pk.kpi_name ?? '').toLowerCase().includes(lq))
  const filteredMetrics = dealMetrics.filter((m) => !lq || dealMetricLabels[m].toLowerCase().includes(lq) || 'crm deal'.includes(lq))

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="w-full text-xs h-7">
          <Plus className="h-3 w-3 mr-1" /> Add source
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start" onOpenAutoFocus={(e) => e.preventDefault()}>
        <div className="p-2 border-b">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              className="h-7 pl-8 text-xs"
              placeholder="Search sources..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              autoFocus
            />
          </div>
        </div>
        <div className="max-h-72 overflow-y-auto">
          {filteredBL.length > 0 && (
            <div className="p-2">
              <div className="text-xs font-medium text-muted-foreground px-2 pb-1">Budget Lines</div>
              {filteredBL.map((bl) => (
                <div
                  key={bl.id}
                  className="flex items-center justify-between rounded-md px-2 py-1.5 cursor-pointer hover:bg-muted/50 text-sm"
                  onClick={() => onLinkBL(bl.id)}
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
          {filteredBL.length > 0 && filteredKpis.length > 0 && <Separator />}
          {filteredKpis.length > 0 && (
            <div className="p-2">
              <div className="text-xs font-medium text-muted-foreground px-2 pb-1">Project KPIs</div>
              {filteredKpis.map((pk) => (
                <div
                  key={pk.id}
                  className="flex items-center justify-between rounded-md px-2 py-1.5 cursor-pointer hover:bg-muted/50 text-sm"
                  onClick={() => onLinkDep(pk.id)}
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
          {(filteredBL.length > 0 || filteredKpis.length > 0) && filteredMetrics.length > 0 && <Separator />}
          {filteredMetrics.length > 0 && (
            <div className="p-2">
              <div className="text-xs font-medium text-muted-foreground px-2 pb-1">CRM Deal Metrics</div>
              {filteredMetrics.map((metric) => (
                <div
                  key={metric}
                  className="flex items-center justify-between rounded-md px-2 py-1.5 cursor-pointer hover:bg-muted/50 text-sm"
                  onClick={() => onLinkDealMetric(metric)}
                >
                  <div className="flex items-center gap-1.5">
                    <UserCheck className="h-3.5 w-3.5 text-muted-foreground" />
                    {dealMetricLabels[metric]}
                  </div>
                  <span className="text-[10px] text-muted-foreground">from linked clients</span>
                </div>
              ))}
            </div>
          )}
          {filteredBL.length === 0 && filteredKpis.length === 0 && filteredMetrics.length === 0 && (
            <div className="p-4 text-center text-sm text-muted-foreground">No sources match &ldquo;{q}&rdquo;</div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

// ── KpiCard ──

function KpiCard({ kpi: k, statusColors, onRecord, onHistory, onDelete, onLinkSources, onSync, isSyncing, formula, benchmarks, onToggleOverview, onUpdateAggregation, onEdit }: {
  kpi: MktProjectKpi; statusColors: Record<string, string>
  onRecord: () => void; onHistory: () => void; onDelete: () => void
  onLinkSources: () => void; onSync: () => void; isSyncing: boolean
  formula?: string | null
  benchmarks?: KpiBenchmarks | null
  onToggleOverview: () => void
  onUpdateAggregation: (mode: 'latest' | 'average' | 'cumulative') => void
  onEdit: () => void
}) {
  const { data: snapsData } = useQuery({
    queryKey: ['mkt-kpi-snapshots', k.id],
    queryFn: () => marketingApi.getKpiSnapshots(k.id, 10),
  })
  const snaps = snapsData?.snapshots ?? [] // newest first
  const sparkValues = [...snaps].reverse().map((s) => s.value)
  const variance = snaps.length >= 2 ? snaps[0].value - snaps[1].value : null

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

  const { data: dealSrcData } = useQuery({
    queryKey: ['mkt-kpi-deal-sources', k.id],
    queryFn: () => marketingApi.getKpiDealSources(k.id),
  })
  const linkedDealCount = dealSrcData?.deal_sources?.length ?? 0

  const { data: kpiDealsCardData } = useQuery({
    queryKey: ['mkt-kpi-deals', k.id],
    queryFn: () => marketingApi.getKpiDeals(k.id),
  })
  const linkedIndividualDeals = kpiDealsCardData?.deals?.length ?? 0
  const hasLinks = linkedBLCount > 0 || linkedDepCount > 0 || linkedDealCount > 0 || linkedIndividualDeals > 0

  const target = Number(k.target_value) || 0
  const avg = Number(k.average_value) || 0
  const cumul = Number(k.cumulative_value) || 0
  const latest = Number(k.latest_value) || 0
  const agg = k.aggregation || 'latest'
  const current = agg === 'average' ? (avg || Number(k.current_value) || 0)
    : agg === 'cumulative' ? (cumul || Number(k.current_value) || 0)
    : (latest || Number(k.current_value) || 0)
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
          <Select value={agg} onValueChange={(v) => onUpdateAggregation(v as 'latest' | 'average' | 'cumulative')}>
            <SelectTrigger className="h-5 w-auto text-[10px] px-1.5 gap-0.5 border-none bg-muted/50">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="latest">Latest</SelectItem>
              <SelectItem value="average">Average</SelectItem>
              <SelectItem value="cumulative">Cumulative</SelectItem>
            </SelectContent>
          </Select>
          {hasLinks && (
            <Badge variant="outline" className="text-[10px] h-5 px-1.5">auto</Badge>
          )}
          <span className={`text-xs font-medium ${statusColors[k.status] ?? ''}`}>
            {k.status.replace('_', ' ')}
          </span>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onEdit} title="Edit KPI">
            <Pencil className="h-3 w-3 text-muted-foreground" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onDelete}>
            <Trash2 className="h-3 w-3 text-muted-foreground" />
          </Button>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold tabular-nums">
              {current.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}{k.unit === 'percentage' ? '%' : k.unit === 'currency' ? ` ${k.currency || 'RON'}` : ''}
            </span>
            {target > 0 && <span className="text-sm text-muted-foreground">
              / {target.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}{k.unit === 'percentage' ? '%' : k.unit === 'currency' ? ` ${k.currency || 'RON'}` : k.unit === 'ratio' ? '' : ` ${k.unit}`}
            </span>}
          </div>
          {(latest > 0 || variance) && (
            <div className="flex items-center gap-2 mt-0.5">
              {latest > 0 && Math.round(current * 100) !== Math.round(latest * 100) && (
                <span className="text-xs text-muted-foreground">
                  Latest: {latest.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}{k.unit === 'percentage' ? '%' : k.unit === 'currency' ? ` ${k.currency || 'RON'}` : ''}
                </span>
              )}
              {variance !== null && variance !== 0 && (
                <span className={cn(
                  'text-[11px] font-semibold tabular-nums px-1.5 py-0.5 rounded-full',
                  (isLowerBetter ? variance < 0 : variance > 0)
                    ? 'text-green-700 dark:text-green-400 bg-green-100 dark:bg-green-950/40'
                    : 'text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-950/40',
                )}>
                  {variance > 0 ? '+' : ''}{variance.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                </span>
              )}
            </div>
          )}
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
          {linkedIndividualDeals > 0 && (
            <Badge variant="outline" className="text-[10px] h-5">
              <ShoppingCart className="h-3 w-3 mr-0.5" /> {linkedIndividualDeals} deal{linkedIndividualDeals > 1 ? 's' : ''}
            </Badge>
          )}
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
  const [addAggregation, setAddAggregation] = useState<'latest' | 'average' | 'cumulative'>('latest')
  const [snapKpiId, setSnapKpiId] = useState<number | null>(null)
  const [snapValue, setSnapValue] = useState('')
  const [historyKpiId, setHistoryKpiId] = useState<number | null>(null)
  const [linkSourcesKpiId, setLinkSourcesKpiId] = useState<number | null>(null)

  // Edit KPI state
  const [editKpiId, setEditKpiId] = useState<number | null>(null)
  const [editTarget, setEditTarget] = useState('')
  const [editWarn, setEditWarn] = useState('')
  const [editCrit, setEditCrit] = useState('')
  const [editChannel, setEditChannel] = useState('')
  const [editCurrency, setEditCurrency] = useState('RON')
  const [editNotes, setEditNotes] = useState('')

  // Custom KPI creation state
  const [addMode, setAddMode] = useState<'catalog' | 'custom'>('catalog')
  const [customName, setCustomName] = useState('')
  const [customFormula, setCustomFormula] = useState('')
  const [customUnit, setCustomUnit] = useState<'number' | 'currency' | 'percentage' | 'ratio'>('number')
  const [customDirection, setCustomDirection] = useState<'higher' | 'lower'>('higher')
  const [customDescription, setCustomDescription] = useState('')
  const [formulaValid, setFormulaValid] = useState<{ valid: boolean; error: string | null; variables: string[] } | null>(null)

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

  const { data: kpiDealData } = useQuery({
    queryKey: ['mkt-kpi-deal-sources', linkSourcesKpiId],
    queryFn: () => marketingApi.getKpiDealSources(linkSourcesKpiId!),
    enabled: !!linkSourcesKpiId,
  })
  const linkedDealSources: MktKpiDealSource[] = kpiDealData?.deal_sources ?? []

  const { data: kpiDealsData } = useQuery({
    queryKey: ['mkt-kpi-deals', linkSourcesKpiId],
    queryFn: () => marketingApi.getKpiDeals(linkSourcesKpiId!),
    enabled: !!linkSourcesKpiId,
  })
  const linkedDeals = kpiDealsData?.deals ?? []

  const { data: availableDealsData } = useQuery({
    queryKey: ['mkt-available-deals', projectId, linkSourcesKpiId],
    queryFn: () => marketingApi.getAvailableDeals(projectId, linkSourcesKpiId!),
    enabled: !!linkSourcesKpiId,
  })
  const availableDeals = availableDealsData?.deals ?? []

  const addMut = useMutation({
    mutationFn: () => {
      const def = definitions.find((d) => String(d.id) === addDefId)
      return marketingApi.addProjectKpi(projectId, {
        kpi_definition_id: Number(addDefId),
        target_value: addTarget !== '' ? Number(addTarget) : null,
        aggregation: addAggregation,
        ...(def?.unit === 'currency' ? { currency: addCurrency } : {}),
      } as Partial<MktProjectKpi>)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] })
      setShowAdd(false)
      resetAddDialog()
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

  const linkDealSourceMut = useMutation({
    mutationFn: ({ role, metric }: { role: string; metric: string }) =>
      marketingApi.linkKpiDealSource(linkSourcesKpiId!, { role, metric }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-deal-sources', linkSourcesKpiId] })
    },
  })

  const unlinkDealSourceMut = useMutation({
    mutationFn: (sourceId: number) => marketingApi.unlinkKpiDealSource(linkSourcesKpiId!, sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-deal-sources', linkSourcesKpiId] })
    },
  })

  const linkDealMut = useMutation({
    mutationFn: (dealId: number) => marketingApi.linkKpiDeal(linkSourcesKpiId!, dealId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-deals', linkSourcesKpiId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-available-deals', projectId, linkSourcesKpiId] })
    },
  })

  const unlinkDealMut = useMutation({
    mutationFn: (dealLinkId: number) => marketingApi.unlinkKpiDeal(linkSourcesKpiId!, dealLinkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-deals', linkSourcesKpiId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-available-deals', projectId, linkSourcesKpiId] })
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

  // Auto-sync interval
  const AUTOSYNC_KEY = `mkt-autosync-${projectId}`
  const [autoSyncMinutes, setAutoSyncMinutes] = useState<number>(() => {
    try { return Number(localStorage.getItem(AUTOSYNC_KEY)) || 0 } catch { return 0 }
  })
  const syncTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [lastSynced, setLastSynced] = useState<Date | null>(null)

  // Keep a stable ref to avoid stale closure in setInterval
  const syncAllRef = useRef(syncAllMut)
  syncAllRef.current = syncAllMut

  useEffect(() => {
    if (syncTimerRef.current) clearInterval(syncTimerRef.current)
    if (autoSyncMinutes > 0 && kpis.length > 0) {
      syncTimerRef.current = setInterval(() => {
        syncAllRef.current.mutate(undefined, {
          onSuccess: () => setLastSynced(new Date()),
        })
      }, autoSyncMinutes * 60 * 1000)
    }
    return () => { if (syncTimerRef.current) clearInterval(syncTimerRef.current) }
  }, [autoSyncMinutes, kpis.length])

  function setAutoSync(minutes: number) {
    setAutoSyncMinutes(minutes)
    try { localStorage.setItem(AUTOSYNC_KEY, String(minutes)) } catch { /* ignore */ }
  }

  const updateKpiMut = useMutation({
    mutationFn: ({ kpiId, updates }: { kpiId: number; updates: Record<string, unknown> }) =>
      marketingApi.updateProjectKpi(projectId, kpiId, updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] }),
  })

  const benchmarkMut = useMutation({
    mutationFn: (defId: number) => marketingApi.generateBenchmarks(defId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions'] })
    },
  })

  // Open edit dialog with current values
  function openEdit(k: MktProjectKpi) {
    setEditKpiId(k.id)
    setEditTarget(k.target_value != null ? String(Number(k.target_value)) : '')
    setEditWarn(k.threshold_warning != null ? String(Number(k.threshold_warning)) : '')
    setEditCrit(k.threshold_critical != null ? String(Number(k.threshold_critical)) : '')
    setEditChannel(k.channel || '')
    setEditCurrency(k.currency || 'RON')
    setEditNotes(k.notes || '')
  }

  const editMut = useMutation({
    mutationFn: () =>
      marketingApi.updateProjectKpi(projectId, editKpiId!, {
        target_value: editTarget !== '' ? Number(editTarget) : null,
        threshold_warning: editWarn !== '' ? Number(editWarn) : null,
        threshold_critical: editCrit !== '' ? Number(editCrit) : null,
        channel: editChannel || null,
        currency: editCurrency,
        notes: editNotes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] })
      setEditKpiId(null)
    },
  })

  // Create custom KPI definition + add to project
  const createCustomMut = useMutation({
    mutationFn: async () => {
      const slug = customName.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/(^_|_$)/g, '')
      const res = await marketingApi.createKpiDefinition({
        name: customName,
        slug,
        unit: customUnit,
        direction: customDirection,
        category: 'custom',
        formula: customFormula || undefined,
        description: customDescription || undefined,
      })
      // Now add it to the project
      await marketingApi.addProjectKpi(projectId, {
        kpi_definition_id: res.id,
        target_value: addTarget !== '' ? Number(addTarget) : null,
        aggregation: addAggregation,
        ...(customUnit === 'currency' ? { currency: addCurrency } : {}),
      } as Partial<MktProjectKpi>)
      return res.id
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-kpis', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions'] })
      setShowAdd(false)
      resetAddDialog()
    },
  })

  function resetAddDialog() {
    setAddDefId('')
    setAddTarget('')
    setAddCurrency('RON')
    setAddAggregation('latest')
    setAiSuggestion(null)
    setAddMode('catalog')
    setCustomName('')
    setCustomFormula('')
    setCustomUnit('number')
    setCustomDirection('higher')
    setCustomDescription('')
    setFormulaValid(null)
  }

  // Formula validation
  const validateFormulaMut = useMutation({
    mutationFn: (formula: string) => marketingApi.validateFormula(formula),
    onSuccess: (data) => setFormulaValid(data),
  })

  const [aiSuggestion, setAiSuggestion] = useState<{ suggested_target: number; reasoning: string; confidence: string } | null>(null)
  const suggestMut = useMutation({
    mutationFn: (defId: number) => marketingApi.suggestKpiTarget(projectId, defId),
    onSuccess: (data) => {
      setAiSuggestion(data)
      setAddTarget(String(data.suggested_target))
    },
  })

  const suggestInlineMut = useMutation({
    mutationFn: () => marketingApi.suggestKpiTargetInline(projectId, {
      kpi_name: customName,
      unit: customUnit,
      direction: customDirection,
      formula: customFormula || undefined,
      description: customDescription || undefined,
    }),
    onSuccess: (data) => {
      setAiSuggestion(data)
      setAddTarget(String(data.suggested_target))
    },
  })

  const kpiStatusColors: Record<string, string> = {
    on_track: 'text-green-600', exceeded: 'text-blue-600',
    at_risk: 'text-yellow-600', behind: 'text-red-600', no_data: 'text-gray-400',
  }

  const historyKpi = kpis.find((k) => k.id === historyKpiId)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2 flex-wrap">
        {kpis.length > 0 && (
          <>
            <div className="flex items-center gap-1.5 mr-2">
              <span className="text-xs text-muted-foreground">Auto-sync:</span>
              <Select value={String(autoSyncMinutes)} onValueChange={(v) => setAutoSync(Number(v))}>
                <SelectTrigger className="h-7 w-[100px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">Off</SelectItem>
                  <SelectItem value="1">1 min</SelectItem>
                  <SelectItem value="5">5 min</SelectItem>
                  <SelectItem value="15">15 min</SelectItem>
                  <SelectItem value="30">30 min</SelectItem>
                  <SelectItem value="60">1 hour</SelectItem>
                </SelectContent>
              </Select>
              {lastSynced && (
                <span className="text-[10px] text-muted-foreground">
                  Last: {lastSynced.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
            </div>
            <Button size="sm" variant="outline" onClick={() => syncAllMut.mutate(undefined, { onSuccess: () => setLastSynced(new Date()) })} disabled={syncAllMut.isPending}>
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${syncAllMut.isPending ? 'animate-spin' : ''}`} /> Refresh All
            </Button>
          </>
        )}
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Add KPI
        </Button>
      </div>

      {kpis.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Target className="mx-auto h-8 w-8 mb-2 opacity-40" />
          <div>No KPIs configured</div>
          <div className="text-xs mt-1">Click "Add KPI" to track performance metrics for this campaign.</div>
        </div>
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
                onToggleOverview={() => updateKpiMut.mutate({ kpiId: k.id, updates: { show_on_overview: !k.show_on_overview } })}
                onUpdateAggregation={(mode) => updateKpiMut.mutate({ kpiId: k.id, updates: { aggregation: mode } })}
                onEdit={() => openEdit(k)}
              />
            )
          })}
        </div>
      )}

      {/* Add KPI Dialog */}
      <Dialog open={showAdd} onOpenChange={(open) => { if (!open) { setShowAdd(false); resetAddDialog() } else setShowAdd(true) }}>
        <DialogContent className="max-w-md" aria-describedby={undefined}>
          <DialogHeader><DialogTitle>Add KPI</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {/* Mode tabs */}
            <div className="flex border rounded-md overflow-hidden">
              <button
                className={cn('flex-1 text-xs py-1.5 px-3 transition-colors', addMode === 'catalog' ? 'bg-primary text-primary-foreground' : 'bg-muted/50 hover:bg-muted')}
                onClick={() => setAddMode('catalog')}
              >From Catalog</button>
              <button
                className={cn('flex-1 text-xs py-1.5 px-3 transition-colors', addMode === 'custom' ? 'bg-primary text-primary-foreground' : 'bg-muted/50 hover:bg-muted')}
                onClick={() => setAddMode('custom')}
              >Create Custom</button>
            </div>

            {addMode === 'catalog' ? (
              <>
                <div className="space-y-1.5">
                  <Label>KPI Definition *</Label>
                  <Select value={addDefId} onValueChange={(v) => { setAddDefId(v); setAiSuggestion(null) }}>
                    <SelectTrigger><SelectValue placeholder="Select KPI" /></SelectTrigger>
                    <SelectContent>
                      {definitions.map((d) => (
                        <SelectItem key={d.id} value={String(d.id)}>{d.name} ({d.unit}){d.formula ? ' [calc]' : ''}</SelectItem>
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
                <div className="space-y-1.5">
                  <Label>Aggregation Mode</Label>
                  <Select value={addAggregation} onValueChange={(v) => setAddAggregation(v as 'latest' | 'average' | 'cumulative')}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="latest">Latest — last recorded value</SelectItem>
                      <SelectItem value="average">Average — mean of all values</SelectItem>
                      <SelectItem value="cumulative">Cumulative — sum of all values</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {addDefId && (
                  <div className="space-y-2">
                    {aiSuggestion && (
                      <div className="rounded-md border border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-950/20 p-2.5 space-y-1">
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-medium text-green-700 dark:text-green-300">AI Suggested Target</div>
                          <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                            aiSuggestion.confidence === 'high' ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' :
                            aiSuggestion.confidence === 'medium' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300' :
                            'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
                          )}>{aiSuggestion.confidence} confidence</span>
                        </div>
                        <div className="text-sm font-bold tabular-nums">{aiSuggestion.suggested_target.toLocaleString('ro-RO')}</div>
                        <div className="text-[11px] text-muted-foreground">{aiSuggestion.reasoning}</div>
                      </div>
                    )}
                    {(() => {
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
                      return null
                    })()}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="w-full text-xs"
                      disabled={suggestMut.isPending || benchmarkMut.isPending}
                      onClick={() => {
                        suggestMut.mutate(Number(addDefId))
                        const def = definitions.find((d) => String(d.id) === addDefId)
                        if (!def?.benchmarks?.segments?.length) benchmarkMut.mutate(Number(addDefId))
                      }}
                    >
                      <Sparkles className={cn('h-3.5 w-3.5 mr-1.5', (suggestMut.isPending || benchmarkMut.isPending) && 'animate-spin')} />
                      {suggestMut.isPending ? 'Analyzing project data...' : 'Suggest target with AI'}
                    </Button>
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => { setShowAdd(false); resetAddDialog() }}>Cancel</Button>
                  <Button disabled={!addDefId || addMut.isPending} onClick={() => addMut.mutate()}>
                    {addMut.isPending ? 'Adding...' : 'Add'}
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div className="space-y-1.5">
                  <Label>Name *</Label>
                  <Input value={customName} onChange={(e) => setCustomName(e.target.value)} placeholder="e.g. Cost Per Lead" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>Unit</Label>
                    <Select value={customUnit} onValueChange={(v) => setCustomUnit(v as 'number' | 'currency' | 'percentage' | 'ratio')}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="number">Number</SelectItem>
                        <SelectItem value="currency">Currency</SelectItem>
                        <SelectItem value="percentage">Percentage</SelectItem>
                        <SelectItem value="ratio">Ratio</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Direction</Label>
                    <Select value={customDirection} onValueChange={(v) => setCustomDirection(v as 'higher' | 'lower')}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="higher">Higher is better</SelectItem>
                        <SelectItem value="lower">Lower is better</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>Formula <span className="text-xs text-muted-foreground">(optional — reference other KPIs)</span></Label>
                  <Input
                    value={customFormula}
                    onChange={(e) => { setCustomFormula(e.target.value); setFormulaValid(null) }}
                    onBlur={() => { if (customFormula.trim()) validateFormulaMut.mutate(customFormula) }}
                    placeholder="e.g. spent / leads"
                    className="font-mono text-sm"
                  />
                  {formulaValid && (
                    formulaValid.valid ? (
                      <div className="text-xs text-green-600 dark:text-green-400">
                        Valid — variables: {formulaValid.variables.join(', ') || 'none'}
                      </div>
                    ) : (
                      <div className="text-xs text-red-600 dark:text-red-400">{formulaValid.error}</div>
                    )
                  )}
                  {formulaValid?.valid && formulaValid.variables.length > 0 && (
                    <div className="text-[11px] text-muted-foreground">
                      After adding, link other project KPIs to these variables via the Link Sources button.
                    </div>
                  )}
                </div>
                <div className="space-y-1.5">
                  <Label>Description</Label>
                  <Input value={customDescription} onChange={(e) => setCustomDescription(e.target.value)} placeholder="Optional description" />
                </div>
                <Separator />
                <div className="space-y-1.5">
                  <Label>Target Value</Label>
                  <div className="flex gap-2">
                    <Input type="number" className="flex-1" value={addTarget} onChange={(e) => setAddTarget(e.target.value)} placeholder="0" />
                    {customUnit === 'currency' && (
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
                <div className="space-y-1.5">
                  <Label>Aggregation Mode</Label>
                  <Select value={addAggregation} onValueChange={(v) => setAddAggregation(v as 'latest' | 'average' | 'cumulative')}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="latest">Latest</SelectItem>
                      <SelectItem value="average">Average</SelectItem>
                      <SelectItem value="cumulative">Cumulative</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {customName.trim() && (
                  <div className="space-y-2">
                    {aiSuggestion && (
                      <div className="rounded-md border border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-950/20 p-2.5 space-y-1">
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-medium text-green-700 dark:text-green-300">AI Suggested Target</div>
                          <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                            aiSuggestion.confidence === 'high' ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' :
                            aiSuggestion.confidence === 'medium' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300' :
                            'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
                          )}>{aiSuggestion.confidence} confidence</span>
                        </div>
                        <div className="text-sm font-bold tabular-nums">{aiSuggestion.suggested_target.toLocaleString('ro-RO')}</div>
                        <div className="text-[11px] text-muted-foreground">{aiSuggestion.reasoning}</div>
                      </div>
                    )}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="w-full text-xs"
                      disabled={suggestInlineMut.isPending}
                      onClick={() => suggestInlineMut.mutate()}
                    >
                      <Sparkles className={cn('h-3.5 w-3.5 mr-1.5', suggestInlineMut.isPending && 'animate-spin')} />
                      {suggestInlineMut.isPending ? 'Analyzing project data...' : 'Suggest target with AI'}
                    </Button>
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => { setShowAdd(false); resetAddDialog() }}>Cancel</Button>
                  <Button
                    disabled={!customName.trim() || createCustomMut.isPending || (customFormula.trim() !== '' && formulaValid?.valid === false)}
                    onClick={() => createCustomMut.mutate()}
                  >
                    {createCustomMut.isPending ? 'Creating...' : 'Create & Add'}
                  </Button>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit KPI Dialog */}
      <Dialog open={!!editKpiId} onOpenChange={(open) => { if (!open) setEditKpiId(null) }}>
        <DialogContent className="max-w-sm" aria-describedby={undefined}>
          {(() => {
            const editKpi = kpis.find((k) => k.id === editKpiId)
            const isCurrencyUnit = editKpi?.unit === 'currency'
            return (
              <>
                <DialogHeader>
                  <DialogTitle>Edit KPI — {editKpi?.kpi_name}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="space-y-1.5">
                    <Label>Target Value</Label>
                    <div className="flex gap-2">
                      <Input type="number" className="flex-1" value={editTarget} onChange={(e) => setEditTarget(e.target.value)} placeholder="0" />
                      {isCurrencyUnit && (
                        <Select value={editCurrency} onValueChange={setEditCurrency}>
                          <SelectTrigger className="w-[90px]"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="RON">RON</SelectItem>
                            <SelectItem value="EUR">EUR</SelectItem>
                          </SelectContent>
                        </Select>
                      )}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label>Warning Threshold</Label>
                      <Input type="number" value={editWarn} onChange={(e) => setEditWarn(e.target.value)} placeholder="Optional" />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Critical Threshold</Label>
                      <Input type="number" value={editCrit} onChange={(e) => setEditCrit(e.target.value)} placeholder="Optional" />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Channel</Label>
                    <Input value={editChannel} onChange={(e) => setEditChannel(e.target.value)} placeholder="e.g. google_ads, facebook" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Notes</Label>
                    <Textarea value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder="Optional notes" rows={2} className="resize-none" />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={() => setEditKpiId(null)}>Cancel</Button>
                    <Button disabled={editMut.isPending} onClick={() => editMut.mutate()}>
                      {editMut.isPending ? 'Saving...' : 'Save'}
                    </Button>
                  </div>
                </div>
              </>
            )
          })()}
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
        <DialogContent className="max-w-2xl" aria-describedby={undefined}>
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
                    const varDeals = linkedDealSources.filter((ds) => ds.role === varName)
                    const hasSources = varBLs.length > 0 || varDeps.length > 0 || varDeals.length > 0
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
                        {varDeals.map((ds) => (
                          <div key={`deal-${ds.id}`} className="flex items-center justify-between rounded-md bg-muted/50 px-2.5 py-1.5">
                            <div className="flex items-center gap-2 text-sm">
                              <UserCheck className="h-3.5 w-3.5 text-muted-foreground" />
                              <span>CRM Deals</span>
                              <Badge variant="outline" className="text-[10px] h-4 px-1.5">{ds.metric.replace('_', ' ')}</Badge>
                              {ds.brand_filter && <span className="text-[10px] text-muted-foreground">{ds.brand_filter}</span>}
                              {ds.source_filter && <span className="text-[10px] text-muted-foreground">{ds.source_filter === 'nw' ? 'New' : 'Used'}</span>}
                            </div>
                            <button className="hover:text-destructive" onClick={() => unlinkDealSourceMut.mutate(ds.id)}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ))}
                        <SourcePicker
                          varDeals={varDeals}
                          availableBL={availableBL}
                          availableKpis={availableKpis}
                          onLinkBL={(lineId) => linkBLMut.mutate({ lineId, role: varName })}
                          onLinkDep={(depId) => linkDepMut.mutate({ depId, role: varName })}
                          onLinkDealMetric={(metric) => linkDealSourceMut.mutate({ role: varName, metric })}
                        />
                      </div>
                    )
                  })}
                </div>
                {/* Individual Deals section */}
                <div className="rounded-lg border p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ShoppingCart className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-sm font-semibold">Individual Deals</span>
                      {linkedDeals.length > 0 && (
                        <Badge variant="default" className="text-[10px] h-4 px-1.5">{linkedDeals.length} deal{linkedDeals.length !== 1 ? 's' : ''} = +{linkedDeals.length}</Badge>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">Each linked deal counts as 1 unit toward this KPI.</p>
                  {linkedDeals.map((d) => (
                    <div key={d.id} className="flex items-center justify-between rounded-md bg-muted/50 px-2.5 py-1.5">
                      <div className="flex items-center gap-2 text-sm min-w-0">
                        <ShoppingCart className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="truncate font-medium">{d.buyer_name ?? '—'}</span>
                        <span className="text-xs text-muted-foreground shrink-0">{d.brand} {d.model_name}</span>
                        {d.contract_date && <span className="text-xs text-muted-foreground shrink-0">{new Date(d.contract_date).toLocaleDateString('ro-RO')}</span>}
                        {d.vin && <span className="font-mono text-[10px] text-muted-foreground shrink-0">{d.vin}</span>}
                      </div>
                      <button className="hover:text-destructive shrink-0 ml-2" onClick={() => unlinkDealMut.mutate(d.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                  {availableDeals.length > 0 ? (
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button variant="outline" size="sm" className="w-full text-xs h-7">
                          <Plus className="h-3 w-3 mr-1" /> Add deal from linked clients
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-[560px] p-0" align="start">
                        <div className="max-h-80 overflow-y-auto">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="text-xs">Client</TableHead>
                                <TableHead className="text-xs">Brand / Model</TableHead>
                                <TableHead className="text-xs">Date</TableHead>
                                <TableHead className="text-xs">VIN</TableHead>
                                <TableHead className="text-xs w-14" />
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {availableDeals.map((d) => (
                                <TableRow key={d.id} className="cursor-pointer hover:bg-muted/50" onClick={() => linkDealMut.mutate(d.id)}>
                                  <TableCell className="text-xs py-1.5">{d.client_name}</TableCell>
                                  <TableCell className="text-xs py-1.5">{d.brand} {d.model_name}</TableCell>
                                  <TableCell className="text-xs py-1.5">{d.contract_date ? new Date(d.contract_date).toLocaleDateString('ro-RO') : '—'}</TableCell>
                                  <TableCell className="text-xs font-mono py-1.5">{d.vin ?? '—'}</TableCell>
                                  <TableCell className="py-1.5">
                                    <Button size="sm" variant="ghost" className="h-6 text-xs px-2">Link</Button>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </PopoverContent>
                    </Popover>
                  ) : (
                    <p className="text-xs text-muted-foreground text-center py-1">
                      {linkedDeals.length > 0 ? 'All deals from linked clients are assigned.' : 'Link CRM clients first to see available deals.'}
                    </p>
                  )}
                </div>
                <div className="flex justify-end">
                  <Button variant="outline" onClick={() => {
                    // Sync the KPI to evaluate formula with newly linked sources
                    if (linkSourcesKpiId) syncMut.mutate(linkSourcesKpiId)
                    setLinkSourcesKpiId(null)
                  }}>Done</Button>
                </div>
              </>
            )
          })()}
        </DialogContent>
      </Dialog>
    </div>
  )
}
