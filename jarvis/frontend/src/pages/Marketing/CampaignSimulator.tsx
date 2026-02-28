import { useMemo, useState, useCallback, Fragment, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import {
  RotateCcw, Wand2, Plus, Users, Trash2,
  Target, DollarSign, Car, TrendingUp, ChevronDown, ChevronRight,
  Info, Sparkles, Settings2, Loader2, Save, X, Columns3, SlidersHorizontal,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { marketingApi } from '@/api/marketing'
import type { SimBenchmark, SimSettings, SimStageTotal, SimTotals } from '@/types/marketing'

// ── Constants ──

const STAGES = ['awareness', 'consideration', 'conversion'] as const
type FunnelStage = typeof STAGES[number]

const STAGE_CONFIG: Record<FunnelStage, {
  label: string; color: string
  headerBg: string; textColor: string; subtotalBg: string
}> = {
  awareness: {
    label: 'Awareness',
    color: 'text-blue-600 dark:text-blue-400',
    headerBg: 'bg-gray-300 dark:bg-gray-700',
    textColor: 'text-gray-900 dark:text-gray-100',
    subtotalBg: 'bg-gray-100 dark:bg-gray-800',
  },
  consideration: {
    label: 'Consideration',
    color: 'text-amber-600 dark:text-amber-400',
    headerBg: 'bg-gray-300 dark:bg-gray-700',
    textColor: 'text-gray-900 dark:text-gray-100',
    subtotalBg: 'bg-gray-100 dark:bg-gray-800',
  },
  conversion: {
    label: 'Conversion',
    color: 'text-green-600 dark:text-green-400',
    headerBg: 'bg-gray-300 dark:bg-gray-700',
    textColor: 'text-gray-900 dark:text-gray-100',
    subtotalBg: 'bg-gray-100 dark:bg-gray-800',
  },
}

const FALLBACK_SETTINGS: SimSettings = {
  awareness_threshold: 0.42,
  awareness_multiplier: 1.7,
  consideration_threshold: 0.14,
  consideration_multiplier: 1.5,
  auto_month_pcts: [0.40, 0.35, 0.25],
  auto_stage_weights: [
    { awareness: 0.80, consideration: 0.10, conversion: 0.10 },
    { awareness: 0.50, consideration: 0.25, conversion: 0.25 },
    { awareness: 0.20, consideration: 0.30, conversion: 0.50 },
  ],
  default_active: {
    awareness: ['meta_traffic_aw', 'meta_reach', 'meta_video_views', 'youtube_skippable_aw', 'google_display'],
    consideration: ['meta_engagement', 'special_activation'],
    conversion: ['google_pmax_conv', 'meta_conversion'],
  },
}

// ── Helpers ──

function fmtNum(n: number, decimals = 0): string {
  return n.toLocaleString('ro-RO', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}
function fmtEur(n: number): string { return `\u20AC ${fmtNum(n, 0)}` }
function fmtPct(n: number): string { return `${(n * 100).toFixed(2)}%` }

// ── Component ──

export default function CampaignSimulator() {
  const [audienceSize, setAudienceSize] = useState(300000)
  const [totalBudget, setTotalBudget] = useState(10000)
  const [leadToSaleRate, setLeadToSaleRate] = useState(5)
  const [allocations, setAllocations] = useState<Record<string, number>>({})
  const [activeChannels, setActiveChannels] = useState<Record<string, boolean>>({})
  const [activeChannelsInitialized, setActiveChannelsInitialized] = useState(false)
  const [collapsedStages, setCollapsedStages] = useState<Record<string, boolean>>({})
  const [showCalcCols, setShowCalcCols] = useState(true)
  const [showKpiDetails, setShowKpiDetails] = useState(false)
  const [showBenchmarks, setShowBenchmarks] = useState(false)
  const [addChannelStage, setAddChannelStage] = useState<FunnelStage | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiReasoning, setAiReasoning] = useState('')
  const queryClient = useQueryClient()

  const { data: settingsData } = useQuery({
    queryKey: ['sim-settings'],
    queryFn: () => marketingApi.getSimSettings(),
    staleTime: 5 * 60_000,
  })
  const cfg: SimSettings = settingsData?.settings ?? FALLBACK_SETTINGS

  const { data: benchmarkData, isLoading } = useQuery({
    queryKey: ['sim-benchmarks'],
    queryFn: () => marketingApi.getSimBenchmarks(),
    staleTime: 5 * 60_000,
  })
  const benchmarks = benchmarkData?.benchmarks ?? []

  // Initialize active channels from settings once loaded
  useEffect(() => {
    if (activeChannelsInitialized) return
    const da = cfg.default_active
    if (!da) return
    const init: Record<string, boolean> = {}
    for (const keys of Object.values(da)) {
      for (const k of keys) init[k] = true
    }
    setActiveChannels(init)
    setActiveChannelsInitialized(true)
  }, [cfg.default_active, activeChannelsInitialized])

  const channelsByStage = useMemo(() => {
    const map: Record<FunnelStage, { key: string; label: string }[]> = {
      awareness: [], consideration: [], conversion: [],
    }
    const seen = new Set<string>()
    for (const b of benchmarks) {
      if (!seen.has(b.channel_key)) {
        seen.add(b.channel_key)
        const s = b.funnel_stage as FunnelStage
        if (map[s]) map[s].push({ key: b.channel_key, label: b.channel_label })
      }
    }
    return map
  }, [benchmarks])

  const benchmarkMap = useMemo(() => {
    const m = new Map<string, SimBenchmark>()
    for (const b of benchmarks) m.set(`${b.channel_key}-${b.month_index}`, b)
    return m
  }, [benchmarks])

  // Column counts for colSpan
  const colsPerMonth = showCalcCols ? 3 : 1
  const totalCols = 1 + colsPerMonth * 3 + 1 // name + (3 months * cols) + total

  // ── Calculation engine (matching Excel formulas) ──
  const outputs = useMemo(() => {
    const byStage: Record<string, SimStageTotal> = {}
    const byMonth: Record<number, SimStageTotal> = {
      1: { budget: 0, clicks: 0, leads: 0 },
      2: { budget: 0, clicks: 0, leads: 0 },
      3: { budget: 0, clicks: 0, leads: 0 },
    }
    const kpiDetails: {
      channel_key: string; channel_label: string; funnel_stage: string
      month_index: number; budget: number; cpc: number; clicks: number
      cvr_lead: number; leads: number; cvr_car: number
    }[] = []

    for (const stage of STAGES) byStage[stage] = { budget: 0, clicks: 0, leads: 0 }

    for (const stage of STAGES) {
      for (const ch of (channelsByStage[stage] ?? [])) {
        if (!activeChannels[ch.key]) continue
        for (const month of [1, 2, 3]) {
          if (stage === 'consideration' && month === 1) continue
          const key = `${ch.key}-${month}`
          const budget = allocations[key] || 0
          const bm = benchmarkMap.get(key)
          if (!bm) continue
          const clicks = budget > 0 ? budget / bm.cpc : 0
          const leads = clicks * bm.cvr_lead
          kpiDetails.push({
            channel_key: ch.key, channel_label: ch.label,
            funnel_stage: stage, month_index: month,
            budget, cpc: bm.cpc, clicks, cvr_lead: bm.cvr_lead, leads, cvr_car: bm.cvr_car,
          })
          byStage[stage].budget += budget
          byStage[stage].clicks += clicks
          byStage[stage].leads += leads
          byMonth[month].budget += budget
          byMonth[month].clicks += clicks
          byMonth[month].leads += leads
        }
      }
    }

    const rawTotalBudget = Object.values(byStage).reduce((s, v) => s + v.budget, 0)
    const rawTotalLeads = Object.values(byStage).reduce((s, v) => s + v.leads, 0)
    const rawTotalClicks = Object.values(byStage).reduce((s, v) => s + v.clicks, 0)

    const awPct = rawTotalBudget > 0 ? byStage.awareness.budget / rawTotalBudget : 0
    const coPct = rawTotalBudget > 0 ? byStage.consideration.budget / rawTotalBudget : 0
    const awMultiplier = awPct > cfg.awareness_threshold ? cfg.awareness_multiplier : 1
    const coMultiplier = coPct > cfg.consideration_threshold ? cfg.consideration_multiplier : 1
    const totalMultiplier = awMultiplier * coMultiplier

    const m1Cvr = byMonth[1].clicks > 0 ? byMonth[1].leads / byMonth[1].clicks : 0
    const m2Cvr = byMonth[2].clicks > 0 ? byMonth[2].leads / byMonth[2].clicks : 0
    const m3Cvr = byMonth[3].clicks > 0 ? byMonth[3].leads / byMonth[3].clicks : 0
    const monthsWithData = [m1Cvr, m2Cvr, m3Cvr].filter(v => v > 0).length
    const avgCvr = monthsWithData > 0 ? (m1Cvr + m2Cvr + m3Cvr) / monthsWithData : 0
    const finalCvr = avgCvr * totalMultiplier

    const totalLeads = rawTotalLeads * totalMultiplier
    const rate = leadToSaleRate / 100
    const totalCars = totalLeads * rate

    const totals: SimTotals = {
      total_budget: rawTotalBudget, total_clicks: rawTotalClicks, total_leads: totalLeads,
      cost_per_lead: totalLeads > 0 ? rawTotalBudget / totalLeads : 0,
      total_cars: totalCars, cost_per_car: totalCars > 0 ? rawTotalBudget / totalCars : 0,
    }

    return { kpiDetails, byStage, byMonth, totals, awPct, coPct, awMultiplier, coMultiplier, totalMultiplier, rawTotalLeads, finalCvr }
  }, [allocations, activeChannels, benchmarkMap, channelsByStage, leadToSaleRate, cfg])

  const budgetRemaining = totalBudget - outputs.totals.total_budget

  // ── Actions ──
  const handleAllocationChange = useCallback((channelKey: string, month: number, value: string) => {
    setAllocations(prev => ({ ...prev, [`${channelKey}-${month}`]: parseFloat(value) || 0 }))
  }, [])

  const handleReset = useCallback(() => { setAllocations({}); setAiReasoning('') }, [])

  const handleAutoDistribute = useCallback(() => {
    const n: Record<string, number> = {}
    const monthPcts = cfg.auto_month_pcts
    const stageWeights = cfg.auto_stage_weights
    for (let mi = 0; mi < 3; mi++) {
      const month = mi + 1, mb = totalBudget * monthPcts[mi], sw = stageWeights[mi]
      for (const stage of STAGES) {
        if (stage === 'consideration' && month === 1) continue
        const sb = mb * sw[stage]
        const chs = (channelsByStage[stage] ?? []).filter(ch => activeChannels[ch.key])
        if (!chs.length) continue
        const per = sb / chs.length
        for (const ch of chs) n[`${ch.key}-${month}`] = Math.round(per)
      }
    }
    setAllocations(n); setAiReasoning('')
  }, [totalBudget, channelsByStage, activeChannels, cfg])

  const handleAiDistribute = useCallback(async () => {
    setAiLoading(true); setAiReasoning('')
    try {
      const activeByStage: Record<string, string[]> = {}
      for (const stage of STAGES) {
        const keys = (channelsByStage[stage] ?? []).filter(ch => activeChannels[ch.key]).map(ch => ch.key)
        if (keys.length > 0) activeByStage[stage] = keys
      }
      const result = await marketingApi.aiDistribute({
        total_budget: totalBudget, audience_size: audienceSize,
        lead_to_sale_rate: leadToSaleRate, active_channels: activeByStage,
        benchmarks: benchmarks.filter(b => activeChannels[b.channel_key]),
      })
      if (result.success && result.allocations) {
        const na: Record<string, number> = {}
        for (const [k, v] of Object.entries(result.allocations)) na[k] = Number(v) || 0
        setAllocations(na); setAiReasoning(result.reasoning || '')
      }
    } catch (err) { console.error('AI distribute failed:', err) }
    finally { setAiLoading(false) }
  }, [totalBudget, audienceSize, leadToSaleRate, channelsByStage, activeChannels, benchmarks])

  const toggleChannel = useCallback((key: string) => {
    setActiveChannels(prev => {
      const next = { ...prev, [key]: !prev[key] }
      if (!next[key]) setAllocations(p => { const a = { ...p }; delete a[`${key}-1`]; delete a[`${key}-2`]; delete a[`${key}-3`]; return a })
      return next
    })
  }, [])

  const toggleStageCollapse = useCallback((stage: string) => {
    setCollapsedStages(prev => ({ ...prev, [stage]: !prev[stage] }))
  }, [])

  const handleDeleteChannel = useCallback(async (channelKey: string) => {
    try {
      await marketingApi.deleteSimChannel(channelKey)
      setActiveChannels(prev => { const n = { ...prev }; delete n[channelKey]; return n })
      setAllocations(prev => {
        const n = { ...prev }; delete n[`${channelKey}-1`]; delete n[`${channelKey}-2`]; delete n[`${channelKey}-3`]; return n
      })
      queryClient.invalidateQueries({ queryKey: ['sim-benchmarks'] })
    } catch (err) { console.error('Delete channel failed:', err) }
  }, [queryClient])

  // Per-cell computed values
  function getCellCalc(ck: string, month: number) {
    const bm = benchmarkMap.get(`${ck}-${month}`)
    const budget = allocations[`${ck}-${month}`] || 0
    if (!bm || budget <= 0) return { clicks: 0, leads: 0 }
    const clicks = budget / bm.cpc
    return { clicks, leads: clicks * bm.cvr_lead }
  }

  function getChannelRowTotal(ck: string, stage: FunnelStage) {
    let t = 0; for (const m of [1, 2, 3]) { if (stage === 'consideration' && m === 1) continue; t += allocations[`${ck}-${m}`] || 0 }; return t
  }
  function getStageMonthBudget(stage: FunnelStage, month: number) {
    let t = 0; for (const ch of (channelsByStage[stage] ?? [])) { if (!activeChannels[ch.key] || (stage === 'consideration' && month === 1)) continue; t += allocations[`${ch.key}-${month}`] || 0 }; return t
  }
  function getStageMonthCalc(stage: FunnelStage, month: number) {
    let clicks = 0, leads = 0
    for (const ch of (channelsByStage[stage] ?? [])) {
      if (!activeChannels[ch.key] || (stage === 'consideration' && month === 1)) continue
      const c = getCellCalc(ch.key, month); clicks += c.clicks; leads += c.leads
    }
    return { clicks, leads }
  }
  function getStageTotal(stage: FunnelStage) {
    let t = 0; for (const ch of (channelsByStage[stage] ?? [])) { if (!activeChannels[ch.key]) continue; for (const m of [1, 2, 3]) { if (stage === 'consideration' && m === 1) continue; t += allocations[`${ch.key}-${m}`] || 0 } }; return t
  }

  if (isLoading) return <div className="space-y-4 mt-4"><Skeleton className="h-32 w-full" /><Skeleton className="h-96 w-full" /></div>

  return (
    <div className="space-y-4">
      <PageHeader
        title="Simulator"
        breadcrumbs={[
          { label: 'Marketing', shortLabel: 'Mkt.', href: '/app/marketing' },
          { label: 'Simulator' },
        ]}
      />
      {/* ── Header ── */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-wrap items-end gap-3 flex-1 min-w-0">
              <div className="space-y-1 flex-1 min-w-[120px] max-w-[160px]">
                <Label className="text-xs text-muted-foreground flex items-center gap-1"><Users className="h-3 w-3" /> Dimensiune audienta</Label>
                <Input type="number" className="h-8 text-sm" value={audienceSize} onChange={e => setAudienceSize(parseInt(e.target.value) || 0)} />
              </div>
              <div className="space-y-1 flex-1 min-w-[120px] max-w-[160px]">
                <Label className="text-xs text-muted-foreground flex items-center gap-1"><DollarSign className="h-3 w-3" /> Buget Disponibil (EUR)</Label>
                <Input type="number" className="h-8 text-sm" value={totalBudget} onChange={e => setTotalBudget(parseFloat(e.target.value) || 0)} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Ramas:</span>
                <Badge variant={budgetRemaining < 0 ? 'destructive' : budgetRemaining === 0 ? 'default' : 'secondary'} className="text-xs tabular-nums">{fmtEur(budgetRemaining)}</Badge>
              </div>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              <Button variant={showCalcCols ? 'default' : 'outline'} size="icon" className="md:size-auto md:px-3" onClick={() => setShowCalcCols(!showCalcCols)} title="Toggle KPI columns">
                <Columns3 className="h-3.5 w-3.5 md:mr-1" />
                <span className="hidden md:inline">{showCalcCols ? 'Hide' : 'Show'} KPI</span>
              </Button>
              <Button variant="outline" size="icon" className="md:size-auto md:px-3" onClick={handleReset} title="Reset">
                <RotateCcw className="h-3.5 w-3.5 md:mr-1" />
                <span className="hidden md:inline">Reset</span>
              </Button>
              <Button variant="outline" size="icon" className="md:size-auto md:px-3" onClick={handleAutoDistribute} title="Auto-Distribute">
                <Wand2 className="h-3.5 w-3.5 md:mr-1" />
                <span className="hidden md:inline">Auto-Distribute</span>
              </Button>
              <Button size="icon" className="md:size-auto md:px-3 bg-purple-600 hover:bg-purple-700 text-white" onClick={handleAiDistribute} disabled={aiLoading} title="AI Distribute">
                {aiLoading ? <Loader2 className="h-3.5 w-3.5 md:mr-1 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 md:mr-1" />}
                <span className="hidden md:inline">AI Distribute</span>
              </Button>
              <Button variant="ghost" size="icon" onClick={() => setShowBenchmarks(true)} title="Settings"><Settings2 className="h-3.5 w-3.5" /></Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {aiReasoning && (
        <Card className="border-purple-200 dark:border-purple-800 bg-purple-50/50 dark:bg-purple-950/20">
          <CardContent className="py-3 flex items-start gap-2">
            <Sparkles className="h-4 w-4 text-purple-600 shrink-0 mt-0.5" />
            <div className="text-sm text-purple-800 dark:text-purple-200">{aiReasoning}</div>
            <button onClick={() => setAiReasoning('')} className="shrink-0 ml-auto"><X className="h-3.5 w-3.5 text-muted-foreground" /></button>
          </CardContent>
        </Card>
      )}

      {/* ── Budget Table (Excel Modul 4) ── */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="text-xs">
                  <TableHead className="w-40 md:w-64 sticky left-0 bg-background z-10 font-bold">Canal / Funnel</TableHead>
                  {[1, 2, 3].map(m => (
                    <Fragment key={m}>
                      <TableHead className={cn('text-center w-28 border-l', !showCalcCols && 'w-28')}>Luna {m}</TableHead>
                      {showCalcCols && <TableHead className="text-center w-20 text-muted-foreground text-[10px]">Clicks</TableHead>}
                      {showCalcCols && <TableHead className="text-center w-20 text-muted-foreground text-[10px]">Leads</TableHead>}
                    </Fragment>
                  ))}
                  <TableHead className="text-right w-28 border-l font-bold">TOTAL</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {STAGES.map(stage => {
                  const cfg = STAGE_CONFIG[stage]
                  const channels = channelsByStage[stage] ?? []
                  const activeList = channels.filter(ch => activeChannels[ch.key])
                  const isCollapsed = collapsedStages[stage]
                  const stTotal = getStageTotal(stage)
                  return (
                    <Fragment key={stage}>
                      {/* Stage header row */}
                      <TableRow className={cn(cfg.headerBg, cfg.textColor, 'cursor-pointer hover:opacity-90')} onClick={() => toggleStageCollapse(stage)}>
                        <TableCell className="py-1.5 font-bold text-xs sticky left-0 bg-inherit">
                          <div className="flex items-center gap-2">
                            {isCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                            {cfg.label}
                            <span className="font-normal opacity-70">({activeList.length}/{channels.length})</span>
                            <div className="ml-auto flex items-center gap-1">
                              <Popover>
                                <PopoverTrigger asChild onClick={e => e.stopPropagation()}>
                                  <button className="opacity-70 hover:opacity-100" title="Toggle channels"><Plus className="h-3.5 w-3.5" /></button>
                                </PopoverTrigger>
                                <PopoverContent className="w-56 p-2" onClick={e => e.stopPropagation()}>
                                  <p className="text-xs font-medium mb-2">Toggle channels</p>
                                  {channels.map(ch => (
                                    <label key={ch.key} className="flex items-center gap-2 py-1 text-xs cursor-pointer hover:bg-accent rounded px-1">
                                      <Checkbox checked={!!activeChannels[ch.key]} onCheckedChange={() => toggleChannel(ch.key)} />
                                      {ch.label}
                                    </label>
                                  ))}
                                  <div className="border-t mt-2 pt-2">
                                    <button
                                      className="flex items-center gap-1 text-xs text-primary hover:underline w-full"
                                      onClick={(e) => { e.stopPropagation(); setAddChannelStage(stage) }}
                                    >
                                      <Plus className="h-3 w-3" /> Add new channel
                                    </button>
                                  </div>
                                </PopoverContent>
                              </Popover>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell colSpan={colsPerMonth * 3} className="py-1.5 border-l" />
                        <TableCell className="py-1.5 border-l" />
                      </TableRow>

                      {/* Channel rows */}
                      {!isCollapsed && activeList.map(ch => {
                        const rowTotal = getChannelRowTotal(ch.key, stage)
                        return (
                          <TableRow key={ch.key} className="text-xs hover:bg-accent/30 group">
                            <TableCell className="py-1 font-medium sticky left-0 bg-background text-xs pl-8">
                              <div className="flex items-center gap-1">
                                <span className="truncate">{ch.label}</span>
                                <button
                                  className="opacity-0 group-hover:opacity-60 hover:!opacity-100 shrink-0 ml-auto text-destructive"
                                  title="Delete channel"
                                  onClick={() => { if (confirm(`Delete "${ch.label}"?`)) handleDeleteChannel(ch.key) }}
                                >
                                  <Trash2 className="h-3 w-3" />
                                </button>
                              </div>
                            </TableCell>
                            {[1, 2, 3].map(month => {
                              const dis = stage === 'consideration' && month === 1
                              const ak = `${ch.key}-${month}`
                              const bgt = allocations[ak] || 0
                              const calc = getCellCalc(ch.key, month)
                              return (
                                <Fragment key={ak}>
                                  <TableCell className={cn('py-1 text-center border-l')}>
                                    {dis ? <span className="text-muted-foreground/30">{'\u2014'}</span> : (
                                      <Input type="number" className="w-24 h-6 text-xs text-center px-1 bg-orange-50/60 dark:bg-orange-950/20 border-orange-200 dark:border-orange-800"
                                        value={bgt || ''} placeholder="0" onChange={e => handleAllocationChange(ch.key, month, e.target.value)} />
                                    )}
                                  </TableCell>
                                  {showCalcCols && (
                                    <TableCell className="py-1 text-center text-[11px] tabular-nums text-muted-foreground">
                                      {dis ? '\u2014' : calc.clicks > 0 ? fmtNum(calc.clicks) : '-'}
                                    </TableCell>
                                  )}
                                  {showCalcCols && (
                                    <TableCell className="py-1 text-center text-[11px] tabular-nums font-medium">
                                      {dis ? '\u2014' : calc.leads > 0 ? fmtNum(calc.leads, 2) : '-'}
                                    </TableCell>
                                  )}
                                </Fragment>
                              )
                            })}
                            <TableCell className="py-1 text-right text-xs font-medium tabular-nums border-l">{rowTotal > 0 ? fmtEur(rowTotal) : '\u20AC -'}</TableCell>
                          </TableRow>
                        )
                      })}

                      {/* Subtotal row */}
                      <TableRow className={cn(cfg.subtotalBg, 'font-bold text-xs')}>
                        <TableCell className="py-1.5 sticky left-0 bg-inherit font-bold pl-4">TOTAL ({cfg.label})</TableCell>
                        {[1, 2, 3].map(m => {
                          const mb = getStageMonthBudget(stage, m)
                          const mc = getStageMonthCalc(stage, m)
                          return (
                            <Fragment key={m}>
                              <TableCell className={cn('py-1.5 text-center tabular-nums border-l')}>{fmtEur(mb)}</TableCell>
                              {showCalcCols && <TableCell className="py-1.5 text-center tabular-nums text-[11px] text-muted-foreground">{mc.clicks > 0 ? fmtNum(mc.clicks) : '-'}</TableCell>}
                              {showCalcCols && <TableCell className="py-1.5 text-center tabular-nums text-[11px]">{mc.leads > 0 ? fmtNum(mc.leads, 1) : '-'}</TableCell>}
                            </Fragment>
                          )
                        })}
                        <TableCell className="py-1.5 text-right tabular-nums border-l">{fmtEur(stTotal)}</TableCell>
                      </TableRow>
                      <TableRow className="h-2"><TableCell colSpan={totalCols} className="p-0" /></TableRow>
                    </Fragment>
                  )
                })}

                {/* Grand total row */}
                <TableRow className="bg-gray-200 dark:bg-gray-700 font-bold text-xs">
                  <TableCell className="py-2 sticky left-0 bg-inherit font-bold">TOTAL CAMPANIE / LUNA</TableCell>
                  {[1, 2, 3].map(m => (
                    <Fragment key={m}>
                      <TableCell className={cn('py-2 text-center tabular-nums border-l')}>{fmtEur(outputs.byMonth[m].budget)}</TableCell>
                      {showCalcCols && <TableCell className="py-2 text-center tabular-nums text-[11px]">{outputs.byMonth[m].clicks > 0 ? fmtNum(outputs.byMonth[m].clicks) : '-'}</TableCell>}
                      {showCalcCols && <TableCell className="py-2 text-center tabular-nums text-[11px]">{outputs.byMonth[m].leads > 0 ? fmtNum(outputs.byMonth[m].leads, 1) : '-'}</TableCell>}
                    </Fragment>
                  ))}
                  <TableCell className="py-2 text-right tabular-nums border-l" />
                </TableRow>

                {/* Summary rows */}
                <SummaryRow label="Buget CONSUMAT" value={fmtEur(outputs.totals.total_budget)} colsPerMonth={colsPerMonth} totalCols={totalCols} />
                <SummaryRow label="CVR" value={outputs.finalCvr > 0 ? fmtPct(outputs.finalCvr) : '0,00%'} colsPerMonth={colsPerMonth} totalCols={totalCols} />
                <SummaryRow label="Numar Lead-uri" value={fmtNum(outputs.totals.total_leads, 1)} highlight={outputs.totalMultiplier > 1} colsPerMonth={colsPerMonth} totalCols={totalCols} />
                <SummaryRow label="Cost / Lead" value={outputs.totals.cost_per_lead > 0 ? fmtEur(outputs.totals.cost_per_lead) : '\u20AC -'} colsPerMonth={colsPerMonth} totalCols={totalCols} />
                <TableRow className="text-xs">
                  <TableCell className="py-1.5 sticky left-0 bg-background font-medium">CVR (Lead {'\u2192'} Sale)</TableCell>
                  <TableCell className="py-1.5 text-center border-l" colSpan={colsPerMonth * 2}>
                    <Input type="number" className="w-20 h-6 text-xs text-center px-1 mx-auto bg-orange-50/60 dark:bg-orange-950/20 border-orange-200 dark:border-orange-800"
                      value={leadToSaleRate} step={0.5} onChange={e => setLeadToSaleRate(parseFloat(e.target.value) || 0)} />
                  </TableCell>
                  <TableCell className="py-1.5" colSpan={colsPerMonth} />
                  <TableCell className="py-1.5 border-l" />
                </TableRow>
                <SummaryRow label="Masini Vandute" value={fmtNum(outputs.totals.total_cars, 1)} bold colsPerMonth={colsPerMonth} totalCols={totalCols} />
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* ── Synergy Multipliers ── */}
      {(outputs.awMultiplier > 1 || outputs.coMultiplier > 1) && (
        <Card className="border-amber-300 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-950/20">
          <CardContent className="py-3">
            <div className="flex items-center gap-3 text-sm flex-wrap">
              <TrendingUp className="h-4 w-4 text-amber-600" />
              <span className="font-medium text-amber-800 dark:text-amber-200">Funnel Synergy Bonus Active!</span>
              <div className="flex gap-2 flex-wrap text-xs">
                {outputs.awMultiplier > 1 && <Badge variant="outline" className="border-blue-400 text-blue-700 dark:text-blue-300">Awareness {fmtPct(outputs.awPct)} &gt; {fmtPct(cfg.awareness_threshold)} {'\u2192'} {outputs.awMultiplier}x</Badge>}
                {outputs.coMultiplier > 1 && <Badge variant="outline" className="border-amber-400 text-amber-700 dark:text-amber-300">Consideration {fmtPct(outputs.coPct)} &gt; {fmtPct(cfg.consideration_threshold)} {'\u2192'} {outputs.coMultiplier}x</Badge>}
                <Badge className="bg-green-600 text-white">Total: {outputs.totalMultiplier}x {'\u2192'} {fmtNum(outputs.totals.total_leads, 1)} leads</Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Results ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <ResultCard icon={<Target className="h-4 w-4 text-green-600" />} label="Total Leads" value={fmtNum(outputs.totals.total_leads, 1)} sub={outputs.totalMultiplier > 1 ? `${fmtNum(outputs.rawTotalLeads, 1)} \u00D7 ${outputs.totalMultiplier}x` : undefined} />
        <ResultCard icon={<DollarSign className="h-4 w-4 text-blue-600" />} label="Cost / Lead" value={outputs.totals.cost_per_lead > 0 ? `\u20AC ${fmtNum(outputs.totals.cost_per_lead, 2)}` : '-'} />
        <ResultCard icon={<Car className="h-4 w-4 text-purple-600" />} label="Masini Vandute" value={fmtNum(outputs.totals.total_cars, 1)} sub={`${leadToSaleRate}% conversion`} />
        <ResultCard icon={<DollarSign className="h-4 w-4 text-red-600" />} label="Cost / Masina" value={outputs.totals.cost_per_car > 0 ? `\u20AC ${fmtNum(outputs.totals.cost_per_car, 2)}` : '-'} />
      </div>

      {/* ── Funnel + Budget Split ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card>
          <CardHeader className="py-3 px-4"><CardTitle className="text-sm flex items-center gap-2"><TrendingUp className="h-4 w-4" /> Funnel Flow</CardTitle></CardHeader>
          <CardContent className="pb-4 px-4"><FunnelVis audience={audienceSize} clicks={outputs.totals.total_clicks} leads={outputs.totals.total_leads} cars={outputs.totals.total_cars} /></CardContent>
        </Card>
        <Card>
          <CardHeader className="py-3 px-4"><CardTitle className="text-sm flex items-center gap-2"><DollarSign className="h-4 w-4" /> Budget Split</CardTitle></CardHeader>
          <CardContent className="pb-4 px-4">
            <div className="space-y-3">
              {STAGES.map(stage => {
                const sb = outputs.byStage[stage]?.budget || 0
                const pct = outputs.totals.total_budget > 0 ? sb / outputs.totals.total_budget : 0
                const sc = STAGE_CONFIG[stage]
                const th = stage === 'awareness' ? cfg.awareness_threshold : stage === 'consideration' ? cfg.consideration_threshold : null
                return (
                  <div key={stage} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className={cn('font-medium', sc.color)}>{sc.label}</span>
                      <span className="tabular-nums">{fmtEur(sb)} ({fmtPct(pct)}){th !== null && pct > th && <span className="text-green-600 ml-1">{'\u2713'}</span>}</span>
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 relative">
                      <div className={cn('h-2 rounded-full', stage === 'awareness' ? 'bg-blue-500' : stage === 'consideration' ? 'bg-amber-500' : 'bg-green-500')} style={{ width: `${Math.min(pct * 100, 100)}%` }} />
                      {th !== null && <div className="absolute top-0 h-2 w-0.5 bg-red-500" style={{ left: `${th * 100}%` }} title={`Threshold: ${fmtPct(th)}`} />}
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── KPI Details ── */}
      <Button variant="outline" size="sm" onClick={() => setShowKpiDetails(!showKpiDetails)} className="text-xs">
        {showKpiDetails ? <ChevronDown className="h-3 w-3 mr-1" /> : <ChevronRight className="h-3 w-3 mr-1" />}
        {showKpiDetails ? 'Hide' : 'Show'} KPI Details (CPC / Clicks / CVR / Leads)
      </Button>
      {showKpiDetails && <KpiTable channelsByStage={channelsByStage} activeChannels={activeChannels} benchmarkMap={benchmarkMap} allocations={allocations} />}

      <div className="text-xs text-muted-foreground flex items-start gap-2 px-1">
        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
        <span>Benchmarks sourced from Toyota Digital Masterclass (Romanian automotive market). CPC and CVR rates vary by month to model audience fatigue (awareness) and retargeting lift (consideration/conversion). Funnel synergy: spending &gt;{fmtPct(cfg.awareness_threshold)} on awareness gives a {cfg.awareness_multiplier}x lead multiplier; &gt;{fmtPct(cfg.consideration_threshold)} on consideration gives {cfg.consideration_multiplier}x. These stack for up to {(cfg.awareness_multiplier * cfg.consideration_multiplier).toFixed(2)}x total.</span>
      </div>

      {/* Dialogs */}
      <BenchmarkEditor open={showBenchmarks} onClose={() => setShowBenchmarks(false)} benchmarks={benchmarks} channelsByStage={channelsByStage} settings={cfg} onSaved={() => { queryClient.invalidateQueries({ queryKey: ['sim-benchmarks'] }); queryClient.invalidateQueries({ queryKey: ['sim-settings'] }) }} />
      <AddChannelDialog
        stage={addChannelStage}
        onClose={() => setAddChannelStage(null)}
        onCreated={(channelKey) => {
          setActiveChannels(prev => ({ ...prev, [channelKey]: true }))
          queryClient.invalidateQueries({ queryKey: ['sim-benchmarks'] })
        }}
      />
    </div>
  )
}

// ── Sub-components ──

function SummaryRow({ label, value, bold, highlight, colsPerMonth, totalCols }: {
  label: string; value: string; bold?: boolean; highlight?: boolean; colsPerMonth: number; totalCols: number
}) {
  void totalCols
  return (
    <TableRow className={cn('text-xs', highlight && 'bg-green-50/50 dark:bg-green-950/20')}>
      <TableCell className={cn('py-1.5 sticky left-0 bg-inherit', bold ? 'font-bold' : 'font-medium')}>{label}</TableCell>
      <TableCell className="py-1.5 text-center border-l tabular-nums" colSpan={colsPerMonth * 2}><span className={bold ? 'font-bold' : ''}>{value}</span></TableCell>
      <TableCell className="py-1.5" colSpan={colsPerMonth} /><TableCell className="py-1.5 border-l" />
    </TableRow>
  )
}

function ResultCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <Card><CardContent className="py-3 px-4">
      <div className="flex items-center gap-2 mb-1">{icon}<span className="text-xs text-muted-foreground">{label}</span></div>
      <p className="text-xl font-bold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </CardContent></Card>
  )
}

function FunnelVis({ audience, clicks, leads, cars }: { audience: number; clicks: number; leads: number; cars: number }) {
  const steps = [
    { label: 'Audienta', value: audience, color: 'bg-blue-500' },
    { label: 'Clicks', value: clicks, color: 'bg-amber-500' },
    { label: 'Lead-uri', value: leads, color: 'bg-green-500' },
    { label: 'Masini', value: cars, color: 'bg-purple-500' },
  ]
  const maxVal = Math.max(audience, 1)
  return (
    <div className="space-y-2">
      {steps.map(step => (
        <div key={step.label} className="flex items-center gap-3">
          <span className="text-xs w-16 text-right text-muted-foreground shrink-0">{step.label}</span>
          <div className="flex-1 flex items-center gap-2">
            <div className={cn('h-6 rounded flex items-center justify-end px-2 transition-all', step.color)} style={{ width: `${Math.max((step.value / maxVal) * 100, 4)}%` }}>
              <span className="text-[10px] font-semibold text-white whitespace-nowrap">{fmtNum(step.value, step.value < 100 ? 1 : 0)}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function KpiTable({ channelsByStage, activeChannels, benchmarkMap, allocations }: {
  channelsByStage: Record<FunnelStage, { key: string; label: string }[]>
  activeChannels: Record<string, boolean>
  benchmarkMap: Map<string, SimBenchmark>
  allocations: Record<string, number>
}) {
  return (
    <Card><CardContent className="p-0"><div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="text-xs">
            <TableHead className="w-48 sticky left-0 bg-background z-10">Channel</TableHead>
            {[1, 2, 3].map(m => <TableHead key={m} className="text-center border-l" colSpan={5}>Luna {m}</TableHead>)}
          </TableRow>
          <TableRow className="text-[10px] text-muted-foreground">
            <TableHead className="sticky left-0 bg-background z-10" />
            {[1, 2, 3].map(m => (
              <Fragment key={m}>
                <TableHead className="text-right border-l">CPC</TableHead>
                <TableHead className="text-right">Clicks</TableHead>
                <TableHead className="text-right">CVR Lead</TableHead>
                <TableHead className="text-right">Leads</TableHead>
                <TableHead className="text-right">CVR Car</TableHead>
              </Fragment>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {STAGES.map(stage => {
            const cfg = STAGE_CONFIG[stage]
            const chs = (channelsByStage[stage] ?? []).filter(ch => activeChannels[ch.key])
            return (
              <Fragment key={stage}>
                <TableRow className={cfg.headerBg}><TableCell colSpan={16} className={cn('py-1 text-xs font-bold', cfg.textColor)}>{cfg.label}</TableCell></TableRow>
                {chs.map(ch => (
                  <TableRow key={ch.key} className="text-xs">
                    <TableCell className="py-1 font-medium sticky left-0 bg-background text-[11px]">{ch.label}</TableCell>
                    {[1, 2, 3].map(month => {
                      const dis = stage === 'consideration' && month === 1
                      const bm = benchmarkMap.get(`${ch.key}-${month}`)
                      const budget = allocations[`${ch.key}-${month}`] || 0
                      const clicks = bm && budget > 0 ? budget / bm.cpc : 0
                      const leads = bm ? clicks * bm.cvr_lead : 0
                      if (dis || !bm) return <Fragment key={month}><TableCell className="py-1 text-right text-muted-foreground/30 border-l">{'\u2014'}</TableCell><TableCell className="py-1 text-right text-muted-foreground/30">{'\u2014'}</TableCell><TableCell className="py-1 text-right text-muted-foreground/30">{'\u2014'}</TableCell><TableCell className="py-1 text-right text-muted-foreground/30">{'\u2014'}</TableCell><TableCell className="py-1 text-right text-muted-foreground/30">{'\u2014'}</TableCell></Fragment>
                      return (
                        <Fragment key={month}>
                          <TableCell className="py-1 text-right tabular-nums border-l">{bm.cpc.toFixed(2)}</TableCell>
                          <TableCell className="py-1 text-right tabular-nums">{clicks > 0 ? fmtNum(clicks) : '0'}</TableCell>
                          <TableCell className="py-1 text-right tabular-nums">{fmtPct(bm.cvr_lead)}</TableCell>
                          <TableCell className="py-1 text-right tabular-nums font-medium">{leads > 0 ? fmtNum(leads, 2) : '0'}</TableCell>
                          <TableCell className="py-1 text-right tabular-nums text-muted-foreground">{fmtPct(bm.cvr_car)}</TableCell>
                        </Fragment>
                      )
                    })}
                  </TableRow>
                ))}
              </Fragment>
            )
          })}
        </TableBody>
      </Table>
    </div></CardContent></Card>
  )
}

function BenchmarkEditor({ open, onClose, benchmarks, channelsByStage, settings, onSaved }: {
  open: boolean; onClose: () => void; benchmarks: SimBenchmark[]
  channelsByStage: Record<FunnelStage, { key: string; label: string }[]>
  settings: SimSettings; onSaved: () => void
}) {
  const [edits, setEdits] = useState<Record<string, Partial<SimBenchmark>>>({})
  const [draft, setDraft] = useState<SimSettings>(settings)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) { setDraft(settings); setEdits({}) } }, [open, settings])

  const handleEdit = (id: number, field: 'cpc' | 'cvr_lead' | 'cvr_car', value: string) => {
    const num = parseFloat(value); if (isNaN(num)) return
    setEdits(prev => ({ ...prev, [id]: { ...prev[id], [field]: num } }))
  }
  const getVal = (bm: SimBenchmark, field: 'cpc' | 'cvr_lead' | 'cvr_car'): number => {
    const e = edits[bm.id]; if (e && field in e) return e[field] as number; return bm[field]
  }

  const settingsChanged = JSON.stringify(draft) !== JSON.stringify(settings)
  const benchmarkChanges = Object.keys(edits).length
  const hasChanges = settingsChanged || benchmarkChanges > 0

  const handleSave = async () => {
    setSaving(true)
    try {
      const promises: Promise<unknown>[] = []
      if (benchmarkChanges > 0) {
        const updates = Object.entries(edits).map(([id, f]) => ({ id: Number(id), ...f }))
        promises.push(marketingApi.bulkUpdateSimBenchmarks(updates))
      }
      if (settingsChanged) {
        promises.push(marketingApi.updateSimSettings(draft))
      }
      await Promise.all(promises)
      setEdits({})
      onSaved()
    } catch (err) { console.error('Failed to save:', err) }
    finally { setSaving(false) }
  }

  const updateWeight = (mi: number, stage: FunnelStage, value: number) => {
    setDraft(prev => {
      const weights = [...prev.auto_stage_weights] as SimSettings['auto_stage_weights']
      weights[mi] = { ...weights[mi], [stage]: value }
      return { ...prev, auto_stage_weights: weights }
    })
  }
  const updateMonthPct = (mi: number, value: number) => {
    setDraft(prev => {
      const pcts = [...prev.auto_month_pcts] as SimSettings['auto_month_pcts']
      pcts[mi] = value
      return { ...prev, auto_month_pcts: pcts }
    })
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent className="sm:max-w-[90vw] w-[90vw] max-h-[85vh] overflow-y-auto" aria-describedby={undefined}>
        <DialogHeader><DialogTitle className="flex items-center gap-2"><Settings2 className="h-4 w-4" /> Simulator Settings</DialogTitle></DialogHeader>

        {/* ── Collapsible Settings Section ── */}
        <div className="border rounded-md">
          <button
            className="flex items-center gap-2 w-full px-3 py-2 text-xs font-semibold text-muted-foreground hover:bg-accent/50 rounded-md"
            onClick={() => setSettingsOpen(!settingsOpen)}
          >
            {settingsOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Funnel Synergy & Auto-Distribute
            {settingsChanged && <Badge variant="outline" className="ml-auto text-[10px] border-amber-400 text-amber-600">modified</Badge>}
          </button>
          {settingsOpen && (
            <div className="px-3 pb-3 space-y-4 border-t">
              {/* Synergy Thresholds */}
              <div className="space-y-2 pt-3">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Funnel Synergy Multipliers</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Awareness Threshold</Label>
                    <div className="flex items-center gap-1">
                      <Input type="number" step="0.01" min="0" max="1" className="h-7 text-xs w-20"
                        value={draft.awareness_threshold} onChange={e => setDraft(d => ({ ...d, awareness_threshold: parseFloat(e.target.value) || 0 }))} />
                      <span className="text-[10px] text-muted-foreground">({fmtPct(draft.awareness_threshold)})</span>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Awareness Multiplier</Label>
                    <Input type="number" step="0.1" min="1" className="h-7 text-xs w-20"
                      value={draft.awareness_multiplier} onChange={e => setDraft(d => ({ ...d, awareness_multiplier: parseFloat(e.target.value) || 1 }))} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Consideration Threshold</Label>
                    <div className="flex items-center gap-1">
                      <Input type="number" step="0.01" min="0" max="1" className="h-7 text-xs w-20"
                        value={draft.consideration_threshold} onChange={e => setDraft(d => ({ ...d, consideration_threshold: parseFloat(e.target.value) || 0 }))} />
                      <span className="text-[10px] text-muted-foreground">({fmtPct(draft.consideration_threshold)})</span>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Consideration Multiplier</Label>
                    <Input type="number" step="0.1" min="1" className="h-7 text-xs w-20"
                      value={draft.consideration_multiplier} onChange={e => setDraft(d => ({ ...d, consideration_multiplier: parseFloat(e.target.value) || 1 }))} />
                  </div>
                </div>
              </div>
              {/* Auto-distribute */}
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Auto-Distribute: Month Budget Split</h4>
                <div className="grid grid-cols-3 gap-3">
                  {[0, 1, 2].map(mi => (
                    <div key={mi} className="space-y-1">
                      <Label className="text-xs">Luna {mi + 1}</Label>
                      <div className="flex items-center gap-1">
                        <Input type="number" step="0.05" min="0" max="1" className="h-7 text-xs w-20"
                          value={draft.auto_month_pcts[mi]} onChange={e => updateMonthPct(mi, parseFloat(e.target.value) || 0)} />
                        <span className="text-[10px] text-muted-foreground">{fmtPct(draft.auto_month_pcts[mi])}</span>
                      </div>
                    </div>
                  ))}
                </div>
                {Math.abs(draft.auto_month_pcts.reduce((s, v) => s + v, 0) - 1) > 0.01 && (
                  <p className="text-xs text-destructive">Month percentages should sum to 100%</p>
                )}
              </div>
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Auto-Distribute: Stage Weights per Month</h4>
                {[0, 1, 2].map(mi => (
                  <div key={mi} className="space-y-1">
                    <Label className="text-xs font-medium">Luna {mi + 1}</Label>
                    <div className="grid grid-cols-3 gap-2">
                      {STAGES.map(stage => (
                        <div key={stage} className="space-y-0.5">
                          <Label className="text-[10px] text-muted-foreground">{STAGE_CONFIG[stage].label}</Label>
                          <Input type="number" step="0.05" min="0" max="1" className="h-6 text-xs"
                            value={draft.auto_stage_weights[mi][stage]}
                            onChange={e => updateWeight(mi, stage, parseFloat(e.target.value) || 0)} />
                        </div>
                      ))}
                    </div>
                    {Math.abs(STAGES.reduce((s, st) => s + (draft.auto_stage_weights[mi][st] || 0), 0) - 1) > 0.01 && (
                      <p className="text-[10px] text-destructive">Weights for Luna {mi + 1} should sum to 100%</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Benchmarks Table ── */}
        <div className="text-xs text-muted-foreground">Adjust CPC and CVR rates per channel per month.</div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="text-xs">
                <TableHead className="w-48">Channel</TableHead>
                {[1, 2, 3].map(m => <TableHead key={m} className="text-center border-l" colSpan={3}>Luna {m}</TableHead>)}
              </TableRow>
              <TableRow className="text-[10px] text-muted-foreground">
                <TableHead />
                {[1, 2, 3].map(m => <Fragment key={m}><TableHead className="text-center border-l">CPC</TableHead><TableHead className="text-center">CVR Lead</TableHead><TableHead className="text-center">CVR Car</TableHead></Fragment>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              {STAGES.map(stage => {
                const sc = STAGE_CONFIG[stage]
                return (
                  <Fragment key={stage}>
                    <TableRow className={sc.headerBg}><TableCell colSpan={10} className={cn('py-1 text-xs font-bold', sc.textColor)}>{sc.label}</TableCell></TableRow>
                    {(channelsByStage[stage] ?? []).map(ch => (
                      <TableRow key={ch.key} className="text-xs">
                        <TableCell className="py-1 font-medium text-[11px]">{ch.label}</TableCell>
                        {[1, 2, 3].map(month => {
                          const dis = stage === 'consideration' && month === 1
                          const bm = benchmarks.find(b => b.channel_key === ch.key && b.month_index === month)
                          if (dis || !bm) return <Fragment key={month}><TableCell className="py-1 text-center text-muted-foreground/30 border-l">{'\u2014'}</TableCell><TableCell className="py-1 text-center text-muted-foreground/30">{'\u2014'}</TableCell><TableCell className="py-1 text-center text-muted-foreground/30">{'\u2014'}</TableCell></Fragment>
                          const isEd = !!edits[bm.id]
                          return (
                            <Fragment key={month}>
                              <TableCell className="py-1 border-l"><Input type="number" step="0.01" className={cn('w-16 h-5 text-[11px] text-center px-0.5', isEd && 'border-amber-400')} value={getVal(bm, 'cpc')} onChange={e => handleEdit(bm.id, 'cpc', e.target.value)} /></TableCell>
                              <TableCell className="py-1"><Input type="number" step="0.0001" className={cn('w-20 h-5 text-[11px] text-center px-0.5', isEd && 'border-amber-400')} value={getVal(bm, 'cvr_lead')} onChange={e => handleEdit(bm.id, 'cvr_lead', e.target.value)} /></TableCell>
                              <TableCell className="py-1"><Input type="number" step="0.0001" className={cn('w-20 h-5 text-[11px] text-center px-0.5', isEd && 'border-amber-400')} value={getVal(bm, 'cvr_car')} onChange={e => handleEdit(bm.id, 'cvr_car', e.target.value)} /></TableCell>
                            </Fragment>
                          )
                        })}
                      </TableRow>
                    ))}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" size="sm" onClick={onClose}><X className="h-3.5 w-3.5 mr-1" /> Close</Button>
          <Button size="sm" onClick={handleSave} disabled={!hasChanges || saving}>
            {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
            Save {hasChanges ? `(${benchmarkChanges}${settingsChanged ? ' + settings' : ''})` : ''}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function AddChannelDialog({ stage, onClose, onCreated }: {
  stage: FunnelStage | null; onClose: () => void; onCreated: (channelKey: string) => void
}) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [m1, setM1] = useState({ cpc: 0.10, cvr_lead: 0.002, cvr_car: 0.0005 })
  const [m2, setM2] = useState({ cpc: 0.10, cvr_lead: 0.002, cvr_car: 0.0005 })
  const [m3, setM3] = useState({ cpc: 0.10, cvr_lead: 0.002, cvr_car: 0.0005 })
  const [error, setError] = useState('')

  const resetForm = () => {
    setName(''); setError('')
    setM1({ cpc: 0.10, cvr_lead: 0.002, cvr_car: 0.0005 })
    setM2({ cpc: 0.10, cvr_lead: 0.002, cvr_car: 0.0005 })
    setM3({ cpc: 0.10, cvr_lead: 0.002, cvr_car: 0.0005 })
  }

  const handleSave = async () => {
    if (!name.trim() || !stage) return
    setError(''); setSaving(true)
    try {
      const months = [
        { month_index: 1, ...m1 },
        { month_index: 2, ...m2 },
        { month_index: 3, ...m3 },
      ]
      const result = await marketingApi.createSimChannel({ channel_label: name.trim(), funnel_stage: stage, months })
      if (result.success) {
        onCreated(result.channel_key)
        resetForm()
        onClose()
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create channel'
      setError(msg)
    } finally { setSaving(false) }
  }

  const monthFields = [
    { label: 'Luna 1', state: m1, setter: setM1, disabled: stage === 'consideration' },
    { label: 'Luna 2', state: m2, setter: setM2, disabled: false },
    { label: 'Luna 3', state: m3, setter: setM3, disabled: false },
  ]

  return (
    <Dialog open={!!stage} onOpenChange={v => { if (!v) { resetForm(); onClose() } }}>
      <DialogContent className="max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-4 w-4" /> Add Channel to {stage ? STAGE_CONFIG[stage].label : ''}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label className="text-xs">Channel Name</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. TikTok Ads" className="h-8 text-sm" autoFocus />
          </div>

          <div className="space-y-3">
            <Label className="text-xs text-muted-foreground">Benchmark values per month</Label>
            {monthFields.map(({ label, state, setter, disabled }) => (
              <div key={label} className={cn('grid grid-cols-4 gap-2 items-center', disabled && 'opacity-40')}>
                <span className="text-xs font-medium">{label}</span>
                <div className="space-y-0.5">
                  <Label className="text-[10px] text-muted-foreground">CPC</Label>
                  <Input type="number" step="0.01" className="h-6 text-xs" disabled={disabled}
                    value={state.cpc} onChange={e => setter({ ...state, cpc: parseFloat(e.target.value) || 0 })} />
                </div>
                <div className="space-y-0.5">
                  <Label className="text-[10px] text-muted-foreground">CVR Lead</Label>
                  <Input type="number" step="0.0001" className="h-6 text-xs" disabled={disabled}
                    value={state.cvr_lead} onChange={e => setter({ ...state, cvr_lead: parseFloat(e.target.value) || 0 })} />
                </div>
                <div className="space-y-0.5">
                  <Label className="text-[10px] text-muted-foreground">CVR Car</Label>
                  <Input type="number" step="0.0001" className="h-6 text-xs" disabled={disabled}
                    value={state.cvr_car} onChange={e => setter({ ...state, cvr_car: parseFloat(e.target.value) || 0 })} />
                </div>
              </div>
            ))}
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => { resetForm(); onClose() }}><X className="h-3.5 w-3.5 mr-1" /> Cancel</Button>
            <Button size="sm" onClick={handleSave} disabled={!name.trim() || saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Plus className="h-3.5 w-3.5 mr-1" />}
              Add Channel
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
