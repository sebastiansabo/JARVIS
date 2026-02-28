import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, Trash2, FileSpreadsheet, Calendar, User, StickyNote, ChevronDown, FileText, Table2, FileCheck, Code2, FileType, BarChart3 } from 'lucide-react'
import { toast } from 'sonner'

import { bilantApi } from '@/api/bilant'
import { PageHeader } from '@/components/shared/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ResultsTable } from './components/ResultsTable'
import { RatioCard } from './components/RatioCard'
import { StructureChart } from './components/StructureChart'
import { AiInsightsCard } from './components/AiInsightsCard'
import type { BilantMetrics, BilantMetricConfig } from '@/types/bilant'

const statusColors: Record<string, string> = {
  completed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  processing: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
}

function fmtCurrency(n: number | undefined): string {
  if (n == null) return '-'
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(n)
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return '-'
  return new Date(s).toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// Fallback ratio thresholds for old generations without metric_configs
const FALLBACK_RATIO_THRESHOLDS: Record<string, { good: number; warning: number; suffix: string; label: string }> = {
  lichiditate_curenta: { good: 2.0, warning: 1.0, suffix: '', label: 'Lichiditate Curenta' },
  lichiditate_rapida: { good: 1.0, warning: 0.5, suffix: '', label: 'Lichiditate Rapida' },
  lichiditate_imediata: { good: 0.5, warning: 0.2, suffix: '', label: 'Lichiditate Imediata' },
  solvabilitate: { good: 50, warning: 30, suffix: '%', label: 'Solvabilitate' },
  indatorare: { good: 30, warning: 60, suffix: '%', label: 'Indatorare' },
  autonomie_financiara: { good: 50, warning: 30, suffix: '%', label: 'Autonomie Financiara' },
}

// Fallback summary labels
const FALLBACK_SUMMARY_ORDER = ['total_active', 'active_imobilizate', 'active_circulante', 'capitaluri_proprii', 'total_datorii']
const FALLBACK_SUMMARY_LABELS: Record<string, string> = {
  total_active: 'Total Active',
  active_imobilizate: 'Active Imobilizate',
  active_circulante: 'Active Circulante',
  capitaluri_proprii: 'Capitaluri Proprii',
  total_datorii: 'Total Datorii',
}

export default function BilantDetail() {
  const { generationId } = useParams<{ generationId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const isMobile = useIsMobile()
  const [tab, setTab] = useState('results')
  const [showDelete, setShowDelete] = useState(false)
  const [editNotes, setEditNotes] = useState(false)
  const [notes, setNotes] = useState('')
  const [showStats, setShowStats] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['bilant-generation', generationId],
    queryFn: () => bilantApi.getGeneration(Number(generationId)),
    enabled: !!generationId,
  })

  const gen = data?.generation
  const results = data?.results || []
  const metrics: BilantMetrics = data?.metrics || { summary: {}, ratios: {}, structure: { assets: [], liabilities: [] } }
  const metricConfigs: BilantMetricConfig[] = data?.metric_configs || []

  // Derive display data from configs or fallback
  const summaryConfigs = metricConfigs.filter(c => c.metric_group === 'summary' || c.metric_group === 'derived')
  const ratioConfigs = metricConfigs.filter(c => c.metric_group === 'ratio')
  const hasDynamicConfigs = metricConfigs.length > 0

  const deleteMut = useMutation({
    mutationFn: () => bilantApi.deleteGeneration(Number(generationId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bilant-generations'] })
      toast.success('Generation deleted')
      navigate('/app/accounting/bilant')
    },
  })

  const notesMut = useMutation({
    mutationFn: () => bilantApi.updateNotes(Number(generationId), notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bilant-generation', generationId] })
      toast.success('Notes saved')
      setEditNotes(false)
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-16" />)}
        </div>
        <Skeleton className="h-96" />
      </div>
    )
  }

  if (error || !gen) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/app/accounting/bilant')}>
          <ArrowLeft className="mr-1.5 h-4 w-4" /> Back
        </Button>
        <p className="text-sm text-destructive">Generation not found</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${gen.company_name || 'Bilant'} — ${gen.period_label || `#${gen.id}`}`}
        breadcrumbs={[
          { label: 'Accounting', shortLabel: 'Acc.', href: '/app/accounting' },
          { label: 'Bilant', href: '/app/accounting/bilant' },
          { label: gen.period_label || `Generation #${gen.id}` },
        ]}
        actions={
          <div className="flex items-center gap-1.5">
            <Badge variant="secondary" className={statusColors[gen.status] || ''}>{gen.status}</Badge>
            {isMobile && (
              <Button variant="ghost" size="icon" onClick={() => setShowStats(s => !s)}>
                <BarChart3 className="h-4 w-4" />
              </Button>
            )}
            {gen.status === 'completed' && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="icon" variant="outline" className="md:size-auto md:px-3">
                    <Download className="h-4 w-4 md:mr-1.5" />
                    <span className="hidden md:inline">Download</span>
                    <ChevronDown className="hidden md:block ml-1 h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => bilantApi.downloadGeneration(gen.id)}>
                    <FileSpreadsheet className="mr-2 h-4 w-4" />
                    Excel (Standard)
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => bilantApi.downloadGenerationPdf(gen.id)}>
                    <FileText className="mr-2 h-4 w-4" />
                    PDF (ANAF Format)
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => bilantApi.downloadGenerationFilledPdf(gen.id)}>
                    <FileCheck className="mr-2 h-4 w-4" />
                    PDF (ANAF Filled)
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => bilantApi.downloadGenerationAnaf(gen.id)}>
                    <Table2 className="mr-2 h-4 w-4" />
                    Excel (ANAF Format)
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => bilantApi.downloadGenerationXml(gen.id)}>
                    <Code2 className="mr-2 h-4 w-4" />
                    XML (ANAF Import)
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => bilantApi.downloadGenerationTxt(gen.id)}>
                    <FileType className="mr-2 h-4 w-4" />
                    TXT (balanta.txt)
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            <Button size="icon" variant="outline" className="md:size-auto md:px-3 text-destructive" onClick={() => setShowDelete(true)}>
              <Trash2 className="h-4 w-4 md:mr-1.5" />
              <span className="hidden md:inline">Delete</span>
            </Button>
          </div>
        }
      />

      {/* Summary Stats — single row */}
      {gen.status === 'completed' && (() => {
        const items = hasDynamicConfigs && summaryConfigs.length > 0
          ? summaryConfigs.sort((a, b) => a.sort_order - b.sort_order).map(cfg => ({
              key: cfg.metric_key, label: cfg.metric_label, value: metrics.summary[cfg.metric_key],
            }))
          : FALLBACK_SUMMARY_ORDER.map(key => ({
              key, label: FALLBACK_SUMMARY_LABELS[key] || key, value: metrics.summary[key],
            }))
        return (
          <div className={`grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-6 ${showStats ? '' : 'hidden md:grid'}`}>
            {items.map(item => (
              <div key={item.key} className="rounded-md border px-3 py-1.5">
                <p className="text-[11px] text-muted-foreground truncate">{item.label}</p>
                <p className="text-sm font-semibold tabular-nums">{fmtCurrency(item.value)}</p>
              </div>
            ))}
          </div>
        )
      })()}

      {/* Error message */}
      {gen.status === 'error' && gen.error_message && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4">
          <p className="text-sm text-destructive">{gen.error_message}</p>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab}>
        {isMobile ? (
          <MobileBottomTabs>
            <TabsList className="w-full">
              <TabsTrigger value="results">Results ({results.length})</TabsTrigger>
              <TabsTrigger value="metrics">Metrics</TabsTrigger>
              <TabsTrigger value="info">Info</TabsTrigger>
            </TabsList>
          </MobileBottomTabs>
        ) : (
          <TabsList className="w-auto">
            <TabsTrigger value="results">Results ({results.length})</TabsTrigger>
            <TabsTrigger value="metrics">Metrics</TabsTrigger>
            <TabsTrigger value="info">Info</TabsTrigger>
          </TabsList>
        )}

        {/* Results Tab */}
        <TabsContent value="results"><ResultsTable results={results} /></TabsContent>

        {/* Metrics Tab */}
        <TabsContent value="metrics">
          <div className="space-y-6">
            {/* Financial Ratios */}
            <div>
              <h3 className="mb-3 text-sm font-semibold">Financial Ratios</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {hasDynamicConfigs && ratioConfigs.length > 0
                  ? ratioConfigs
                      .sort((a, b) => a.sort_order - b.sort_order)
                      .map(cfg => {
                        const ratioVal = metrics.ratios[cfg.metric_key]
                        const value = ratioVal && typeof ratioVal === 'object' && 'value' in ratioVal
                          ? ratioVal.value
                          : typeof ratioVal === 'number' ? ratioVal : null
                        const suffix = cfg.display_format === 'percent' ? '%' : ''
                        const thresholds = cfg.threshold_good != null && cfg.threshold_warning != null
                          ? { good: cfg.threshold_good, warning: cfg.threshold_warning }
                          : undefined
                        return (
                          <RatioCard
                            key={cfg.metric_key}
                            label={cfg.metric_label}
                            value={value}
                            suffix={suffix}
                            thresholds={thresholds}
                            description={cfg.interpretation || undefined}
                          />
                        )
                      })
                  : Object.entries(FALLBACK_RATIO_THRESHOLDS).map(([key, meta]) => {
                      const ratioVal = metrics.ratios[key]
                      const value = typeof ratioVal === 'number'
                        ? ratioVal
                        : ratioVal && typeof ratioVal === 'object' && 'value' in ratioVal
                          ? ratioVal.value
                          : null
                      const thresholds = key === 'indatorare'
                        ? { good: meta.warning, warning: meta.good }
                        : { good: meta.good, warning: meta.warning }
                      return (
                        <RatioCard
                          key={key}
                          label={meta.label}
                          value={value}
                          suffix={meta.suffix}
                          thresholds={thresholds}
                          description={undefined}
                        />
                      )
                    })
                }
              </div>
            </div>

            {/* Structure Charts */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <StructureChart
                title="Asset Structure"
                items={metrics.structure.assets}
                colorScheme="blue"
              />
              <StructureChart
                title="Liability Structure"
                items={metrics.structure.liabilities}
                colorScheme="amber"
              />
            </div>

            {/* AI Financial Analyst */}
            <AiInsightsCard generationId={gen.id} initialAnalysis={data?.ai_analysis} />
          </div>
        </TabsContent>

        {/* Info Tab */}
        <TabsContent value="info">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <InfoItem icon={<FileSpreadsheet className="h-4 w-4" />} label="Template" value={gen.template_name || '-'} />
              <InfoItem icon={<Calendar className="h-4 w-4" />} label="Created" value={fmtDate(gen.created_at)} />
              <InfoItem icon={<User className="h-4 w-4" />} label="Created by" value={gen.generated_by_name || '-'} />
              <InfoItem icon={<FileSpreadsheet className="h-4 w-4" />} label="Original file" value={gen.original_filename || '-'} />
              <InfoItem icon={<Calendar className="h-4 w-4" />} label="Period date" value={gen.period_date ? fmtDate(gen.period_date) : '-'} />
              <InfoItem label="Rows" value={String(results.length)} />
            </div>

            {/* Notes */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <StickyNote className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-medium">Notes</h3>
                {!editNotes && (
                  <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => { setNotes(gen.notes || ''); setEditNotes(true) }}>
                    Edit
                  </Button>
                )}
              </div>
              {editNotes ? (
                <div className="space-y-2">
                  <Textarea value={notes} onChange={e => setNotes(e.target.value)} rows={4} placeholder="Add notes..." />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => notesMut.mutate()} disabled={notesMut.isPending}>Save</Button>
                    <Button size="sm" variant="outline" onClick={() => setEditNotes(false)}>Cancel</Button>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{gen.notes || 'No notes'}</p>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* Delete Confirm */}
      <ConfirmDialog
        open={showDelete}
        onOpenChange={setShowDelete}
        title="Delete generation?"
        description={`Delete "${gen.company_name} - ${gen.period_label || gen.id}"? This cannot be undone.`}
        onConfirm={() => deleteMut.mutate()}
        confirmLabel="Delete"
        variant="destructive"
      />
    </div>
  )
}

function InfoItem({ icon, label, value }: { icon?: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      {icon && <div className="mt-0.5 text-muted-foreground">{icon}</div>}
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-medium">{value}</p>
      </div>
    </div>
  )
}
