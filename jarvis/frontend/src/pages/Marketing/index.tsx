import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { useTabParam } from '@/hooks/useTabParam'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { cn } from '@/lib/utils'
import {
  Plus, Search, LayoutGrid, LayoutDashboard, List, Columns3,
  DollarSign, Target, AlertTriangle, FolderOpen, FileText,
  BarChart3, PieChart, Download, SlidersHorizontal,
  Archive, Trash2, RotateCcw, AlertCircle, Heart, GitCompareArrows, X, Check, CalendarDays, Info,
  Sparkles, ChevronDown, ChevronUp, Loader2,
} from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { marketingApi } from '@/api/marketing'
import { hrApi } from '@/api/hr'
import { settingsApi } from '@/api/settings'
import { organizationApi } from '@/api/organization'
import { QueryError } from '@/components/QueryError'
import { useMarketingStore } from '@/stores/marketingStore'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
import type { MktProject, MktKpiScoreboardItem } from '@/types/marketing'
import ProjectForm from './ProjectForm'


// ---- AI Campaign Generator ----

const CAMPAIGN_TEMPLATES = [
  {
    label: 'Product Launch',
    prompt: 'Launch campaign for a new vehicle model. Focus on brand awareness in the first month, transitioning to lead generation with digital ads, OOH, and showroom events.',
    channels: ['meta_ads', 'google_ads', 'ooh', 'events'],
  },
  {
    label: 'Always-On Digital',
    prompt: 'Ongoing digital lead generation campaign across search and social. Optimize for cost per lead with retargeting and lookalike audiences.',
    channels: ['meta_ads', 'google_ads', 'email'],
  },
  {
    label: 'Event Campaign',
    prompt: 'Promotional campaign around a dealership event or auto show. Drive foot traffic and test drive appointments via targeted local advertising.',
    channels: ['meta_ads', 'events', 'sms', 'ooh'],
  },
  {
    label: 'Branding Campaign',
    prompt: 'Brand awareness campaign to build market presence. Multi-channel approach with emphasis on reach and frequency metrics.',
    channels: ['meta_ads', 'google_ads', 'radio', 'ooh', 'influencer'],
  },
]

function AICampaignGenerator({ companies, onCreated }: {
  companies: { id: number; company: string }[]
  onCreated: (projectId: number) => void
}) {
  const [open, setOpen] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [product, setProduct] = useState('')
  const [scope, setScope] = useState('')
  const [budget, setBudget] = useState('')
  const [currency, setCurrency] = useState('EUR')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [companyId, setCompanyId] = useState<number | null>(companies[0]?.id ?? null)
  const [error, setError] = useState('')

  const generateMut = useMutation({
    mutationFn: (data: Parameters<typeof marketingApi.generateCampaign>[0]) =>
      marketingApi.generateCampaign(data),
    onSuccess: (res) => {
      onCreated(res.id)
      setOpen(false)
      resetForm()
    },
    onError: (err: Error & { response?: { data?: { error?: string } } }) => {
      setError(err.response?.data?.error || err.message || 'Generation failed')
    },
  })

  const resetForm = () => {
    setPrompt('')
    setProduct('')
    setScope('')
    setBudget('')
    setStartDate('')
    setEndDate('')
    setError('')
  }

  const applyTemplate = (t: typeof CAMPAIGN_TEMPLATES[0]) => {
    setPrompt(t.prompt)
  }

  const handleGenerate = () => {
    setError('')
    if (!prompt.trim()) return setError('Describe what you want the campaign to achieve')
    if (!budget || Number(budget) <= 0) return setError('Enter a valid budget')
    if (!startDate || !endDate) return setError('Set start and end dates')
    if (!companyId) return setError('Select a company')
    generateMut.mutate({
      prompt: prompt.trim(),
      total_budget: Number(budget),
      currency,
      start_date: startDate,
      end_date: endDate,
      company_id: companyId,
      product: product.trim() || undefined,
      scope: scope.trim() || undefined,
    })
  }

  return (
    <div className="rounded-lg border bg-gradient-to-r from-violet-50/50 to-blue-50/50 dark:from-violet-950/20 dark:to-blue-950/20">
      <button
        className="flex w-full items-center justify-between px-4 py-3 text-left"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-violet-500" />
          <span className="text-sm font-medium">AI Campaign Generator</span>
          <span className="text-xs text-muted-foreground">— create a full campaign from a brief</span>
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
      </button>

      {open && (
        <div className="border-t px-4 pb-4 pt-3 space-y-4">
          {/* Templates */}
          <div className="flex flex-wrap gap-1.5">
            {CAMPAIGN_TEMPLATES.map((t) => (
              <button
                key={t.label}
                onClick={() => applyTemplate(t)}
                className="rounded-full border px-3 py-1 text-xs hover:bg-muted transition-colors"
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Main prompt */}
          <div className="space-y-1.5">
            <Label className="text-xs">Campaign Brief</Label>
            <Textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe your campaign goals, target audience, and key messages..."
              className="min-h-[80px] text-sm"
            />
          </div>

          {/* Two-column parameters */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Product / Vehicle</Label>
              <Input value={product} onChange={(e) => setProduct(e.target.value)} placeholder="e.g. Audi Q5 Sportback" className="text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Scope / Goals</Label>
              <Input value={scope} onChange={(e) => setScope(e.target.value)} placeholder="e.g. Brand awareness + lead generation" className="text-sm" />
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Budget</Label>
              <Input type="number" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="50000" className="text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Currency</Label>
              <Select value={currency} onValueChange={setCurrency}>
                <SelectTrigger className="text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="RON">RON</SelectItem>
                  <SelectItem value="EUR">EUR</SelectItem>
                  <SelectItem value="USD">USD</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Start Date</Label>
              <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">End Date</Label>
              <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Company</Label>
              <Select value={companyId ? String(companyId) : ''} onValueChange={(v) => setCompanyId(Number(v))}>
                <SelectTrigger className="text-sm"><SelectValue placeholder="Select..." /></SelectTrigger>
                <SelectContent>
                  {companies.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 dark:bg-red-950/30 dark:border-red-800 p-2.5 text-xs text-red-700 dark:text-red-400">
              {error}
            </div>
          )}

          {/* Action */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              Creates a draft project with budget lines, KPIs, and OKRs
            </span>
            <Button
              onClick={handleGenerate}
              disabled={generateMut.isPending}
              className="gap-2"
            >
              {generateMut.isPending ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Generating...</>
              ) : (
                <><Sparkles className="h-4 w-4" /> Generate Campaign</>
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}


const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  pending_approval: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  approved: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200',
  active: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200',
  paused: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-200',
  completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200',
  cancelled: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200',
  archived: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
}

function formatCurrency(val: number | string | null | undefined, currency = 'RON') {
  const n = typeof val === 'string' ? parseFloat(val) : (val ?? 0)
  return `${n.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} ${currency}`
}

function burnRate(spent: number, budget: number) {
  if (!budget) return 0
  return Math.round((spent / budget) * 100)
}


type MainTab = 'projects' | 'archived' | 'trash'

export default function Marketing() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('marketing_summary')
  const isMobile = useIsMobile()
  const { filters, updateFilter, clearFilters, viewMode, setViewMode } = useMarketingStore()
  const [filtersOpen, setFiltersOpen] = useState(false)
  const effectiveViewMode = isMobile ? 'cards' : viewMode
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showStats, setShowStats] = useState(false)
  const [mainTabRaw, setMainTab] = useTabParam<MainTab>('projects')
  // Migrate old tab=dashboard / tab=calendar URLs to projects view
  const mainTab: MainTab = ((mainTabRaw as string) === 'dashboard' || (mainTabRaw as string) === 'calendar') ? 'projects' : mainTabRaw
  const [compareMode, setCompareMode] = useState(false)
  const [compareIds, setCompareIds] = useState<Set<number>>(new Set())

  const toggleCompare = (id: number) => {
    setCompareIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else if (next.size < 4) next.add(id)
      return next
    })
  }

  // Data queries
  const { data: projectsData, isLoading: projectsLoading, isError: projectsError, refetch: refetchProjects } = useQuery({
    queryKey: ['mkt-projects', filters],
    queryFn: () => marketingApi.listProjects(filters),
  })

  const { data: companiesData } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
  })

  const { data: statusOptions } = useQuery({
    queryKey: ['dropdown-options', 'mkt_project_status'],
    queryFn: () => settingsApi.getDropdownOptions('mkt_project_status'),
  })

  const { data: typeOptions } = useQuery({
    queryKey: ['dropdown-options', 'mkt_project_type'],
    queryFn: () => settingsApi.getDropdownOptions('mkt_project_type'),
  })

  const projects = projectsData?.projects ?? []
  const total = projectsData?.total ?? 0
  const companies = companiesData ?? []

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Marketing"
        breadcrumbs={[
          { label: 'Marketing', shortLabel: 'Mkt.' },
          { label: mainTab === 'projects' ? `Campaigns (${total})` : mainTab === 'archived' ? 'Archived' : 'Trash' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className={showStats ? 'bg-muted' : ''} onClick={() => setShowStats(s => !s)} title="Toggle stats">
              <BarChart3 className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={toggleDashboardWidget} title={isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}>
              <LayoutDashboard className="h-4 w-4" />
            </Button>
            <Button size="icon" onClick={() => setShowCreateDialog(true)} title="New Campaign">
              <Plus className="h-4 w-4" />
            </Button>
            {!isMobile && (
              <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)}>
                <TabsList className="w-auto">
                  <TabsTrigger value="projects" title="Campaigns"><FolderOpen className="h-3.5 w-3.5" /></TabsTrigger>
                  <TabsTrigger value="archived" title="Archived"><Archive className="h-3.5 w-3.5" /></TabsTrigger>
                  <TabsTrigger value="trash" title="Trash"><Trash2 className="h-3.5 w-3.5" /></TabsTrigger>
                </TabsList>
              </Tabs>
            )}
          </div>
        }
      />

      {/* Mobile tabs */}
      {isMobile && (
        <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)}>
          <MobileBottomTabs>
            <TabsList className="w-full">
              <TabsTrigger value="projects" title="Campaigns"><FolderOpen className="h-3.5 w-3.5" /></TabsTrigger>
              <TabsTrigger value="archived" title="Archived"><Archive className="h-3.5 w-3.5" /></TabsTrigger>
              <TabsTrigger value="trash" title="Trash"><Trash2 className="h-3.5 w-3.5" /></TabsTrigger>
            </TabsList>
          </MobileBottomTabs>
        </Tabs>
      )}

      {mainTab === 'projects' && (
        <>
          {/* Stat Cards — computed from filtered projects */}
          <div className={`grid grid-cols-2 gap-3 lg:grid-cols-4 ${showStats ? '' : 'hidden'}`}>
            <StatCard
              title="Campaigns"
              value={projects.length}
              icon={<FolderOpen className="h-4 w-4" />}
              isLoading={projectsLoading}
            />
            <StatCard
              title="Total Budget"
              value={formatCurrency(projects.reduce((s, p) => s + Number(p.total_budget ?? 0), 0))}
              icon={<DollarSign className="h-4 w-4" />}
              isLoading={projectsLoading}
            />
            <StatCard
              title="Total Spent"
              value={formatCurrency(projects.reduce((s, p) => s + Number(p.total_spent ?? 0), 0))}
              icon={<Target className="h-4 w-4" />}
              isLoading={projectsLoading}
            />
            <StatCard
              title="Active"
              value={projects.filter(p => p.status === 'active').length}
              icon={<AlertTriangle className="h-4 w-4" />}
              isLoading={projectsLoading}
            />
          </div>

          {/* AI Campaign Generator */}
          <AICampaignGenerator
            companies={companies}
            onCreated={(projectId) => {
              queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
              queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
              navigate(`/app/marketing/projects/${projectId}`)
            }}
          />

          {/* Filter Bar */}
          {(() => {
            const activeFilterCount = [filters.status, filters.project_type, filters.company_id].filter(Boolean).length

            const filterControls = (
              <>
                <Select
                  value={filters.status ?? 'all'}
                  onValueChange={(v) => updateFilter('status', v === 'all' ? undefined : v)}
                >
                  <SelectTrigger className={isMobile ? 'w-full' : 'w-[160px]'}>
                    <SelectValue placeholder="All statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    {(statusOptions ?? []).map((opt: { value: string; label: string }) => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select
                  value={filters.project_type ?? 'all'}
                  onValueChange={(v) => updateFilter('project_type', v === 'all' ? undefined : v)}
                >
                  <SelectTrigger className={isMobile ? 'w-full' : 'w-[160px]'}>
                    <SelectValue placeholder="All types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All types</SelectItem>
                    {(typeOptions ?? []).map((opt: { value: string; label: string }) => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select
                  value={filters.company_id ? String(filters.company_id) : 'all'}
                  onValueChange={(v) => updateFilter('company_id', v === 'all' ? undefined : Number(v))}
                >
                  <SelectTrigger className={isMobile ? 'w-full' : 'w-[180px]'}>
                    <SelectValue placeholder="All companies" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All companies</SelectItem>
                    {companies.map((c: { id: number; company: string }) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </>
            )

            if (isMobile) {
              return (
                <>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                      <Input className="pl-8" placeholder="Search..." value={filters.search ?? ''} onChange={(e) => updateFilter('search', e.target.value || undefined)} />
                    </div>
                    <Button variant="outline" size="icon" className="shrink-0" onClick={() => setFiltersOpen(true)}>
                      <SlidersHorizontal className="h-4 w-4" />
                      {activeFilterCount > 0 && (
                        <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
                          {activeFilterCount}
                        </span>
                      )}
                    </Button>
                  </div>
                  <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
                    <SheetContent side="bottom" className="max-h-[80vh] overflow-y-auto px-4">
                      <SheetHeader><SheetTitle>Filters</SheetTitle></SheetHeader>
                      <div className="grid grid-cols-2 gap-2 py-4">
                        {filterControls}
                        <div className="col-span-2 flex gap-2 pt-2">
                          {activeFilterCount > 0 && (
                            <Button variant="outline" onClick={() => { clearFilters(); setFiltersOpen(false) }} className="flex-1">
                              Clear All
                            </Button>
                          )}
                          <Button onClick={() => setFiltersOpen(false)} className="flex-1">
                            Apply
                          </Button>
                        </div>
                      </div>
                    </SheetContent>
                  </Sheet>
                </>
              )
            }

            return (
              <div className="flex flex-wrap gap-3 items-center">
                <div className="relative flex-1 min-w-0 max-w-sm">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input placeholder="Search projects..." className="pl-9" value={filters.search ?? ''} onChange={(e) => updateFilter('search', e.target.value || undefined)} />
                </div>
                {filterControls}
                {Object.values(filters).some((v) => v != null && v !== '' && v !== 50 && v !== 0) && (
                  <Button variant="ghost" size="sm" onClick={clearFilters}>Clear</Button>
                )}
                <div className="ml-auto flex gap-1">
                  <Button
                    variant={compareMode ? 'default' : 'ghost'}
                    size="icon"
                    onClick={() => { setCompareMode((v) => !v); setCompareIds(new Set()) }}
                    title="Compare campaigns"
                  >
                    <GitCompareArrows className="h-4 w-4" />
                  </Button>
                  <Button variant={viewMode === 'table' ? 'secondary' : 'ghost'} size="icon" onClick={() => setViewMode('table')} title="Table view">
                    <List className="h-4 w-4" />
                  </Button>
                  <Button variant={viewMode === 'cards' ? 'secondary' : 'ghost'} size="icon" onClick={() => setViewMode('cards')} title="Card view">
                    <LayoutGrid className="h-4 w-4" />
                  </Button>
                  <Button variant={viewMode === 'kanban' ? 'secondary' : 'ghost'} size="icon" onClick={() => setViewMode('kanban')} title="Kanban view">
                    <Columns3 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )
          })()}

          {/* Project List */}
          {projectsError ? (
            <QueryError message="Failed to load projects" onRetry={() => refetchProjects()} />
          ) : projectsLoading ? (
            <TableSkeleton rows={6} columns={7} />
          ) : effectiveViewMode === 'kanban' ? (
            <KanbanBoard
              projects={projects}
              onSelect={(p) => navigate(`/app/marketing/projects/${p.id}`)}
              onStatusChange={async (p, newStatus) => {
                const transitions: Record<string, () => Promise<unknown>> = {
                  active: () => marketingApi.activateProject(p.id),
                  paused: () => marketingApi.pauseProject(p.id),
                  completed: () => marketingApi.completeProject(p.id),
                  archived: () => marketingApi.archiveProject(p.id),
                }
                const fn = transitions[newStatus]
                if (fn) {
                  await fn()
                  queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
                  queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
                }
              }}
            />
          ) : effectiveViewMode === 'table' ? (
            <ProjectTable
              projects={projects}
              onSelect={(p) => navigate(`/app/marketing/projects/${p.id}`)}
              compareMode={compareMode}
              compareIds={compareIds}
              onToggleCompare={toggleCompare}
              onArchive={async (p) => {
                await marketingApi.archiveProject(p.id)
                queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
                queryClient.invalidateQueries({ queryKey: ['mkt-archived'] })
                queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
              }}
              onDelete={async (p) => {
                await marketingApi.deleteProject(p.id)
                queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
                queryClient.invalidateQueries({ queryKey: ['mkt-trash'] })
                queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
              }}
            />
          ) : (
            <ProjectCards
              projects={projects}
              onSelect={(p) => navigate(`/app/marketing/projects/${p.id}`)}
              compareMode={compareMode}
              compareIds={compareIds}
              onToggleCompare={toggleCompare}
              onArchive={async (p) => {
                await marketingApi.archiveProject(p.id)
                queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
                queryClient.invalidateQueries({ queryKey: ['mkt-archived'] })
                queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
              }}
              onDelete={async (p) => {
                await marketingApi.deleteProject(p.id)
                queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
                queryClient.invalidateQueries({ queryKey: ['mkt-trash'] })
                queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
              }}
            />
          )}

          {/* Pagination */}
          {total > (filters.limit ?? 50) && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                Showing {(filters.offset ?? 0) + 1}–{Math.min((filters.offset ?? 0) + (filters.limit ?? 50), total)} of {total}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!filters.offset}
                  onClick={() => updateFilter('offset', Math.max(0, (filters.offset ?? 0) - (filters.limit ?? 50)))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={(filters.offset ?? 0) + (filters.limit ?? 50) >= total}
                  onClick={() => updateFilter('offset', (filters.offset ?? 0) + (filters.limit ?? 50))}
                >
                  Next
                </Button>
              </div>
            </div>
          )}

          {/* Compare Panel */}
          {compareMode && compareIds.size >= 2 && (
            <ComparePanel
              projects={projects.filter((p) => compareIds.has(p.id))}
              onClose={() => { setCompareMode(false); setCompareIds(new Set()) }}
            />
          )}
          {compareMode && compareIds.size < 2 && (
            <div className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
              Select {2 - compareIds.size} more campaign{compareIds.size === 0 ? 's' : ''} to compare (up to 4)
            </div>
          )}
        </>
      )}

      {/* Dashboard and Calendar are now view modes within Campaigns tab */}

      {mainTab === 'archived' && (
        <ArchivedView
          onRestore={() => {
            queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
            queryClient.invalidateQueries({ queryKey: ['mkt-archived'] })
            queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
          }}
          onDelete={() => {
            queryClient.invalidateQueries({ queryKey: ['mkt-archived'] })
            queryClient.invalidateQueries({ queryKey: ['mkt-trash'] })
          }}
        />
      )}

      {mainTab === 'trash' && (
        <TrashView
          onRestore={() => {
            queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
            queryClient.invalidateQueries({ queryKey: ['mkt-trash'] })
            queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
          }}
          onPermanentDelete={() => {
            queryClient.invalidateQueries({ queryKey: ['mkt-trash'] })
          }}
        />
      )}

      {/* Create Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-[1024px] max-h-[90vh] overflow-y-auto" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>New Project</DialogTitle>
          </DialogHeader>
          <ProjectForm
            onSuccess={() => {
              setShowCreateDialog(false)
              queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
              queryClient.invalidateQueries({ queryKey: ['mkt-dashboard-summary'] })
            }}
            onCancel={() => setShowCreateDialog(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  )
}


// ---- Health Score Utility ----

interface HealthResult {
  score: number
  label: string
  color: string
  icon: React.ElementType
  budgetHealth: number
  statusHealth: number
  burn: number
  expectedBurn: number
  burnDelta: number
  timelinePct: number
}

function computeHealthScore(p: MktProject): HealthResult {
  const budget = typeof p.total_budget === 'string' ? parseFloat(p.total_budget as unknown as string) : (p.total_budget ?? 0)
  const spent = typeof p.total_spent === 'string' ? parseFloat(p.total_spent as string) : (p.total_spent ?? 0)
  const burn = budget ? (spent / budget) * 100 : 0

  // Timeline progress
  let timelinePct = 0
  if (p.start_date && p.end_date) {
    const start = new Date(p.start_date).getTime()
    const end = new Date(p.end_date).getTime()
    const now = Date.now()
    if (end > start) {
      timelinePct = Math.max(0, Math.min(100, ((now - start) / (end - start)) * 100))
    }
  }

  // Budget health: penalize if burn significantly outpaces timeline
  let budgetHealth = 100
  const expectedBurn = timelinePct || 50
  let burnDelta = 0
  if (budget > 0) {
    burnDelta = burn - expectedBurn
    if (burnDelta > 30) budgetHealth = 20
    else if (burnDelta > 15) budgetHealth = 50
    else if (burnDelta > 5) budgetHealth = 75
    else budgetHealth = 100
    if (burn > 95) budgetHealth = Math.min(budgetHealth, 30)
  }

  // Status health
  let statusHealth = 100
  if (p.status === 'paused') statusHealth = 60
  else if (p.status === 'draft') statusHealth = 80
  else if (p.status === 'active') statusHealth = 100
  else if (p.status === 'completed') statusHealth = 100

  const score = Math.round((budgetHealth * 0.7) + (statusHealth * 0.3))

  const base = { score, budgetHealth, statusHealth, burn, expectedBurn, burnDelta, timelinePct }
  if (score >= 80) return { ...base, label: 'Healthy', color: 'text-green-600 dark:text-green-400', icon: Heart }
  if (score >= 50) return { ...base, label: 'At Risk', color: 'text-yellow-600 dark:text-yellow-400', icon: AlertTriangle }
  return { ...base, label: 'Critical', color: 'text-red-600 dark:text-red-400', icon: AlertCircle }
}

function HealthBadge({ project }: { project: MktProject }) {
  const h = computeHealthScore(project)
  const Icon = h.icon
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={`inline-flex items-center gap-1 text-xs font-medium ${h.color}`}>
            <Icon className="h-3 w-3" />
            {h.score}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[260px] p-3">
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between font-medium">
              <span>{h.label}</span>
              <span className={h.color}>{h.score}/100</span>
            </div>
            <div className="h-px bg-border" />
            <div className="space-y-1 text-muted-foreground">
              <div className="flex justify-between">
                <span>Budget Health (70%)</span>
                <span className="font-medium text-foreground">{h.budgetHealth}</span>
              </div>
              <div className="flex justify-between">
                <span>Status Health (30%)</span>
                <span className="font-medium text-foreground">{h.statusHealth}</span>
              </div>
            </div>
            <div className="h-px bg-border" />
            <div className="space-y-0.5 text-muted-foreground">
              <div className="flex justify-between">
                <span>Budget burned</span>
                <span>{h.burn.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span>Timeline elapsed</span>
                <span>{h.timelinePct.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span>Burn vs expected</span>
                <span className={h.burnDelta > 5 ? 'text-red-500' : h.burnDelta > 0 ? 'text-yellow-500' : 'text-green-500'}>
                  {h.burnDelta > 0 ? '+' : ''}{h.burnDelta.toFixed(1)}%
                </span>
              </div>
            </div>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function HealthInfoHeader() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors">
          Health
          <Info className="h-3 w-3 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent side="bottom" align="center" className="w-[340px] p-4 text-xs">
        <div className="space-y-3">
          <div className="font-semibold text-sm">How Health Score Works</div>
          <p className="text-muted-foreground leading-relaxed">
            Each campaign gets a health score from 0 to 100 based on
            budget pacing and project status.
          </p>

          <div className="space-y-2">
            <div className="font-medium">Formula</div>
            <div className="bg-muted rounded-md px-3 py-2 font-mono text-[11px]">
              Health = Budget Health x 70% + Status Health x 30%
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="font-medium">Budget Health (0–100)</div>
            <p className="text-muted-foreground leading-relaxed">
              Compares how much budget you've spent vs. how far along
              the campaign timeline is. Spending ahead of schedule
              lowers the score.
            </p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-muted-foreground mt-1">
              <span>On pace or under ({"<"}5% over)</span><span className="text-right font-medium text-foreground">100</span>
              <span>Slightly over (5–15%)</span><span className="text-right font-medium text-foreground">75</span>
              <span>Significantly over (15–30%)</span><span className="text-right font-medium text-foreground">50</span>
              <span>Way over budget ({">"}30%)</span><span className="text-right font-medium text-foreground">20</span>
              <span>Budget {">"}95% depleted</span><span className="text-right font-medium text-foreground">max 30</span>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="font-medium">Status Health (0–100)</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-muted-foreground">
              <span>Active / Completed</span><span className="text-right font-medium text-foreground">100</span>
              <span>Draft</span><span className="text-right font-medium text-foreground">80</span>
              <span>Paused</span><span className="text-right font-medium text-foreground">60</span>
            </div>
          </div>

          <div className="h-px bg-border" />

          <div className="space-y-1.5">
            <div className="font-medium">Score Ranges</div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Heart className="h-3 w-3 text-green-600" />
                <span className="text-green-600 font-medium">80–100</span>
                <span className="text-muted-foreground">Healthy — on track</span>
              </div>
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-3 w-3 text-yellow-600" />
                <span className="text-yellow-600 font-medium">50–79</span>
                <span className="text-muted-foreground">At Risk — needs attention</span>
              </div>
              <div className="flex items-center gap-2">
                <AlertCircle className="h-3 w-3 text-red-600" />
                <span className="text-red-600 font-medium">0–49</span>
                <span className="text-muted-foreground">Critical — overspending or stalled</span>
              </div>
            </div>
          </div>

          <div className="h-px bg-border" />
          <p className="text-muted-foreground italic leading-relaxed">
            Hover over any health score to see the detailed breakdown
            for that specific campaign.
          </p>
        </div>
      </PopoverContent>
    </Popover>
  )
}


// ---- Kanban Board View ----

const kanbanStatuses = [
  { key: 'draft', label: 'Draft', color: 'border-t-gray-400' },
  { key: 'pending_approval', label: 'Pending', color: 'border-t-yellow-400' },
  { key: 'approved', label: 'Approved', color: 'border-t-green-400' },
  { key: 'active', label: 'Active', color: 'border-t-blue-400' },
  { key: 'paused', label: 'Paused', color: 'border-t-orange-400' },
  { key: 'completed', label: 'Completed', color: 'border-t-emerald-400' },
]

function KanbanBoard({ projects, onSelect, onStatusChange: _onStatusChange }: {
  projects: MktProject[]
  onSelect: (p: MktProject) => void
  onStatusChange?: (p: MktProject, newStatus: string) => void
}) {
  const grouped = new Map<string, MktProject[]>()
  for (const s of kanbanStatuses) grouped.set(s.key, [])
  for (const p of projects) {
    const arr = grouped.get(p.status)
    if (arr) arr.push(p)
  }

  // Non-empty columns only, plus always show active
  const visibleStatuses = kanbanStatuses.filter(
    (s) => s.key === 'active' || (grouped.get(s.key)?.length ?? 0) > 0
  )

  if (projects.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <FolderOpen className="mx-auto h-8 w-8 mb-2 opacity-40" />
        No campaigns yet. Create your first campaign to get started.
      </div>
    )
  }

  return (
    <div className="flex gap-4 overflow-x-auto pb-4 -mx-4 px-4 md:mx-0 md:px-0">
      {visibleStatuses.map((status) => {
        const items = grouped.get(status.key) ?? []
        return (
          <div
            key={status.key}
            className={cn(
              'flex-shrink-0 w-[280px] rounded-lg border border-t-4 bg-muted/30',
              status.color,
            )}
          >
            <div className="px-3 py-2.5 border-b flex items-center justify-between">
              <span className="text-sm font-semibold">{status.label}</span>
              <Badge variant="secondary" className="text-xs h-5 px-1.5">{items.length}</Badge>
            </div>
            <div className="p-2 space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto">
              {items.length === 0 && (
                <div className="text-center py-6 text-xs text-muted-foreground">No projects</div>
              )}
              {items.map((p) => {
                const spent = typeof p.total_spent === 'string' ? parseFloat(p.total_spent) : (p.total_spent ?? 0)
                const budget = typeof p.total_budget === 'string' ? parseFloat(p.total_budget as unknown as string) : (p.total_budget ?? 0)
                const burn = burnRate(spent, budget)
                return (
                  <div
                    key={p.id}
                    className="rounded-md border bg-card p-3 space-y-2 cursor-pointer hover:shadow-md hover:border-primary/30 transition-all"
                    onClick={() => onSelect(p)}
                  >
                    <div className="flex items-start justify-between gap-1">
                      <h4 className="text-sm font-medium truncate leading-tight">{p.name}</h4>
                      <HealthBadge project={p} />
                    </div>
                    <div className="text-xs text-muted-foreground truncate">
                      {p.company_name}{p.brand_name ? ` / ${p.brand_name}` : ''}
                    </div>
                    {/* Budget mini-bar */}
                    {budget > 0 && (
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10px] text-muted-foreground tabular-nums">
                          <span>{formatCurrency(spent, p.currency)}</span>
                          <span>{burn}%</span>
                        </div>
                        <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full rounded-full ${burn > 90 ? 'bg-red-500' : burn > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                            style={{ width: `${Math.min(burn, 100)}%` }}
                          />
                        </div>
                      </div>
                    )}
                    {/* Channel chips */}
                    {p.channel_mix?.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {p.channel_mix.slice(0, 3).map((ch) => (
                          <span key={ch} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-muted text-muted-foreground">
                            {ch.replace('_', ' ')}
                          </span>
                        ))}
                        {p.channel_mix.length > 3 && (
                          <span className="text-[10px] text-muted-foreground">+{p.channel_mix.length - 3}</span>
                        )}
                      </div>
                    )}
                    {/* Footer */}
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1">
                      <span>{p.owner_name}</span>
                      {p.start_date && (
                        <span>{new Date(p.start_date).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' })}</span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}


// ---- Table View ----

function ProjectTable({ projects, onSelect, onArchive, onDelete, compareMode, compareIds, onToggleCompare }: {
  projects: MktProject[]
  onSelect: (p: MktProject) => void
  onArchive?: (p: MktProject) => void
  onDelete?: (p: MktProject) => void
  compareMode?: boolean
  compareIds?: Set<number>
  onToggleCompare?: (id: number) => void
}) {
  if (!projects.length) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <FolderOpen className="mx-auto h-8 w-8 mb-2 opacity-40" />
        No campaigns yet. Create your first campaign to get started.
      </div>
    )
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            {compareMode && <TableHead className="w-10" />}
            <TableHead>Project</TableHead>
            <TableHead>Company</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-center w-14">
                <HealthInfoHeader />
              </TableHead>
            <TableHead className="text-right">Budget</TableHead>
            <TableHead className="text-right">Spent</TableHead>
            <TableHead>Burn</TableHead>
            <TableHead>Owner</TableHead>
            <TableHead>Dates</TableHead>
            {(onArchive || onDelete) && <TableHead className="w-[80px]" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {projects.map((p) => {
            const spent = typeof p.total_spent === 'string' ? parseFloat(p.total_spent) : (p.total_spent ?? 0)
            const budget = typeof p.total_budget === 'string' ? parseFloat(p.total_budget as unknown as string) : (p.total_budget ?? 0)
            const burn = burnRate(spent, budget)
            return (
              <TableRow
                key={p.id}
                className={cn('cursor-pointer hover:bg-muted/50', compareIds?.has(p.id) && 'bg-primary/5')}
                onClick={() => compareMode ? onToggleCompare?.(p.id) : onSelect(p)}
              >
                {compareMode && (
                  <TableCell className="w-10">
                    <div className={cn(
                      'h-4 w-4 rounded border flex items-center justify-center transition-colors',
                      compareIds?.has(p.id) ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground/30',
                    )}>
                      {compareIds?.has(p.id) && <Check className="h-3 w-3" />}
                    </div>
                  </TableCell>
                )}
                <TableCell className="font-medium max-w-[200px] truncate">{p.name}</TableCell>
                <TableCell className="text-sm">{p.company_name}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-xs capitalize">
                    {(p.project_type ?? '').replace('_', ' ')}
                  </Badge>
                </TableCell>
                <TableCell>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[p.status] ?? ''}`}>
                    {(p.status ?? '').replace('_', ' ')}
                  </span>
                </TableCell>
                <TableCell className="text-center">
                  <HealthBadge project={p} />
                </TableCell>
                <TableCell className="text-right text-sm tabular-nums">
                  {formatCurrency(budget, p.currency)}
                </TableCell>
                <TableCell className="text-right text-sm tabular-nums">
                  {formatCurrency(spent, p.currency)}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full ${burn > 90 ? 'bg-red-500' : burn > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                        style={{ width: `${Math.min(burn, 100)}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground">{burn}%</span>
                  </div>
                </TableCell>
                <TableCell className="text-sm">{p.owner_name}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {p.start_date ? new Date(p.start_date).toLocaleDateString('ro-RO') : '—'}
                </TableCell>
                {(onArchive || onDelete) && (
                  <TableCell>
                    <div className="flex items-center gap-1">
                      {onArchive && p.status !== 'archived' && (
                        <button
                          type="button"
                          className="p-1 rounded hover:bg-accent cursor-pointer transition-colors"
                          title="Archive"
                          onClick={(e) => { e.stopPropagation(); onArchive(p) }}
                        >
                          <Archive className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      )}
                      {onDelete && (
                        <button
                          type="button"
                          className="p-1 rounded hover:bg-destructive/10 cursor-pointer transition-colors"
                          title="Delete"
                          onClick={(e) => { e.stopPropagation(); onDelete(p) }}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </button>
                      )}
                    </div>
                  </TableCell>
                )}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}


// ---- Card View ----

function ProjectCards({ projects, onSelect, onArchive, onDelete, compareMode, compareIds, onToggleCompare }: {
  projects: MktProject[]
  onSelect: (p: MktProject) => void
  onArchive?: (p: MktProject) => void
  onDelete?: (p: MktProject) => void
  compareMode?: boolean
  compareIds?: Set<number>
  onToggleCompare?: (id: number) => void
}) {
  if (!projects.length) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <FolderOpen className="mx-auto h-8 w-8 mb-2 opacity-40" />
        No campaigns yet. Create your first campaign to get started.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {projects.map((p) => {
        const spent = typeof p.total_spent === 'string' ? parseFloat(p.total_spent) : (p.total_spent ?? 0)
        const budget = typeof p.total_budget === 'string' ? parseFloat(p.total_budget as unknown as string) : (p.total_budget ?? 0)
        const burn = burnRate(spent, budget)
        return (
          <div
            key={p.id}
            className={cn(
              'rounded-lg border bg-card p-4 space-y-3 cursor-pointer hover:border-primary/50 transition-colors relative',
              compareIds?.has(p.id) && 'border-primary ring-1 ring-primary/30',
            )}
            onClick={() => compareMode ? onToggleCompare?.(p.id) : onSelect(p)}
          >
            {compareMode && (
              <div className={cn(
                'absolute top-2 right-2 h-5 w-5 rounded-full border-2 flex items-center justify-center transition-colors z-10',
                compareIds?.has(p.id) ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground/30 bg-background',
              )}>
                {compareIds?.has(p.id) && <Check className="h-3 w-3" />}
              </div>
            )}
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="font-semibold truncate">{p.name}</h3>
                <p className="text-sm text-muted-foreground">{p.company_name}{p.brand_name ? ` / ${p.brand_name}` : ''}</p>
              </div>
              <span className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[p.status] ?? ''}`}>
                {(p.status ?? '').replace('_', ' ')}
              </span>
            </div>

            {/* Channel chips */}
            {p.channel_mix?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {p.channel_mix.slice(0, 4).map((ch) => (
                  <Badge key={ch} variant="secondary" className="text-xs">
                    {ch.replace('_', ' ')}
                  </Badge>
                ))}
                {p.channel_mix.length > 4 && (
                  <Badge variant="secondary" className="text-xs">+{p.channel_mix.length - 4}</Badge>
                )}
              </div>
            )}

            {/* Budget bar */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{formatCurrency(spent)} spent</span>
                <span>{formatCurrency(budget)} budget</span>
              </div>
              <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${burn > 90 ? 'bg-red-500' : burn > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                  style={{ width: `${Math.min(burn, 100)}%` }}
                />
              </div>
            </div>

            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{p.owner_name}</span>
              <div className="flex items-center gap-1">
                {onArchive && p.status !== 'archived' && (
                  <button
                    type="button"
                    className="p-1 rounded hover:bg-accent cursor-pointer transition-colors"
                    title="Archive"
                    onClick={(e) => { e.stopPropagation(); onArchive(p) }}
                  >
                    <Archive className="h-3.5 w-3.5" />
                  </button>
                )}
                {onDelete && (
                  <button
                    type="button"
                    className="p-1 rounded hover:bg-destructive/10 cursor-pointer transition-colors text-destructive"
                    title="Delete"
                    onClick={(e) => { e.stopPropagation(); onDelete(p) }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
                <span>{p.start_date ? new Date(p.start_date).toLocaleDateString('ro-RO') : ''}</span>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}


// ---- Calendar/Timeline View ----

type CalendarRange = 'day' | 'week' | 'month' | 'quarter' | 'year'

function getRange(anchor: Date, range: CalendarRange): { start: Date; end: Date } {
  const y = anchor.getFullYear(), m = anchor.getMonth(), d = anchor.getDate()
  switch (range) {
    case 'day':
      return { start: new Date(y, m, d), end: new Date(y, m, d + 1) }
    case 'week': {
      const dow = anchor.getDay() || 7 // Mon=1
      const mon = new Date(y, m, d - dow + 1)
      return { start: mon, end: new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + 7) }
    }
    case 'month':
      return { start: new Date(y, m, 1), end: new Date(y, m + 1, 1) }
    case 'quarter': {
      const q = Math.floor(m / 3) * 3
      return { start: new Date(y, q, 1), end: new Date(y, q + 3, 1) }
    }
    case 'year':
      return { start: new Date(y, 0, 1), end: new Date(y + 1, 0, 1) }
  }
}

function shiftAnchor(anchor: Date, range: CalendarRange, dir: 1 | -1): Date {
  const y = anchor.getFullYear(), m = anchor.getMonth(), d = anchor.getDate()
  switch (range) {
    case 'day': return new Date(y, m, d + dir)
    case 'week': return new Date(y, m, d + 7 * dir)
    case 'month': return new Date(y, m + dir, 1)
    case 'quarter': return new Date(y, m + 3 * dir, 1)
    case 'year': return new Date(y + dir, 0, 1)
  }
}

function generateGridMarkers(start: Date, end: Date, range: CalendarRange): { label: string; left: number }[] {
  const totalMs = end.getTime() - start.getTime()
  const markers: { label: string; left: number }[] = []
  const fmt = (d: Date, opts: Intl.DateTimeFormatOptions) => d.toLocaleDateString('ro-RO', opts)

  if (range === 'day') {
    // Hourly markers
    for (let h = 0; h < 24; h++) {
      const t = new Date(start.getFullYear(), start.getMonth(), start.getDate(), h)
      markers.push({ label: `${h}:00`, left: ((t.getTime() - start.getTime()) / totalMs) * 100 })
    }
  } else if (range === 'week') {
    // Daily markers
    const c = new Date(start)
    while (c < end) {
      markers.push({ label: fmt(c, { weekday: 'short', day: 'numeric' }), left: ((c.getTime() - start.getTime()) / totalMs) * 100 })
      c.setDate(c.getDate() + 1)
    }
  } else if (range === 'month') {
    // Daily markers (show every few days for readability)
    const c = new Date(start)
    while (c < end) {
      markers.push({ label: String(c.getDate()), left: ((c.getTime() - start.getTime()) / totalMs) * 100 })
      c.setDate(c.getDate() + 1)
    }
  } else if (range === 'quarter') {
    // Weekly markers
    const c = new Date(start)
    while (c < end) {
      markers.push({ label: fmt(c, { day: 'numeric', month: 'short' }), left: ((c.getTime() - start.getTime()) / totalMs) * 100 })
      c.setDate(c.getDate() + 7)
    }
  } else {
    // Monthly markers
    const c = new Date(start.getFullYear(), start.getMonth(), 1)
    while (c < end) {
      markers.push({ label: fmt(c, { month: 'short' }), left: ((c.getTime() - start.getTime()) / totalMs) * 100 })
      c.setMonth(c.getMonth() + 1)
    }
  }
  return markers
}

function rangeTitle(anchor: Date, range: CalendarRange): string {
  const fmt = (d: Date, opts: Intl.DateTimeFormatOptions) => d.toLocaleDateString('ro-RO', opts)
  const { start, end } = getRange(anchor, range)
  switch (range) {
    case 'day': return fmt(anchor, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
    case 'week': {
      const wEnd = new Date(end.getTime() - 86400000)
      return `${fmt(start, { day: 'numeric', month: 'short' })} – ${fmt(wEnd, { day: 'numeric', month: 'short', year: 'numeric' })}`
    }
    case 'month': return fmt(anchor, { month: 'long', year: 'numeric' })
    case 'quarter': {
      const q = Math.floor(anchor.getMonth() / 3) + 1
      return `Q${q} ${anchor.getFullYear()}`
    }
    case 'year': return String(anchor.getFullYear())
  }
}

// ── Mobile calendar views ──

type MobileCalProps = {
  projects: MktProject[]
  events: { id: number; name: string; start_date: string; end_date: string; company?: string | null }[]
  barColors: Record<string, string>
  onSelect: (p: MktProject) => void
  onEventClick: () => void
}

function MobileDayView({ anchor, projects, events, barColors, onSelect, onEventClick }: MobileCalProps & { anchor: Date }) {
  const dayStart = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate())
  const now = new Date()
  const isToday = dayStart.toDateString() === now.toDateString()
  const currentHour = isToday ? now.getHours() + now.getMinutes() / 60 : -1

  const hours = Array.from({ length: 24 }, (_, i) => i)

  return (
    <div className="space-y-3">
      {/* All-day / spanning campaigns */}
      {projects.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Campaigns ({projects.length})</div>
          {projects.map((p) => (
            <div
              key={p.id}
              className={cn('flex items-center gap-2 rounded-md px-2.5 py-2.5 cursor-pointer', barColors[p.status] ?? 'bg-gray-400')}
              onClick={() => onSelect(p)}
            >
              <span className="text-xs font-medium text-white truncate">{p.name}</span>
              <span className="ml-auto text-[10px] text-white/80 shrink-0">
                {new Date(p.start_date!).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })} – {new Date(p.end_date!).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })}
              </span>
            </div>
          ))}
        </div>
      )}
      {events.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Events ({events.length})</div>
          {events.map((e) => (
            <div
              key={`evt-${e.id}`}
              className="flex items-center gap-2 rounded-md px-2.5 py-2.5 cursor-pointer bg-purple-500"
              onClick={onEventClick}
            >
              <CalendarDays className="h-3.5 w-3.5 text-white shrink-0" />
              <span className="text-xs font-medium text-white truncate">{e.name}</span>
              {e.company && <span className="ml-auto text-[10px] text-white/80 shrink-0">{e.company}</span>}
            </div>
          ))}
        </div>
      )}

      {/* Hour timeline */}
      <div className="rounded-lg border overflow-hidden">
        {hours.map((h) => (
          <div
            key={h}
            className={cn(
              'flex items-start border-b last:border-b-0 min-h-[36px]',
              isToday && h === Math.floor(currentHour) && 'bg-red-500/5',
            )}
          >
            <div className="w-12 shrink-0 py-1.5 text-right pr-2 text-[10px] text-muted-foreground font-medium border-r">
              {String(h).padStart(2, '0')}:00
            </div>
            <div className="flex-1 min-h-[36px] relative">
              {isToday && h === Math.floor(currentHour) && (
                <div
                  className="absolute left-0 right-0 h-px bg-red-500"
                  style={{ top: `${((currentHour - h) * 100)}%` }}
                />
              )}
            </div>
          </div>
        ))}
      </div>

      {projects.length === 0 && events.length === 0 && (
        <div className="text-center py-8 text-muted-foreground text-sm">No campaigns or events today.</div>
      )}
    </div>
  )
}

function MobileWeekView({ anchor, projects, events, barColors, onSelect, onEventClick }: MobileCalProps & { anchor: Date }) {
  const today = new Date()
  const todayStr = `${today.getFullYear()}-${today.getMonth()}-${today.getDate()}`
  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

  // Calculate week start (Monday)
  const { start: weekStart } = getRange(anchor, 'week')
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart)
    d.setDate(d.getDate() + i)
    return d
  })

  // Items for each day
  function getItemsForDay(date: Date) {
    const dayStart = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
    const dayEnd = dayStart + 86400000
    return {
      projects: projects.filter((p) => {
        const s = new Date(p.start_date!).getTime(), e = new Date(p.end_date!).getTime()
        return s < dayEnd && e > dayStart
      }),
      events: events.filter((e) => {
        const s = new Date(e.start_date).getTime(), en = new Date(e.end_date).getTime()
        return s < dayEnd && en > dayStart
      }),
    }
  }

  return (
    <div className="space-y-3">
      {/* Week day cards */}
      <div className="rounded-lg border overflow-hidden divide-y">
        {days.map((date, i) => {
          const dayKey = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
          const isToday = dayKey === todayStr
          const items = getItemsForDay(date)
          const hasItems = items.projects.length > 0 || items.events.length > 0

          return (
            <div key={i} className={cn('', isToday && 'bg-red-500/5')}>
              {/* Day header */}
              <div className={cn(
                'flex items-center gap-2 px-3 py-2',
                isToday ? 'border-l-2 border-l-red-500' : '',
              )}>
                <span className={cn(
                  'text-xs font-medium w-8',
                  isToday ? 'text-red-500' : 'text-muted-foreground',
                )}>
                  {dayNames[i]}
                </span>
                <span className={cn(
                  'flex items-center justify-center w-7 h-7 rounded-full text-sm font-semibold',
                  isToday ? 'bg-red-500 text-white' : '',
                )}>
                  {date.getDate()}
                </span>
                <span className="text-xs text-muted-foreground">
                  {date.toLocaleDateString('ro-RO', { month: 'short' })}
                </span>
              </div>

              {/* Items for the day */}
              {hasItems && (
                <div className="px-3 pb-2 space-y-1">
                  {items.projects.map((p) => (
                    <div
                      key={p.id}
                      className={cn('flex items-center gap-2 rounded px-2 py-1.5 cursor-pointer', barColors[p.status] ?? 'bg-gray-400')}
                      onClick={() => onSelect(p)}
                    >
                      <span className="text-[11px] font-medium text-white truncate">{p.name}</span>
                    </div>
                  ))}
                  {items.events.map((e) => (
                    <div
                      key={`evt-${e.id}`}
                      className="flex items-center gap-1.5 rounded px-2 py-1.5 cursor-pointer bg-purple-500"
                      onClick={onEventClick}
                    >
                      <CalendarDays className="h-3 w-3 text-white shrink-0" />
                      <span className="text-[11px] font-medium text-white truncate">{e.name}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function MobileQuarterView({ anchor, projects, events, barColors, onSelect, onEventClick }: MobileCalProps & { anchor: Date }) {
  const today = new Date()
  const todayStr = `${today.getFullYear()}-${today.getMonth()}-${today.getDate()}`
  const dayNames = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

  const qMonth = Math.floor(anchor.getMonth() / 3) * 3
  const year = anchor.getFullYear()
  const months = [qMonth, qMonth + 1, qMonth + 2]

  function buildWeeks(yr: number, mo: number) {
    const first = new Date(yr, mo, 1)
    const daysInMonth = new Date(yr, mo + 1, 0).getDate()
    let startDay = first.getDay() - 1
    if (startDay < 0) startDay = 6
    const weeks: (number | null)[][] = []
    let week: (number | null)[] = Array(startDay).fill(null)
    for (let d = 1; d <= daysInMonth; d++) {
      week.push(d)
      if (week.length === 7) { weeks.push(week); week = [] }
    }
    if (week.length > 0) {
      while (week.length < 7) week.push(null)
      weeks.push(week)
    }
    return weeks
  }

  function getItemsForDay(yr: number, mo: number, day: number) {
    const dayStart = new Date(yr, mo, day).getTime()
    const dayEnd = dayStart + 86400000
    return {
      projects: projects.filter((p) => {
        const s = new Date(p.start_date!).getTime(), e = new Date(p.end_date!).getTime()
        return s < dayEnd && e > dayStart
      }),
      events: events.filter((e) => {
        const s = new Date(e.start_date).getTime(), en = new Date(e.end_date).getTime()
        return s < dayEnd && en > dayStart
      }),
    }
  }

  return (
    <div className="space-y-4">
      {/* 3 month grids stacked */}
      {months.map((mo) => {
        const weeks = buildWeeks(year, mo)
        const monthLabel = new Date(year, mo, 1).toLocaleDateString('ro-RO', { month: 'long' })

        return (
          <div key={mo} className="rounded-lg border overflow-hidden">
            <div className="px-3 py-1.5 bg-muted/50 border-b">
              <span className="text-xs font-semibold capitalize">{monthLabel}</span>
            </div>
            <div className="grid grid-cols-7">
              {dayNames.map((d) => (
                <div key={d} className="text-center text-[10px] font-medium text-muted-foreground py-1 bg-muted/30 border-b">{d}</div>
              ))}
            </div>
            {weeks.map((week, wi) => (
              <div key={wi} className="grid grid-cols-7">
                {week.map((day, di) => {
                  if (day === null) return <div key={di} className="h-10 border-b border-r last:border-r-0" />
                  const items = getItemsForDay(year, mo, day)
                  const hasItems = items.projects.length > 0 || items.events.length > 0
                  const isToday = `${year}-${mo}-${day}` === todayStr
                  return (
                    <div
                      key={di}
                      className={cn(
                        'relative h-10 border-b border-r last:border-r-0 p-0.5 overflow-hidden',
                        isToday && 'bg-red-500/10',
                      )}
                      onClick={() => {
                        if (items.projects.length === 1) onSelect(items.projects[0])
                        else if (items.events.length > 0 && items.projects.length === 0) onEventClick()
                      }}
                    >
                      <div className={cn(
                        'text-[10px] leading-none',
                        isToday ? 'font-bold text-red-500' : 'text-muted-foreground',
                      )}>
                        {day}
                      </div>
                      {hasItems && (
                        <div className="flex flex-wrap gap-px mt-0.5">
                          {items.projects.slice(0, 2).map((p) => (
                            <div
                              key={p.id}
                              className={cn('h-1.5 rounded-full flex-1 min-w-[6px]', barColors[p.status] ?? 'bg-gray-400')}
                            />
                          ))}
                          {items.events.slice(0, 1).map((e) => (
                            <div key={`e-${e.id}`} className="h-1.5 rounded-full flex-1 min-w-[6px] bg-purple-500" />
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        )
      })}

      {/* Campaign list */}
      {projects.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Campaigns ({projects.length})</div>
          {projects.map((p) => (
            <div
              key={p.id}
              className={cn('flex items-center gap-2 rounded-md px-2.5 py-2 cursor-pointer', barColors[p.status] ?? 'bg-gray-400')}
              onClick={() => onSelect(p)}
            >
              <span className="text-xs font-medium text-white truncate">{p.name}</span>
              <span className="ml-auto text-[10px] text-white/80 shrink-0">
                {new Date(p.start_date!).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })} – {new Date(p.end_date!).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })}
              </span>
            </div>
          ))}
        </div>
      )}
      {events.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Events ({events.length})</div>
          {events.map((e) => (
            <div
              key={`evt-${e.id}`}
              className="flex items-center gap-2 rounded-md px-2.5 py-2 cursor-pointer bg-purple-500"
              onClick={onEventClick}
            >
              <CalendarDays className="h-3 w-3 text-white shrink-0" />
              <span className="text-xs font-medium text-white truncate">{e.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MobileCalendarGrid({ range, anchor, projects, events, barColors, onSelect, onEventClick }: {
  range: 'month' | 'year'
  anchor: Date
  projects: MktProject[]
  events: { id: number; name: string; start_date: string; end_date: string; company?: string | null }[]
  barColors: Record<string, string>
  onSelect: (p: MktProject) => void
  onEventClick: () => void
}) {
  const y = anchor.getFullYear(), m = anchor.getMonth()
  const today = new Date()
  const todayStr = `${today.getFullYear()}-${today.getMonth()}-${today.getDate()}`

  const dayNames = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

  // Build weeks for a given month
  function buildWeeks(year: number, month: number) {
    const first = new Date(year, month, 1)
    const daysInMonth = new Date(year, month + 1, 0).getDate()
    // Monday=0 offset
    let startDay = first.getDay() - 1
    if (startDay < 0) startDay = 6
    const weeks: (number | null)[][] = []
    let week: (number | null)[] = Array(startDay).fill(null)
    for (let d = 1; d <= daysInMonth; d++) {
      week.push(d)
      if (week.length === 7) { weeks.push(week); week = [] }
    }
    if (week.length > 0) {
      while (week.length < 7) week.push(null)
      weeks.push(week)
    }
    return weeks
  }

  // Check if a day has campaigns/events
  function getItemsForDay(year: number, month: number, day: number) {
    const dayStart = new Date(year, month, day).getTime()
    const dayEnd = new Date(year, month, day + 1).getTime()
    const matchedProjects = projects.filter((p) => {
      const s = new Date(p.start_date!).getTime(), e = new Date(p.end_date!).getTime()
      return s < dayEnd && e > dayStart
    })
    const matchedEvents = events.filter((e) => {
      const s = new Date(e.start_date).getTime(), en = new Date(e.end_date).getTime()
      return s < dayEnd && en > dayStart
    })
    return { projects: matchedProjects, events: matchedEvents }
  }

  function renderMonth(year: number, month: number, compact = false) {
    const weeks = buildWeeks(year, month)
    const isToday = (day: number | null) =>
      day !== null && `${year}-${month}-${day}` === todayStr

    return (
      <div className={compact ? '' : 'rounded-lg border overflow-hidden'}>
        {compact && (
          <div className="text-xs font-semibold text-muted-foreground px-1 pb-1">
            {new Date(year, month, 1).toLocaleDateString('ro-RO', { month: 'short' })}
          </div>
        )}
        {/* Day name headers */}
        <div className="grid grid-cols-7">
          {dayNames.map((d) => (
            <div key={d} className={cn(
              'text-center font-medium text-muted-foreground',
              compact ? 'text-[8px] py-0.5' : 'text-[10px] py-1.5 bg-muted/50 border-b',
            )}>{d}</div>
          ))}
        </div>
        {/* Week rows */}
        {weeks.map((week, wi) => (
          <div key={wi} className="grid grid-cols-7">
            {week.map((day, di) => {
              if (day === null) return <div key={di} className={compact ? 'h-5' : 'h-12 border-b border-r last:border-r-0'} />
              const items = getItemsForDay(year, month, day)
              const hasItems = items.projects.length > 0 || items.events.length > 0
              return (
                <div
                  key={di}
                  className={cn(
                    'relative overflow-hidden',
                    compact ? 'h-5 flex items-center justify-center' : 'h-12 border-b border-r last:border-r-0 p-0.5',
                    isToday(day) && 'bg-red-500/10',
                  )}
                  onClick={() => {
                    if (items.projects.length === 1) onSelect(items.projects[0])
                    else if (items.events.length > 0 && items.projects.length === 0) onEventClick()
                  }}
                >
                  <div className={cn(
                    compact ? 'text-[8px]' : 'text-[10px] leading-none',
                    isToday(day) ? 'font-bold text-red-500' : 'text-muted-foreground',
                  )}>
                    {day}
                  </div>
                  {!compact && hasItems && (
                    <div className="flex flex-wrap gap-px mt-0.5">
                      {items.projects.slice(0, 3).map((p) => (
                        <div
                          key={p.id}
                          className={cn('h-1.5 rounded-full flex-1 min-w-[8px] max-w-full', barColors[p.status] ?? 'bg-gray-400')}
                          title={p.name}
                        />
                      ))}
                      {items.events.slice(0, 2).map((e) => (
                        <div key={`e-${e.id}`} className="h-1.5 rounded-full flex-1 min-w-[8px] max-w-full bg-purple-500" title={e.name} />
                      ))}
                    </div>
                  )}
                  {compact && hasItems && (
                    <div className={cn(
                      'absolute bottom-0 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full',
                      items.projects.length > 0 ? (barColors[items.projects[0].status] ?? 'bg-gray-400') : 'bg-purple-500',
                    )} />
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    )
  }

  if (range === 'month') {
    return (
      <div className="space-y-3">
        {renderMonth(y, m)}
        {/* Campaign list below the grid */}
        {projects.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Campaigns ({projects.length})</div>
            {projects.map((p) => (
              <div
                key={p.id}
                className={cn('flex items-center gap-2 rounded-md px-2.5 py-2 cursor-pointer', barColors[p.status] ?? 'bg-gray-400')}
                onClick={() => onSelect(p)}
              >
                <span className="text-xs font-medium text-white truncate">{p.name}</span>
                <span className="ml-auto text-[10px] text-white/80 shrink-0">
                  {new Date(p.start_date!).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })} – {new Date(p.end_date!).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })}
                </span>
              </div>
            ))}
          </div>
        )}
        {events.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Events ({events.length})</div>
            {events.map((e) => (
              <div
                key={`evt-${e.id}`}
                className="flex items-center gap-2 rounded-md px-2.5 py-2 cursor-pointer bg-purple-500"
                onClick={onEventClick}
              >
                <span className="text-xs font-medium text-white truncate">{e.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Year view: 3 months per row, mini calendars
  const months = Array.from({ length: 12 }, (_, i) => i)
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        {months.map((mo) => (
          <div key={mo}>{renderMonth(y, mo, true)}</div>
        ))}
      </div>
      {/* Campaign list */}
      {projects.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Campaigns ({projects.length})</div>
          {projects.map((p) => (
            <div
              key={p.id}
              className={cn('flex items-center gap-2 rounded-md px-2.5 py-2 cursor-pointer', barColors[p.status] ?? 'bg-gray-400')}
              onClick={() => onSelect(p)}
            >
              <span className="text-xs font-medium text-white truncate">{p.name}</span>
              <span className="ml-auto text-[10px] text-white/80 shrink-0">
                {new Date(p.start_date!).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })} – {new Date(p.end_date!).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function CalendarView({ onSelect }: { onSelect: (p: MktProject) => void }) {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const [range, setRange] = useState<CalendarRange>('quarter')
  const [anchor, setAnchor] = useState(() => new Date())

  const { data, isLoading } = useQuery({
    queryKey: ['mkt-projects', { limit: 200, offset: 0 }],
    queryFn: () => marketingApi.listProjects({ limit: 200, offset: 0 }),
  })
  const { data: eventsData } = useQuery({
    queryKey: ['hr-events'],
    queryFn: () => hrApi.getEvents(),
  })
  const allProjects = (data?.projects ?? []).filter((p) => p.start_date && p.end_date)
  const allEvents = (eventsData ?? []).filter((e) => e.start_date && e.end_date)

  const { start: timeStart, end: timeEnd } = getRange(anchor, range)
  const totalMs = timeEnd.getTime() - timeStart.getTime()

  // Filter items overlapping current range
  const projects = allProjects.filter((p) => {
    const s = new Date(p.start_date!).getTime(), e = new Date(p.end_date!).getTime()
    return s < timeEnd.getTime() && e > timeStart.getTime()
  })
  const events = allEvents.filter((e) => {
    const s = new Date(e.start_date).getTime(), en = new Date(e.end_date).getTime()
    return s < timeEnd.getTime() && en > timeStart.getTime()
  })

  const markers = generateGridMarkers(timeStart, timeEnd, range)
  const todayPct = ((Date.now() - timeStart.getTime()) / totalMs) * 100

  const barColors: Record<string, string> = {
    draft: 'bg-gray-400',
    pending_approval: 'bg-yellow-400',
    approved: 'bg-green-400',
    active: 'bg-blue-500',
    paused: 'bg-orange-400',
    completed: 'bg-emerald-500',
    cancelled: 'bg-red-400',
    archived: 'bg-gray-300',
  }

  const renderGridAndToday = () => (
    <>
      {markers.map((m, i) => (
        <div key={i} className="absolute top-0 h-full border-l border-dashed border-muted-foreground/10" style={{ left: `${m.left}%` }} />
      ))}
      {todayPct >= 0 && todayPct <= 100 && (
        <div className="absolute top-0 h-full w-px bg-red-500/20" style={{ left: `${todayPct}%` }} />
      )}
    </>
  )

  const clampBar = (itemStart: Date, itemEnd: Date) => {
    const s = Math.max(itemStart.getTime(), timeStart.getTime())
    const e = Math.min(itemEnd.getTime(), timeEnd.getTime())
    return {
      leftPct: ((s - timeStart.getTime()) / totalMs) * 100,
      widthPct: ((e - s) / totalMs) * 100,
    }
  }

  const rangeButtons: { key: CalendarRange; label: string }[] = [
    { key: 'day', label: 'Day' },
    { key: 'week', label: 'Week' },
    { key: 'month', label: 'Month' },
    { key: 'quarter', label: 'Quarter' },
    { key: 'year', label: 'Year' },
  ]

  if (isLoading) return <TableSkeleton rows={6} columns={5} />

  return (
    <div className="space-y-4">
      {/* Toolbar: range selector + navigation */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border overflow-hidden">
          {rangeButtons.map((rb) => (
            <button
              key={rb.key}
              className={cn(
                'px-2.5 py-1 text-xs font-medium transition-colors',
                range === rb.key
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-background hover:bg-muted text-muted-foreground',
              )}
              onClick={() => setRange(rb.key)}
            >
              {rb.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" className="h-7 w-7" onClick={() => setAnchor(shiftAnchor(anchor, range, -1))}>
            <span className="text-xs">&larr;</span>
          </Button>
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setAnchor(new Date())}>
            Today
          </Button>
          <Button variant="outline" size="icon" className="h-7 w-7" onClick={() => setAnchor(shiftAnchor(anchor, range, 1))}>
            <span className="text-xs">&rarr;</span>
          </Button>
        </div>
        <span className="text-sm font-medium ml-1">{rangeTitle(anchor, range)}</span>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        {Object.entries(barColors).map(([status, cls]) => (
          <div key={status} className="flex items-center gap-1.5">
            <span className={`w-3 h-2 rounded-sm ${cls}`} />
            <span className="capitalize">{status.replace('_', ' ')}</span>
          </div>
        ))}
        {allEvents.length > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-2 rounded-sm bg-purple-500" />
            <span>Event</span>
          </div>
        )}
      </div>

      {projects.length === 0 && events.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          No campaigns or events in this period.
        </div>
      ) : isMobile && range === 'day' ? (
        <MobileDayView
          anchor={anchor}
          projects={projects}
          events={events}
          barColors={barColors}
          onSelect={onSelect}
          onEventClick={() => navigate('/app/marketing/events')}
        />
      ) : isMobile && range === 'week' ? (
        <MobileWeekView
          anchor={anchor}
          projects={projects}
          events={events}
          barColors={barColors}
          onSelect={onSelect}
          onEventClick={() => navigate('/app/marketing/events')}
        />
      ) : isMobile && range === 'quarter' ? (
        <MobileQuarterView
          anchor={anchor}
          projects={projects}
          events={events}
          barColors={barColors}
          onSelect={onSelect}
          onEventClick={() => navigate('/app/marketing/events')}
        />
      ) : isMobile && (range === 'month' || range === 'year') ? (
        <MobileCalendarGrid
          range={range}
          anchor={anchor}
          projects={projects}
          events={events}
          barColors={barColors}
          onSelect={onSelect}
          onEventClick={() => navigate('/app/marketing/events')}
        />
      ) : (
        <div className="rounded-lg border overflow-hidden">
          {/* Grid headers */}
          <div className="relative h-7 bg-muted/50 border-b">
            {markers.map((m, i) => (
              <div
                key={i}
                className="absolute top-0 h-full border-l border-dashed border-muted-foreground/20 flex items-center px-1"
                style={{ left: `${m.left}%` }}
              >
                <span className="text-[10px] text-muted-foreground font-medium whitespace-nowrap">{m.label}</span>
              </div>
            ))}
            {todayPct >= 0 && todayPct <= 100 && (
              <div className="absolute top-0 h-full w-px bg-red-500 z-10" style={{ left: `${todayPct}%` }}>
                <span className="absolute -top-0.5 -translate-x-1/2 text-[8px] text-red-500 font-bold">TODAY</span>
              </div>
            )}
          </div>

          {/* Campaign rows */}
          {projects.length > 0 && (
            <>
              <div className="px-2 py-1 bg-muted/30 border-b">
                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Campaigns ({projects.length})</span>
              </div>
              <div className="divide-y">
                {projects.map((p) => {
                  const { leftPct, widthPct } = clampBar(new Date(p.start_date!), new Date(p.end_date!))
                  const spent = typeof p.total_spent === 'string' ? parseFloat(p.total_spent) : (p.total_spent ?? 0)
                  const budget = typeof p.total_budget === 'string' ? parseFloat(p.total_budget as unknown as string) : (p.total_budget ?? 0)
                  const burn = burnRate(spent, budget)
                  return (
                    <div
                      key={p.id}
                      className="relative h-10 hover:bg-muted/30 cursor-pointer transition-colors group"
                      onClick={() => onSelect(p)}
                    >
                      {renderGridAndToday()}
                      <div
                        className={cn(
                          'absolute top-1.5 h-7 rounded-md flex items-center px-2 min-w-[40px] shadow-sm transition-shadow group-hover:shadow-md',
                          barColors[p.status] ?? 'bg-gray-400',
                        )}
                        style={{ left: `${Math.max(0, leftPct)}%`, width: `${Math.max(1, widthPct)}%` }}
                      >
                        <span className="text-[10px] font-medium text-white truncate drop-shadow-sm">
                          {p.name}
                        </span>
                        {budget > 0 && (
                          <span className="ml-auto text-[9px] text-white/80 shrink-0 tabular-nums pl-1">
                            {burn}%
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </>
          )}

          {/* Event rows */}
          {events.length > 0 && (
            <>
              <div className="px-2 py-1 bg-muted/30 border-b border-t">
                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Events ({events.length})</span>
              </div>
              <div className="divide-y">
                {events.map((e) => {
                  const { leftPct, widthPct } = clampBar(new Date(e.start_date), new Date(e.end_date))
                  return (
                    <div
                      key={`evt-${e.id}`}
                      className="relative h-10 hover:bg-muted/30 cursor-pointer transition-colors group"
                      onClick={() => navigate('/app/marketing/events')}
                    >
                      {renderGridAndToday()}
                      <div
                        className="absolute top-1.5 h-7 rounded-md flex items-center px-2 min-w-[40px] shadow-sm transition-shadow group-hover:shadow-md bg-purple-500"
                        style={{ left: `${Math.max(0, leftPct)}%`, width: `${Math.max(1, widthPct)}%` }}
                      >
                        <CalendarDays className="h-3 w-3 text-white shrink-0 mr-1" />
                        <span className="text-[10px] font-medium text-white truncate drop-shadow-sm">
                          {e.name}
                        </span>
                        {e.company && (
                          <span className="ml-auto text-[9px] text-white/80 shrink-0 pl-1">
                            {e.company}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}


// ---- Dashboard View ----

const DASH_WIDGETS_KEY = 'mkt-dashboard-widgets'
const ALL_WIDGETS = ['alerts', 'budgetByChannel', 'kpiScoreboard', 'channelAttribution', 'budgetVsActual', 'channelPerformance'] as const
type DashWidget = (typeof ALL_WIDGETS)[number]
const WIDGET_LABELS: Record<DashWidget, string> = {
  alerts: 'Budget Alerts',
  budgetByChannel: 'Budget by Channel',
  kpiScoreboard: 'KPI Scoreboard',
  channelAttribution: 'Channel Attribution',
  budgetVsActual: 'Budget vs Actual',
  channelPerformance: 'Channel Performance',
}

export function useDashboardWidgets() {
  const [visibleWidgets, setVisibleWidgets] = useState<Set<DashWidget>>(() => {
    try {
      const saved = localStorage.getItem(DASH_WIDGETS_KEY)
      return saved ? new Set(JSON.parse(saved) as DashWidget[]) : new Set(ALL_WIDGETS)
    } catch { return new Set(ALL_WIDGETS) }
  })

  function toggleWidget(w: DashWidget) {
    setVisibleWidgets((prev) => {
      const next = new Set(prev)
      if (next.has(w)) next.delete(w); else next.add(w)
      try { localStorage.setItem(DASH_WIDGETS_KEY, JSON.stringify([...next])) } catch { /* ignore */ }
      return next
    })
  }

  const customizeButton = (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="h-8 w-8" title="Customize">
          <SlidersHorizontal className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-2" align="end">
        <div className="text-xs font-semibold text-muted-foreground px-2 pb-1.5">Toggle Widgets</div>
        {ALL_WIDGETS.map((w) => (
          <button
            key={w}
            type="button"
            className="flex items-center gap-2 w-full px-2 py-1.5 rounded-sm text-sm hover:bg-muted transition-colors"
            onClick={() => toggleWidget(w)}
          >
            <div className={cn(
              'h-3.5 w-3.5 rounded border flex items-center justify-center',
              visibleWidgets.has(w) ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground/30',
            )}>
              {visibleWidgets.has(w) && <Check className="h-2.5 w-2.5" />}
            </div>
            {WIDGET_LABELS[w]}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )

  return { visibleWidgets, customizeButton }
}

export function DashboardView({ showStats, widgetVisibility }: { showStats: boolean; widgetVisibility?: Set<DashWidget> }) {
  const navigate = useNavigate()

  // Fallback: if no external widget visibility passed, use internal default (all visible)
  const fallbackWidgets = useMemo(() => new Set(ALL_WIDGETS), [])
  const activeWidgets = widgetVisibility ?? fallbackWidgets
  const showWidget = (w: DashWidget) => activeWidgets.has(w)

  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ['mkt-dashboard-summary'],
    queryFn: () => marketingApi.getDashboardSummary(),
  })
  const summary = summaryData?.summary

  const { data: budgetData, isLoading: budgetLoading } = useQuery({
    queryKey: ['mkt-budget-overview'],
    queryFn: () => marketingApi.getBudgetOverview(),
  })
  const channels = budgetData?.channels ?? []

  const { data: scoreboardData, isLoading: scoreboardLoading } = useQuery({
    queryKey: ['mkt-kpi-scoreboard'],
    queryFn: () => marketingApi.getKpiScoreboard(),
  })
  const kpis = scoreboardData?.kpis ?? []

  const { data: bvaData, isLoading: bvaLoading } = useQuery({
    queryKey: ['mkt-report-bva'],
    queryFn: () => marketingApi.getReportBudgetVsActual(),
  })
  const bvaProjects = bvaData?.projects ?? []

  const { data: channelPerfData, isLoading: channelPerfLoading } = useQuery({
    queryKey: ['mkt-report-channel-perf'],
    queryFn: () => marketingApi.getReportChannelPerformance(),
  })
  const channelPerf = channelPerfData?.channels ?? []

  const totalPlanned = channels.reduce((s, c) => s + (Number(c.planned) || 0), 0)
  const totalSpent = channels.reduce((s, c) => s + (Number(c.spent) || 0), 0)

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className={`grid grid-cols-2 gap-3 lg:grid-cols-5 ${showStats ? '' : 'hidden'}`}>
        <StatCard title="Active" value={summary?.active_count ?? 0} icon={<FolderOpen className="h-4 w-4" />} isLoading={summaryLoading} />
        <StatCard title="Draft" value={summary?.draft_count ?? 0} icon={<FileText className="h-4 w-4" />} isLoading={summaryLoading} />
        <StatCard title="Total Budget" value={formatCurrency(summary?.total_budget)} icon={<DollarSign className="h-4 w-4" />} isLoading={summaryLoading} />
        <StatCard title="Total Spent" value={formatCurrency(summary?.total_spent)} icon={<Target className="h-4 w-4" />} isLoading={summaryLoading} />
        <StatCard title="KPI Alerts" value={summary?.kpi_alerts ?? 0} icon={<AlertTriangle className="h-4 w-4" />} isLoading={summaryLoading} />
      </div>

      {/* Budget Alerts Panel */}
      {showWidget('alerts') && !bvaLoading && (() => {
        const alerts = bvaProjects
          .map((p: Record<string, unknown>) => ({
            id: p.id as number,
            name: p.name as string,
            budget: Number(p.total_budget) || 0,
            spent: Number(p.total_spent) || 0,
            util: Number(p.utilization_pct) || 0,
            status: p.status as string,
          }))
          .filter((p) => p.budget > 0 && p.util >= 70 && p.status !== 'completed')
          .sort((a, b) => b.util - a.util)

        if (alerts.length === 0) return null
        return (
          <div className="rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-50/50 dark:bg-orange-950/10 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-600" />
              <h3 className="font-semibold text-sm text-orange-800 dark:text-orange-200">Budget Alerts ({alerts.length})</h3>
            </div>
            <div className="space-y-2">
              {alerts.slice(0, 5).map((a) => (
                <div
                  key={a.id}
                  className="flex items-center gap-3 rounded-md bg-background/60 px-3 py-2 cursor-pointer hover:bg-background transition-colors"
                  onClick={() => navigate(`/app/marketing/projects/${a.id}`)}
                >
                  {a.util >= 100 ? (
                    <AlertCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                  ) : (
                    <AlertTriangle className="h-3.5 w-3.5 text-orange-500 shrink-0" />
                  )}
                  <span className="text-sm font-medium truncate flex-1">{a.name}</span>
                  <span className={cn('text-xs font-medium tabular-nums', a.util >= 100 ? 'text-red-600' : 'text-orange-600')}>
                    {a.util}%
                  </span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {formatCurrency(a.budget - a.spent)} left
                  </span>
                </div>
              ))}
              {alerts.length > 5 && (
                <div className="text-xs text-muted-foreground text-center pt-1">+{alerts.length - 5} more alerts</div>
              )}
            </div>
          </div>
        )
      })()}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Budget by Channel */}
        {showWidget('budgetByChannel') && <div className="rounded-lg border p-4 space-y-4">
          <div className="flex items-center gap-2">
            <PieChart className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold text-sm">Budget by Channel</h3>
          </div>
          {budgetLoading ? (
            <TableSkeleton rows={4} columns={3} showHeader={false} />
          ) : channels.length === 0 ? (
            <div className="text-center py-6 text-sm text-muted-foreground">
              <DollarSign className="mx-auto h-6 w-6 mb-1.5 opacity-40" />
              No budget data yet. Add budget lines to your campaigns.
            </div>
          ) : (
            <div className="space-y-3">
              {/* Mini donut + legend */}
              {(() => {
                const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#f97316']
                const sz = 100, cx = 50, cy = 50, r = 35, sw = 16
                let cum = 0
                const arcs = channels.map((ch, i) => {
                  const planned = Number(ch.planned) || 0
                  const pct = totalPlanned > 0 ? planned / totalPlanned : 0
                  const sa = cum * 2 * Math.PI - Math.PI / 2
                  cum += pct
                  const ea = cum * 2 * Math.PI - Math.PI / 2
                  const la = pct > 0.5 ? 1 : 0
                  const x1 = cx + r * Math.cos(sa), y1 = cy + r * Math.sin(sa)
                  const x2 = cx + r * Math.cos(ea), y2 = cy + r * Math.sin(ea)
                  return {
                    channel: ch.channel, color: COLORS[i % COLORS.length], pct,
                    d: pct >= 0.999
                      ? `M ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx + r - 0.001} ${cy}`
                      : `M ${x1} ${y1} A ${r} ${r} 0 ${la} 1 ${x2} ${y2}`,
                  }
                })
                return (
                  <div className="flex items-center gap-4">
                    <svg width={sz} height={sz} viewBox={`0 0 ${sz} ${sz}`} className="shrink-0">
                      {arcs.map((a, i) => (
                        <path key={i} d={a.d} fill="none" stroke={a.color} strokeWidth={sw} strokeLinecap="butt" />
                      ))}
                      <text x={cx} y={cy + 4} textAnchor="middle" className="fill-foreground text-xs font-bold">
                        {totalPlanned >= 1000 ? `${(totalPlanned / 1000).toFixed(0)}k` : totalPlanned}
                      </text>
                    </svg>
                    <div className="flex-1 grid grid-cols-2 gap-x-3 gap-y-1">
                      {arcs.map((a, i) => (
                        <div key={i} className="flex items-center gap-1.5 text-xs">
                          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: a.color }} />
                          <span className="truncate">{a.channel.replace('_', ' ')}</span>
                          <span className="text-muted-foreground ml-auto">{Math.round(a.pct * 100)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })()}
              {/* Channel bars */}
              {channels.map((ch) => {
                const planned = Number(ch.planned) || 0
                const spent = Number(ch.spent) || 0
                const pct = totalPlanned ? Math.round((planned / totalPlanned) * 100) : 0
                const util = planned ? Math.round((spent / planned) * 100) : 0
                return (
                  <div key={ch.channel} className="space-y-1.5">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">{(ch.channel ?? '').replace('_', ' ')}</Badge>
                        <span className="text-xs text-muted-foreground">{ch.project_count} project{ch.project_count !== 1 ? 's' : ''}</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs tabular-nums">
                        <span>{formatCurrency(spent)} / {formatCurrency(planned)}</span>
                        <span className="text-muted-foreground">{pct}%</span>
                      </div>
                    </div>
                    <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full ${util > 90 ? 'bg-red-500' : util > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                        style={{ width: `${Math.min(util, 100)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
              <div className="pt-2 border-t flex justify-between text-sm font-medium">
                <span>Total</span>
                <span className="tabular-nums">{formatCurrency(totalSpent)} / {formatCurrency(totalPlanned)}</span>
              </div>
            </div>
          )}
        </div>}

        {/* KPI Scoreboard — Matrix Grid */}
        {showWidget('kpiScoreboard') && <div className="rounded-lg border p-4 space-y-4">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold text-sm">KPI Scoreboard (Active Projects)</h3>
          </div>
          {scoreboardLoading ? (
            <TableSkeleton rows={3} columns={5} />
          ) : kpis.length === 0 ? (
            <div className="text-center py-6 text-sm text-muted-foreground">
              <Target className="mx-auto h-6 w-6 mb-1.5 opacity-40" />
              No KPIs tracked. Configure KPIs on your active campaigns.
            </div>
          ) : (
            <KpiMatrix kpis={kpis} onProjectClick={(id) => navigate(`/app/marketing/projects/${id}`)} />
          )}
        </div>}
      </div>

      {/* Budget vs Actual Report */}
      {showWidget('budgetVsActual') && <div className="rounded-lg border p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold text-sm">Budget vs Actual</h3>
          </div>
          {bvaProjects.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => exportCsv(
              ['Project', 'Status', 'Budget', 'Approved', 'Spent', 'Variance', 'Utilization %'],
              bvaProjects.map((p: Record<string, unknown>) => {
                const budget = Number(p.total_budget) || 0
                const spent = Number(p.total_spent) || 0
                return [p.name as string, p.status as string, budget, Number(p.total_approved) || 0, spent, budget - spent, Number(p.utilization_pct) || 0]
              }),
              'budget-vs-actual',
            )}>
              <Download className="h-3.5 w-3.5 mr-1.5" /> Export CSV
            </Button>
          )}
        </div>
        {bvaLoading ? (
          <TableSkeleton rows={4} columns={6} />
        ) : bvaProjects.length === 0 ? (
          <div className="text-center py-6 text-sm text-muted-foreground">
            <BarChart3 className="mx-auto h-6 w-6 mb-1.5 opacity-40" />
            No budget vs actual data. Create campaigns with budgets to see comparisons.
          </div>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Project</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Budget</TableHead>
                  <TableHead className="text-right">Approved</TableHead>
                  <TableHead className="text-right">Spent</TableHead>
                  <TableHead className="text-right">Variance</TableHead>
                  <TableHead>Utilization</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bvaProjects.map((p: Record<string, unknown>) => {
                  const budget = Number(p.total_budget) || 0
                  const spent = Number(p.total_spent) || 0
                  const approved = Number(p.total_approved) || 0
                  const util = Number(p.utilization_pct) || 0
                  const variance = budget - spent
                  return (
                    <TableRow
                      key={p.id as number}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/app/marketing/projects/${p.id}`)}
                    >
                      <TableCell className="text-sm font-medium">{p.name as string}</TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[p.status as string] ?? ''}`}>
                          {(p.status as string ?? '').replace('_', ' ')}
                        </span>
                      </TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{formatCurrency(budget)}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{formatCurrency(approved)}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{formatCurrency(spent)}</TableCell>
                      <TableCell className={cn('text-right text-sm tabular-nums', variance < 0 ? 'text-red-600' : 'text-green-600')}>
                        {variance >= 0 ? '+' : ''}{formatCurrency(variance)}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-2 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full ${util > 90 ? 'bg-red-500' : util > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                              style={{ width: `${Math.min(util, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">{util}%</span>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>}

      {/* Channel Attribution Summary */}
      {showWidget('channelAttribution') && !channelPerfLoading && channelPerf.length > 1 && (() => {
        const sorted = [...channelPerf]
          .map((ch: Record<string, unknown>) => ({
            channel: ch.channel as string,
            planned: Number(ch.total_planned) || 0,
            spent: Number(ch.total_spent) || 0,
            util: Number(ch.avg_utilization) || 0,
            projects: Number(ch.project_count) || 0,
          }))
          .filter((c) => c.planned > 0)
          .sort((a, b) => b.spent - a.spent)
        const maxSpent = Math.max(...sorted.map((c) => c.spent), 1)
        const totalChannelSpent = sorted.reduce((s, c) => s + c.spent, 0)

        return (
          <div className="rounded-lg border p-4 space-y-4">
            <div className="flex items-center gap-2">
              <GitCompareArrows className="h-4 w-4 text-muted-foreground" />
              <h3 className="font-semibold text-sm">Channel Attribution</h3>
            </div>
            <div className="space-y-3">
              {sorted.map((ch) => {
                const shareOfSpend = totalChannelSpent ? Math.round((ch.spent / totalChannelSpent) * 100) : 0
                const efficiency = ch.util <= 80 ? 'text-green-600 dark:text-green-400' : ch.util <= 95 ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400'
                return (
                  <div key={ch.channel} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs capitalize">{ch.channel.replace('_', ' ')}</Badge>
                        <span className="text-xs text-muted-foreground">{ch.projects} campaign{ch.projects !== 1 ? 's' : ''}</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs tabular-nums">
                        <span className="text-muted-foreground">{shareOfSpend}% of spend</span>
                        <span className={efficiency}>{Math.round(ch.util)}% util</span>
                        <span className="font-medium">{formatCurrency(ch.spent)}</span>
                      </div>
                    </div>
                    <div className="flex gap-1 items-center">
                      <div className="flex-1 h-3 rounded bg-muted overflow-hidden">
                        <div
                          className="h-full rounded bg-blue-500/80 transition-all"
                          style={{ width: `${(ch.spent / maxSpent) * 100}%` }}
                        />
                      </div>
                      <div className="w-12 h-3 rounded bg-muted overflow-hidden">
                        <div
                          className={cn('h-full rounded transition-all', ch.util > 90 ? 'bg-red-500' : ch.util > 70 ? 'bg-yellow-500' : 'bg-green-500')}
                          style={{ width: `${Math.min(ch.util, 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
            <div className="text-[10px] text-muted-foreground flex items-center gap-4 pt-1">
              <span>Long bar = spend share</span>
              <span>Short bar = utilization</span>
            </div>
          </div>
        )
      })()}

      {/* Channel Performance Report */}
      {showWidget('channelPerformance') && <div className="rounded-lg border p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <PieChart className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold text-sm">Channel Performance</h3>
          </div>
          {channelPerf.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => exportCsv(
              ['Channel', 'Total Planned', 'Total Spent', 'Variance', 'Avg Utilization %', 'Spend/Project', 'Projects'],
              channelPerf.map((ch: Record<string, unknown>) => {
                const planned = Number(ch.total_planned) || 0
                const spent = Number(ch.total_spent) || 0
                const cnt = Number(ch.project_count) || 1
                return [ch.channel as string, planned, spent, planned - spent, Math.round(Number(ch.avg_utilization) || 0), Math.round(spent / cnt), cnt]
              }),
              'channel-performance',
            )}>
              <Download className="h-3.5 w-3.5 mr-1.5" /> Export CSV
            </Button>
          )}
        </div>
        {channelPerfLoading ? (
          <TableSkeleton rows={3} columns={5} />
        ) : channelPerf.length === 0 ? (
          <div className="text-center py-6 text-sm text-muted-foreground">
            <PieChart className="mx-auto h-6 w-6 mb-1.5 opacity-40" />
            No channel performance data yet.
          </div>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Channel</TableHead>
                  <TableHead className="text-right">Total Planned</TableHead>
                  <TableHead className="text-right">Total Spent</TableHead>
                  <TableHead className="text-right">Variance</TableHead>
                  <TableHead>Avg Utilization</TableHead>
                  <TableHead className="text-right">Spend/Project</TableHead>
                  <TableHead className="text-right">Projects</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {channelPerf.map((ch: Record<string, unknown>) => {
                  const planned = Number(ch.total_planned) || 0
                  const spent = Number(ch.total_spent) || 0
                  const avgUtil = Number(ch.avg_utilization) || 0
                  const variance = planned - spent
                  const projCount = Number(ch.project_count) || 1
                  return (
                    <TableRow key={ch.channel as string}>
                      <TableCell>
                        <Badge variant="outline" className="text-xs">{((ch.channel as string) ?? '').replace('_', ' ')}</Badge>
                      </TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{formatCurrency(planned)}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{formatCurrency(spent)}</TableCell>
                      <TableCell className={cn('text-right text-sm tabular-nums', variance < 0 ? 'text-red-600' : 'text-green-600')}>
                        {variance >= 0 ? '+' : ''}{formatCurrency(variance)}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-2 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full ${avgUtil > 90 ? 'bg-red-500' : avgUtil > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                              style={{ width: `${Math.min(avgUtil, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">{Math.round(avgUtil)}%</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{formatCurrency(Math.round(spent / projCount))}</TableCell>
                      <TableCell className="text-right text-sm">{ch.project_count as number}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>}
    </div>
  )
}


// ---- KPI Matrix Grid ----

const kpiCellColors: Record<string, string> = {
  on_track: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  exceeded: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  at_risk: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  behind: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  no_data: 'bg-gray-100 text-gray-500 dark:bg-gray-800/40 dark:text-gray-400',
}

function KpiMatrix({ kpis, onProjectClick }: {
  kpis: MktKpiScoreboardItem[]
  onProjectClick: (id: number) => void
}) {
  // Pivot: rows = projects, cols = unique KPI names
  const projectMap = new Map<number, { name: string; kpis: Map<string, MktKpiScoreboardItem> }>()
  const kpiNames = new Set<string>()

  for (const k of kpis) {
    kpiNames.add(k.kpi_name)
    if (!projectMap.has(k.project_id)) {
      projectMap.set(k.project_id, { name: k.project_name, kpis: new Map() })
    }
    projectMap.get(k.project_id)!.kpis.set(k.kpi_name, k)
  }

  const kpiCols = Array.from(kpiNames)
  const projects = Array.from(projectMap.entries())

  return (
    <TooltipProvider delayDuration={200}>
      <div className="overflow-x-auto max-h-80">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sticky left-0 z-10 bg-card min-w-[140px]">Project</TableHead>
              {kpiCols.map((name) => (
                <TableHead key={name} className="text-center text-xs min-w-[90px]">{name}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {projects.map(([pid, proj]) => (
              <TableRow
                key={pid}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => onProjectClick(pid)}
              >
                <TableCell className="sticky left-0 z-10 bg-card text-sm font-medium">{proj.name}</TableCell>
                {kpiCols.map((kpiName) => {
                  const k = proj.kpis.get(kpiName)
                  if (!k) return <TableCell key={kpiName} className="text-center text-xs text-muted-foreground">—</TableCell>
                  const current = Number(k.current_value) || 0
                  const target = Number(k.target_value) || 0
                  const pct = target ? Math.round((current / target) * 100) : 0
                  return (
                    <TableCell key={kpiName} className="p-1 text-center">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className={cn(
                            'rounded px-2 py-1.5 text-xs font-medium tabular-nums',
                            kpiCellColors[k.status] ?? kpiCellColors.no_data,
                          )}>
                            {current.toLocaleString('ro-RO')}
                          </div>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="text-xs">
                          <div className="space-y-0.5">
                            <div className="font-medium">{kpiName}</div>
                            <div>Current: {current.toLocaleString('ro-RO')}</div>
                            <div>Target: {target ? target.toLocaleString('ro-RO') : '—'}</div>
                            <div>Progress: {pct}% &middot; {k.status.replace('_', ' ')}</div>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>
                  )
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </TooltipProvider>
  )
}


// ---- Archived View ----

function ArchivedView({ onRestore, onDelete }: { onRestore: () => void; onDelete: () => void }) {
  const [confirming, setConfirming] = useState<number | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['mkt-archived'],
    queryFn: () => marketingApi.getArchivedProjects(),
  })
  const projects = data?.projects ?? []

  const handleRestore = async (id: number) => {
    await marketingApi.restoreProject(id)
    onRestore()
    refetch()
  }

  const handleDelete = async (id: number) => {
    await marketingApi.deleteProject(id)
    onDelete()
    refetch()
    setConfirming(null)
  }

  if (isError) return <QueryError message="Failed to load archived projects" onRetry={() => refetch()} />
  if (isLoading) return <TableSkeleton rows={4} columns={5} />

  return (
    <div className="space-y-4">
      {projects.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Archive className="mx-auto h-8 w-8 mb-2 opacity-50" />
          No archived projects.
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((p) => (
            <div key={p.id} className="flex items-center gap-4 rounded-lg border p-4 opacity-80">
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold truncate">{p.name}</h3>
                <p className="text-sm text-muted-foreground">{p.company_name}{p.brand_name ? ` / ${p.brand_name}` : ''}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Owner: {p.owner_name} &middot; Budget: {formatCurrency(p.total_budget, p.currency)}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button variant="outline" size="sm" onClick={() => handleRestore(p.id)}>
                  <RotateCcw className="h-3.5 w-3.5 mr-1" /> Restore
                </Button>
                {confirming === p.id ? (
                  <div className="flex items-center gap-1">
                    <Button variant="destructive" size="sm" onClick={() => handleDelete(p.id)}>Confirm</Button>
                    <Button variant="ghost" size="sm" onClick={() => setConfirming(null)}>Cancel</Button>
                  </div>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => setConfirming(p.id)}>
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// ---- Trash View ----

function TrashView({ onRestore, onPermanentDelete }: { onRestore: () => void; onPermanentDelete: () => void }) {
  const [confirming, setConfirming] = useState<number | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['mkt-trash'],
    queryFn: () => marketingApi.getTrashProjects(),
  })
  const projects = data?.projects ?? []

  const handleRestore = async (id: number) => {
    await marketingApi.restoreProject(id)
    onRestore()
    refetch()
  }

  const handlePermanentDelete = async (id: number) => {
    await marketingApi.permanentDeleteProject(id)
    onPermanentDelete()
    refetch()
    setConfirming(null)
  }

  if (isError) return <QueryError message="Failed to load trash" onRetry={() => refetch()} />
  if (isLoading) return <TableSkeleton rows={4} columns={5} />

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-700 p-3 text-sm">
        <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
        <span className="text-amber-800 dark:text-amber-200">Projects in trash can be restored or permanently deleted.</span>
      </div>

      {projects.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Trash2 className="mx-auto h-8 w-8 mb-2 opacity-50" />
          Trash is empty.
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((p) => (
            <div key={p.id} className="flex items-center gap-4 rounded-lg border border-dashed p-4 opacity-60">
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold truncate">{p.name}</h3>
                <p className="text-sm text-muted-foreground">{p.company_name}{p.brand_name ? ` / ${p.brand_name}` : ''}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Deleted: {p.deleted_at ? new Date(p.deleted_at).toLocaleDateString('ro-RO') : '—'}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button variant="outline" size="sm" onClick={() => handleRestore(p.id)}>
                  <RotateCcw className="h-3.5 w-3.5 mr-1" /> Restore
                </Button>
                {confirming === p.id ? (
                  <div className="flex items-center gap-1">
                    <Button variant="destructive" size="sm" onClick={() => handlePermanentDelete(p.id)}>Delete Forever</Button>
                    <Button variant="ghost" size="sm" onClick={() => setConfirming(null)}>Cancel</Button>
                  </div>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => setConfirming(p.id)} className="text-destructive">
                    <Trash2 className="h-3.5 w-3.5 mr-1" /> Delete
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// ---- Compare Panel ----

function ComparePanel({ projects, onClose }: { projects: MktProject[]; onClose: () => void }) {
  const rows: { label: string; values: (p: MktProject) => React.ReactNode }[] = [
    { label: 'Status', values: (p) => (
      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[p.status] ?? ''}`}>
        {(p.status ?? '').replace('_', ' ')}
      </span>
    )},
    { label: 'Health', values: (p) => <HealthBadge project={p} /> },
    { label: 'Company', values: (p) => <span className="text-sm">{p.company_name}</span> },
    { label: 'Type', values: (p) => <span className="text-sm capitalize">{(p.project_type ?? '').replace('_', ' ')}</span> },
    { label: 'Budget', values: (p) => <span className="text-sm tabular-nums">{formatCurrency(p.total_budget, p.currency)}</span> },
    { label: 'Spent', values: (p) => <span className="text-sm tabular-nums">{formatCurrency(p.total_spent, p.currency)}</span> },
    { label: 'Burn Rate', values: (p) => {
      const b = burnRate(
        typeof p.total_spent === 'string' ? parseFloat(p.total_spent) : (p.total_spent ?? 0),
        typeof p.total_budget === 'string' ? parseFloat(p.total_budget as unknown as string) : (p.total_budget ?? 0),
      )
      return (
        <div className="flex items-center gap-2">
          <div className="w-16 h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full ${b > 90 ? 'bg-red-500' : b > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
              style={{ width: `${Math.min(b, 100)}%` }}
            />
          </div>
          <span className="text-xs">{b}%</span>
        </div>
      )
    }},
    { label: 'Owner', values: (p) => <span className="text-sm">{p.owner_name ?? '—'}</span> },
    { label: 'Channels', values: (p) => (
      <div className="flex flex-wrap gap-1">
        {(p.channel_mix ?? []).map((ch) => (
          <Badge key={ch} variant="secondary" className="text-[10px]">{ch.replace('_', ' ')}</Badge>
        ))}
        {(!p.channel_mix || p.channel_mix.length === 0) && <span className="text-xs text-muted-foreground">—</span>}
      </div>
    )},
    { label: 'Start', values: (p) => <span className="text-sm">{p.start_date ? new Date(p.start_date).toLocaleDateString('ro-RO') : '—'}</span> },
    { label: 'End', values: (p) => <span className="text-sm">{p.end_date ? new Date(p.end_date).toLocaleDateString('ro-RO') : '—'}</span> },
  ]

  return (
    <div className="rounded-lg border bg-card shadow-md">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h3 className="font-semibold text-sm flex items-center gap-2">
          <GitCompareArrows className="h-4 w-4" />
          Comparing {projects.length} Campaigns
        </h3>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[120px] text-xs">Metric</TableHead>
              {projects.map((p) => (
                <TableHead key={p.id} className="text-xs min-w-[160px]">{p.name}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.label}>
                <TableCell className="text-xs font-medium text-muted-foreground">{row.label}</TableCell>
                {projects.map((p) => (
                  <TableCell key={p.id}>{row.values(p)}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}


// ---- CSV Export Helper ----

function exportCsv(headers: string[], rows: (string | number | null | undefined)[][], filename: string) {
  const escape = (v: unknown) => {
    const s = String(v ?? '')
    return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [headers.map(escape).join(','), ...rows.map((r) => r.map(escape).join(','))].join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${filename}-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
