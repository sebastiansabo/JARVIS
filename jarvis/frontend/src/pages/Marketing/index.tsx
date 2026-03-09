import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { useTabParam } from '@/hooks/useTabParam'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
  Archive, Trash2, RotateCcw, AlertCircle, Heart, GitCompareArrows, X, Check,
} from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { marketingApi } from '@/api/marketing'
import { settingsApi } from '@/api/settings'
import { organizationApi } from '@/api/organization'
import { QueryError } from '@/components/QueryError'
import { useMarketingStore } from '@/stores/marketingStore'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
import type { MktProject, MktKpiScoreboardItem } from '@/types/marketing'
import ProjectForm from './ProjectForm'


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

import { Calendar } from 'lucide-react'

type MainTab = 'projects' | 'dashboard' | 'calendar' | 'archived' | 'trash'

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
  const [mainTab, setMainTab] = useTabParam<MainTab>('dashboard')
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
          { label: mainTab === 'projects' ? `Campaigns (${total})` : mainTab === 'dashboard' ? 'Dashboard' : mainTab === 'calendar' ? 'Calendar' : mainTab === 'archived' ? 'Archived' : 'Trash' },
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
                  <TabsTrigger value="dashboard"><BarChart3 className="h-3.5 w-3.5" />Dashboard</TabsTrigger>
                  <TabsTrigger value="projects"><FolderOpen className="h-3.5 w-3.5" />Campaigns</TabsTrigger>
                  <TabsTrigger value="calendar"><Calendar className="h-3.5 w-3.5" />Calendar</TabsTrigger>
                  <TabsTrigger value="archived"><Archive className="h-3.5 w-3.5" />Archived</TabsTrigger>
                  <TabsTrigger value="trash"><Trash2 className="h-3.5 w-3.5" />Trash</TabsTrigger>
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
              <TabsTrigger value="dashboard"><BarChart3 className="h-3.5 w-3.5" />Dashboard</TabsTrigger>
              <TabsTrigger value="projects"><FolderOpen className="h-3.5 w-3.5" />Campaigns</TabsTrigger>
              <TabsTrigger value="calendar"><Calendar className="h-3.5 w-3.5" />Calendar</TabsTrigger>
              <TabsTrigger value="archived"><Archive className="h-3.5 w-3.5" />Archived</TabsTrigger>
              <TabsTrigger value="trash"><Trash2 className="h-3.5 w-3.5" />Trash</TabsTrigger>
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

      {mainTab === 'dashboard' && <DashboardView showStats={showStats} />}

      {mainTab === 'calendar' && (
        <CalendarView
          onSelect={(p) => navigate(`/app/marketing/projects/${p.id}`)}
        />
      )}

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
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" aria-describedby={undefined}>
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

function computeHealthScore(p: MktProject): { score: number; label: string; color: string; icon: React.ElementType } {
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

  // Score: 100 = perfect, 0 = terrible
  // Budget health: penalize if burn significantly outpaces timeline
  let budgetHealth = 100
  if (budget > 0) {
    const expectedBurn = timelinePct || 50 // If no dates, assume midpoint
    const burnDelta = burn - expectedBurn
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

  if (score >= 80) return { score, label: 'Healthy', color: 'text-green-600 dark:text-green-400', icon: Heart }
  if (score >= 50) return { score, label: 'At Risk', color: 'text-yellow-600 dark:text-yellow-400', icon: AlertTriangle }
  return { score, label: 'Critical', color: 'text-red-600 dark:text-red-400', icon: AlertCircle }
}

function HealthBadge({ project }: { project: MktProject }) {
  const health = computeHealthScore(project)
  const Icon = health.icon
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={`inline-flex items-center gap-1 text-xs font-medium ${health.color}`}>
            <Icon className="h-3 w-3" />
            {health.score}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-xs">
          <div>Health: {health.label} ({health.score}/100)</div>
          <div className="text-muted-foreground">Budget + timeline + status composite</div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
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
            <TableHead className="text-center w-14">Health</TableHead>
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

function CalendarView({ onSelect }: { onSelect: (p: MktProject) => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['mkt-projects', { limit: 200, offset: 0 }],
    queryFn: () => marketingApi.listProjects({ limit: 200, offset: 0 }),
  })
  const projects = (data?.projects ?? []).filter((p) => p.start_date && p.end_date)

  if (isLoading) return <TableSkeleton rows={6} columns={5} />
  if (projects.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No projects with date ranges found. Set start/end dates to see the timeline.
      </div>
    )
  }

  // Compute timeline bounds
  const allDates = projects.flatMap((p) => [new Date(p.start_date!), new Date(p.end_date!)])
  const minDate = new Date(Math.min(...allDates.map((d) => d.getTime())))
  const maxDate = new Date(Math.max(...allDates.map((d) => d.getTime())))
  // Pad by 7 days each side
  const timeStart = new Date(minDate.getTime() - 7 * 86400000)
  const timeEnd = new Date(maxDate.getTime() + 7 * 86400000)
  const totalMs = timeEnd.getTime() - timeStart.getTime()

  // Generate month markers
  const months: { label: string; left: number }[] = []
  const cursor = new Date(timeStart.getFullYear(), timeStart.getMonth(), 1)
  while (cursor <= timeEnd) {
    const left = ((cursor.getTime() - timeStart.getTime()) / totalMs) * 100
    months.push({ label: cursor.toLocaleDateString('ro-RO', { month: 'short', year: '2-digit' }), left: Math.max(0, left) })
    cursor.setMonth(cursor.getMonth() + 1)
  }

  // Today marker
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        {Object.entries(barColors).map(([status, cls]) => (
          <div key={status} className="flex items-center gap-1.5">
            <span className={`w-3 h-2 rounded-sm ${cls}`} />
            <span className="capitalize">{status.replace('_', ' ')}</span>
          </div>
        ))}
      </div>

      <div className="rounded-lg border overflow-hidden">
        {/* Month headers */}
        <div className="relative h-7 bg-muted/50 border-b">
          {months.map((m, i) => (
            <div
              key={i}
              className="absolute top-0 h-full border-l border-dashed border-muted-foreground/20 flex items-center px-1.5"
              style={{ left: `${m.left}%` }}
            >
              <span className="text-[10px] text-muted-foreground font-medium whitespace-nowrap">{m.label}</span>
            </div>
          ))}
          {/* Today line */}
          {todayPct >= 0 && todayPct <= 100 && (
            <div className="absolute top-0 h-full w-px bg-red-500 z-10" style={{ left: `${todayPct}%` }}>
              <span className="absolute -top-0.5 -translate-x-1/2 text-[8px] text-red-500 font-bold">TODAY</span>
            </div>
          )}
        </div>

        {/* Project rows */}
        <div className="divide-y">
          {projects.map((p) => {
            const start = new Date(p.start_date!)
            const end = new Date(p.end_date!)
            const leftPct = ((start.getTime() - timeStart.getTime()) / totalMs) * 100
            const widthPct = ((end.getTime() - start.getTime()) / totalMs) * 100
            const spent = typeof p.total_spent === 'string' ? parseFloat(p.total_spent) : (p.total_spent ?? 0)
            const budget = typeof p.total_budget === 'string' ? parseFloat(p.total_budget as unknown as string) : (p.total_budget ?? 0)
            const burn = burnRate(spent, budget)
            return (
              <div
                key={p.id}
                className="relative h-10 hover:bg-muted/30 cursor-pointer transition-colors group"
                onClick={() => onSelect(p)}
              >
                {/* Month grid lines */}
                {months.map((m, i) => (
                  <div key={i} className="absolute top-0 h-full border-l border-dashed border-muted-foreground/10" style={{ left: `${m.left}%` }} />
                ))}
                {/* Today line */}
                {todayPct >= 0 && todayPct <= 100 && (
                  <div className="absolute top-0 h-full w-px bg-red-500/20" style={{ left: `${todayPct}%` }} />
                )}
                {/* Bar */}
                <div
                  className={cn(
                    'absolute top-1.5 h-7 rounded-md flex items-center px-2 min-w-[40px] shadow-sm transition-shadow group-hover:shadow-md',
                    barColors[p.status] ?? 'bg-gray-400',
                  )}
                  style={{ left: `${Math.max(0, leftPct)}%`, width: `${Math.max(2, widthPct)}%` }}
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
      </div>
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

function DashboardView({ showStats }: { showStats: boolean }) {
  const navigate = useNavigate()

  // Widget visibility
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

  const showWidget = (w: DashWidget) => visibleWidgets.has(w)

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
      {/* Dashboard customize toggle */}
      <div className="flex justify-end">
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm">
              <SlidersHorizontal className="h-3.5 w-3.5 mr-1.5" /> Customize
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
      </div>

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
