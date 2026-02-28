import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { cn } from '@/lib/utils'
import {
  Plus, Search, LayoutGrid, LayoutDashboard, List,
  DollarSign, Target, AlertTriangle, FolderOpen,
  BarChart3, PieChart, Download,
  Archive, Trash2, RotateCcw, AlertCircle,
} from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
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

type MainTab = 'projects' | 'dashboard' | 'archived' | 'trash'

export default function Marketing() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('marketing_summary')
  const { filters, updateFilter, clearFilters, viewMode, setViewMode } = useMarketingStore()
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [mainTab, setMainTab] = useTabParam<MainTab>('dashboard')

  // Data queries
  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ['mkt-dashboard-summary'],
    queryFn: () => marketingApi.getDashboardSummary(),
  })
  const summary = summaryData?.summary

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
    <div className="space-y-6">
      <PageHeader
        title="Marketing"
        breadcrumbs={[
          { label: 'Marketing' },
          { label: mainTab === 'projects' ? `Campaigns (${total})` : mainTab === 'dashboard' ? 'Dashboard' : mainTab === 'archived' ? 'Archived' : 'Trash' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={toggleDashboardWidget}>
              <LayoutDashboard className="mr-1.5 h-3.5 w-3.5" />
              {isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}
            </Button>
            <Button onClick={() => setShowCreateDialog(true)}>
              <Plus className="h-4 w-4 mr-2" /> New Project
            </Button>
          </div>
        }
      />

      {/* Main Tabs */}
      <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
        <TabsList className="w-max md:w-auto">
          <TabsTrigger value="dashboard"><BarChart3 className="h-3.5 w-3.5" />Dashboard</TabsTrigger>
          <TabsTrigger value="projects"><FolderOpen className="h-3.5 w-3.5" />Campaigns</TabsTrigger>
          <TabsTrigger value="archived"><Archive className="h-3.5 w-3.5" />Archived</TabsTrigger>
          <TabsTrigger value="trash"><Trash2 className="h-3.5 w-3.5" />Trash</TabsTrigger>
        </TabsList>
        </div>
      </Tabs>

      {mainTab === 'projects' && (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              title="Active"
              value={summary?.active_count ?? 0}
              icon={<FolderOpen className="h-4 w-4" />}
              isLoading={summaryLoading}
            />
            <StatCard
              title="Total Budget"
              value={formatCurrency(summary?.total_budget)}
              icon={<DollarSign className="h-4 w-4" />}
              isLoading={summaryLoading}
            />
            <StatCard
              title="Total Spent"
              value={formatCurrency(summary?.total_spent)}
              icon={<Target className="h-4 w-4" />}
              isLoading={summaryLoading}
            />
            <StatCard
              title="KPI Alerts"
              value={summary?.kpi_alerts ?? 0}
              icon={<AlertTriangle className="h-4 w-4" />}
              isLoading={summaryLoading}
            />
          </div>

          {/* Filter Bar */}
          <div className="flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search projects..."
                className="pl-9"
                value={filters.search ?? ''}
                onChange={(e) => updateFilter('search', e.target.value || undefined)}
              />
            </div>

            <Select
              value={filters.status ?? 'all'}
              onValueChange={(v) => updateFilter('status', v === 'all' ? undefined : v)}
            >
              <SelectTrigger className="w-[160px]">
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
              <SelectTrigger className="w-[160px]">
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
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="All companies" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All companies</SelectItem>
                {companies.map((c: { id: number; company: string }) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {Object.values(filters).some((v) => v != null && v !== '' && v !== 50 && v !== 0) && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>Clear</Button>
            )}

            <div className="ml-auto flex gap-1">
              <Button
                variant={viewMode === 'table' ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => setViewMode('table')}
              >
                <List className="h-4 w-4" />
              </Button>
              <Button
                variant={viewMode === 'cards' ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => setViewMode('cards')}
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Project List */}
          {projectsError ? (
            <QueryError message="Failed to load projects" onRetry={() => refetchProjects()} />
          ) : projectsLoading ? (
            <TableSkeleton rows={6} columns={7} />
          ) : viewMode === 'table' ? (
            <ProjectTable
              projects={projects}
              onSelect={(p) => navigate(`/app/marketing/projects/${p.id}`)}
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
        </>
      )}

      {mainTab === 'dashboard' && <DashboardView />}



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


// ---- Table View ----

function ProjectTable({ projects, onSelect, onArchive, onDelete }: {
  projects: MktProject[]
  onSelect: (p: MktProject) => void
  onArchive?: (p: MktProject) => void
  onDelete?: (p: MktProject) => void
}) {
  if (!projects.length) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No projects found. Create your first marketing project.
      </div>
    )
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Project</TableHead>
            <TableHead>Company</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Status</TableHead>
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
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => onSelect(p)}
              >
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

function ProjectCards({ projects, onSelect, onArchive, onDelete }: {
  projects: MktProject[]
  onSelect: (p: MktProject) => void
  onArchive?: (p: MktProject) => void
  onDelete?: (p: MktProject) => void
}) {
  if (!projects.length) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No projects found. Create your first marketing project.
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
            className="rounded-lg border bg-card p-4 space-y-3 cursor-pointer hover:border-primary/50 transition-colors"
            onClick={() => onSelect(p)}
          >
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


// ---- Dashboard View ----

function DashboardView() {
  const navigate = useNavigate()

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
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard title="Active" value={summary?.active_count ?? 0} icon={<FolderOpen className="h-4 w-4" />} isLoading={summaryLoading} />
        <StatCard title="Draft" value={summary?.draft_count ?? 0} icon={<FolderOpen className="h-4 w-4" />} isLoading={summaryLoading} />
        <StatCard title="Total Budget" value={formatCurrency(summary?.total_budget)} icon={<DollarSign className="h-4 w-4" />} isLoading={summaryLoading} />
        <StatCard title="Total Spent" value={formatCurrency(summary?.total_spent)} icon={<Target className="h-4 w-4" />} isLoading={summaryLoading} />
        <StatCard title="KPI Alerts" value={summary?.kpi_alerts ?? 0} icon={<AlertTriangle className="h-4 w-4" />} isLoading={summaryLoading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Budget by Channel */}
        <div className="rounded-lg border p-4 space-y-4">
          <div className="flex items-center gap-2">
            <PieChart className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold text-sm">Budget by Channel</h3>
          </div>
          {budgetLoading ? (
            <TableSkeleton rows={4} columns={3} showHeader={false} />
          ) : channels.length === 0 ? (
            <div className="text-center py-6 text-sm text-muted-foreground">No budget data.</div>
          ) : (
            <div className="space-y-3">
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
        </div>

        {/* KPI Scoreboard — Matrix Grid */}
        <div className="rounded-lg border p-4 space-y-4">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-semibold text-sm">KPI Scoreboard (Active Projects)</h3>
          </div>
          {scoreboardLoading ? (
            <TableSkeleton rows={3} columns={5} />
          ) : kpis.length === 0 ? (
            <div className="text-center py-6 text-sm text-muted-foreground">No KPIs tracked.</div>
          ) : (
            <KpiMatrix kpis={kpis} onProjectClick={(id) => navigate(`/app/marketing/projects/${id}`)} />
          )}
        </div>
      </div>

      {/* Budget vs Actual Report */}
      <div className="rounded-lg border p-4 space-y-4">
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
          <div className="text-center py-6 text-sm text-muted-foreground">No project data.</div>
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
      </div>

      {/* Channel Performance Report */}
      <div className="rounded-lg border p-4 space-y-4">
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
          <div className="text-center py-6 text-sm text-muted-foreground">No channel data.</div>
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
      </div>
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
