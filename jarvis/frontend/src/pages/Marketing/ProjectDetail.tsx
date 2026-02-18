import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTabParam } from '@/hooks/useTabParam'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import {
  ArrowLeft, Pencil, Play, Pause, CheckCircle, Send, Copy, Check, RefreshCw,
  DollarSign, Target, Users, Clock, FileText, MessageSquare, ClipboardCheck,
  Plus, Trash2, BarChart3, CalendarDays, Link2, Search, Eye, Info, Loader2, X,
  ChevronDown, ChevronRight, Upload, Sparkles,
} from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import { usersApi } from '@/api/users'
import { settingsApi } from '@/api/settings'
import type { MktProject, MktBudgetLine, MktProjectKpi, MktKeyResult, HrEventSearchResult, InvoiceSearchResult, KpiBenchmarks } from '@/types/marketing'
import type { UserDetail } from '@/types/users'
import { approvalsApi } from '@/api/approvals'
import { ApprovalWidget } from '@/components/shared/ApprovalWidget'
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

function fmt(val: number | string | null | undefined, currency = 'RON') {
  const n = typeof val === 'string' ? parseFloat(val) : (val ?? 0)
  return `${n.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} ${currency}`
}

function fmtDate(d: string | null | undefined) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

function fmtDatetime(d: string | null | undefined) {
  if (!d) return '—'
  return new Date(d).toLocaleString('ro-RO', { dateStyle: 'medium', timeStyle: 'short' })
}

type Tab = 'overview' | 'budget' | 'kpis' | 'team' | 'events' | 'activity' | 'files' | 'comments'

const tabs: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: 'overview', label: 'Overview', icon: BarChart3 },
  { key: 'budget', label: 'Budget', icon: DollarSign },
  { key: 'kpis', label: 'KPIs', icon: Target },
  { key: 'team', label: 'Team', icon: Users },
  { key: 'events', label: 'Events', icon: CalendarDays },
  { key: 'activity', label: 'Activity', icon: Clock },
  { key: 'files', label: 'Files', icon: FileText },
  { key: 'comments', label: 'Comments', icon: MessageSquare },
]

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const id = Number(projectId)

  const [activeTab, setActiveTab] = useTabParam<Tab>('overview')
  const [showEditDialog, setShowEditDialog] = useState(false)

  const { data: project, isLoading } = useQuery({
    queryKey: ['mkt-project', id],
    queryFn: () => marketingApi.getProject(id),
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!project) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        Project not found.
        <Button variant="link" onClick={() => navigate('/app/marketing')}>Back to projects</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => navigate('/app/marketing')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h1 className="text-2xl font-bold truncate">{project.name}</h1>
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColors[project.status] ?? ''}`}>
              {(project.status ?? '').replace('_', ' ')}
            </span>
          </div>
          <p className="text-sm text-muted-foreground ml-9">
            {project.company_name}{project.brand_name ? ` / ${project.brand_name}` : ''}
            {' · '}
            {(project.project_type ?? '').replace('_', ' ')}
            {project.owner_name ? ` · Owner: ${project.owner_name}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={() => setShowEditDialog(true)}>
            <Pencil className="h-3.5 w-3.5 mr-1.5" /> Edit
          </Button>
          <StatusActions project={project} onDone={() => queryClient.invalidateQueries({ queryKey: ['mkt-project', id] })} />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 overflow-x-auto border-b">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                activeTab === tab.key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && <OverviewTab project={project} />}
      {activeTab === 'budget' && <BudgetTab projectId={id} currency={project.currency} />}
      {activeTab === 'kpis' && <KpisTab projectId={id} />}
      {activeTab === 'team' && <TeamTab projectId={id} />}
      {activeTab === 'events' && <EventsTab projectId={id} />}
      {activeTab === 'activity' && <ActivityTab projectId={id} />}
      {activeTab === 'files' && <FilesTab projectId={id} />}
      {activeTab === 'comments' && <CommentsTab projectId={id} />}

      {/* Edit Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Project</DialogTitle>
          </DialogHeader>
          <ProjectForm
            project={project}
            onSuccess={() => {
              setShowEditDialog(false)
              queryClient.invalidateQueries({ queryKey: ['mkt-project', id] })
              queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
            }}
            onCancel={() => setShowEditDialog(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  )
}


// ──────────────────────────────────────────
// Status Action Buttons
// ──────────────────────────────────────────

function StatusActions({ project, onDone }: { project: MktProject; onDone: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [submitOpen, setSubmitOpen] = useState(false)
  const [selectedApprover, setSelectedApprover] = useState<number | undefined>()
  const { data: membersData } = useQuery({ queryKey: ['mkt-members', project.id], queryFn: () => marketingApi.getMembers(project.id) })
  const stakeholders = (membersData?.members ?? []).filter((m) => m.role === 'stakeholder')
  const hasStakeholders = stakeholders.length > 0
  const { data: allUsers } = useQuery({ queryKey: ['users-list'], queryFn: () => usersApi.getUsers(), enabled: submitOpen && !hasStakeholders })
  const submitMut = useMutation({
    mutationFn: () => marketingApi.submitApproval(project.id, hasStakeholders ? undefined : selectedApprover),
    onSuccess: () => { setSubmitOpen(false); setSelectedApprover(undefined); onDone() },
  })
  const activateMut = useMutation({ mutationFn: () => marketingApi.activateProject(project.id), onSuccess: onDone })
  const pauseMut = useMutation({ mutationFn: () => marketingApi.pauseProject(project.id), onSuccess: onDone })
  const completeMut = useMutation({ mutationFn: () => marketingApi.completeProject(project.id), onSuccess: onDone })
  const dupMut = useMutation({
    mutationFn: () => marketingApi.duplicateProject(project.id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
      if (data?.id) navigate(`/app/marketing/projects/${data.id}`)
      else onDone()
    },
  })
  const deleteMut = useMutation({
    mutationFn: () => marketingApi.deleteProject(project.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-projects'] })
      navigate('/app/marketing')
    },
  })

  const s = project.status
  return (
    <div className="flex items-center gap-1.5">
      {(s === 'draft' || s === 'cancelled') && hasStakeholders ? (
        <Button size="sm" onClick={() => submitMut.mutate()} disabled={submitMut.isPending}>
          <Send className="h-3.5 w-3.5 mr-1.5" />
          {submitMut.isPending ? 'Submitting...' : `Submit (${stakeholders.length} stakeholder${stakeholders.length === 1 ? '' : 's'})`}
        </Button>
      ) : (s === 'draft' || s === 'cancelled') && (
        <Popover open={submitOpen} onOpenChange={(o) => { setSubmitOpen(o); if (!o) setSelectedApprover(undefined) }}>
          <PopoverTrigger asChild>
            <Button size="sm">
              <Send className="h-3.5 w-3.5 mr-1.5" /> Submit
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-3 space-y-2" align="end">
            <label className="text-xs font-medium text-muted-foreground">Select Approver</label>
            <select
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
              value={selectedApprover ?? ''}
              onChange={(e) => setSelectedApprover(e.target.value ? Number(e.target.value) : undefined)}
            >
              <option value="">Choose...</option>
              {(allUsers ?? []).map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
            <Button size="sm" className="w-full" disabled={!selectedApprover || submitMut.isPending} onClick={() => submitMut.mutate()}>
              {submitMut.isPending ? 'Submitting...' : 'Submit for Approval'}
            </Button>
          </PopoverContent>
        </Popover>
      )}
      {s === 'approved' && (
        <Button size="sm" onClick={() => activateMut.mutate()} disabled={activateMut.isPending}>
          <Play className="h-3.5 w-3.5 mr-1.5" /> Activate
        </Button>
      )}
      {s === 'active' && (
        <>
          <Button size="sm" variant="outline" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending}>
            <Pause className="h-3.5 w-3.5 mr-1.5" /> Pause
          </Button>
          <Button size="sm" onClick={() => completeMut.mutate()} disabled={completeMut.isPending}>
            <CheckCircle className="h-3.5 w-3.5 mr-1.5" /> Complete
          </Button>
        </>
      )}
      {s === 'paused' && (
        <>
          <Button size="sm" onClick={() => activateMut.mutate()} disabled={activateMut.isPending}>
            <Play className="h-3.5 w-3.5 mr-1.5" /> Resume
          </Button>
          <Button size="sm" variant="outline" onClick={() => completeMut.mutate()} disabled={completeMut.isPending}>
            <CheckCircle className="h-3.5 w-3.5 mr-1.5" /> Complete
          </Button>
        </>
      )}
      <Button size="sm" variant="ghost" onClick={() => dupMut.mutate()} disabled={dupMut.isPending}>
        <Copy className="h-3.5 w-3.5" />
      </Button>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &quot;{project.name}&quot; and all associated data (budget lines, KPIs, files, comments). This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteMut.mutate()}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}


// ──────────────────────────────────────────
// Overview Tab
// ──────────────────────────────────────────

function OverviewTab({ project }: { project: MktProject }) {
  const queryClient = useQueryClient()
  const budget = typeof project.total_budget === 'string' ? parseFloat(project.total_budget as string) : (project.total_budget ?? 0)
  const spent = typeof project.total_spent === 'string' ? parseFloat(project.total_spent as string) : (project.total_spent ?? 0)
  const burn = budget ? Math.round((spent / budget) * 100) : 0

  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState(project.description ?? '')

  const { data: kpisData } = useQuery({
    queryKey: ['mkt-project-kpis', project.id],
    queryFn: () => marketingApi.getProjectKpis(project.id),
  })
  const overviewKpis = (kpisData?.kpis ?? []).filter((k) => k.show_on_overview)

  const saveMut = useMutation({
    mutationFn: (desc: string) => marketingApi.updateProject(project.id, { description: desc }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project', project.id] })
      setEditingDesc(false)
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
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-lg font-bold">{fmt(budget, project.currency)}</div>
              <div className="text-xs text-muted-foreground">Total Budget</div>
            </div>
            <div>
              <div className="text-lg font-bold">{fmt(spent, project.currency)}</div>
              <div className="text-xs text-muted-foreground">Spent</div>
            </div>
            <div>
              <div className={`text-lg font-bold ${burn > 90 ? 'text-red-500' : burn > 70 ? 'text-yellow-500' : ''}`}>{burn}%</div>
              <div className="text-xs text-muted-foreground">Burn Rate</div>
            </div>
          </div>
          <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full ${burn > 90 ? 'bg-red-500' : burn > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
              style={{ width: `${Math.min(burn, 100)}%` }}
            />
          </div>
        </div>

        {/* KPI Overview — only KPIs marked show_on_overview */}
        {overviewKpis.length > 0 && (
          <div className="rounded-lg border p-4 space-y-3">
            <h3 className="font-semibold text-sm">Key Metrics</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {overviewKpis.map((k) => {
                const target = Number(k.target_value) || 0
                const current = Number(k.current_value) || 0
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
              <Textarea
                value={descDraft}
                onChange={(e) => setDescDraft(e.target.value)}
                placeholder="Add project details, goals, scope, notes..."
                rows={6}
                className="text-sm"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditingDesc(false)}>Cancel</Button>
                <Button size="sm" disabled={saveMut.isPending} onClick={() => saveMut.mutate(descDraft)}>
                  {saveMut.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {project.description || 'No description yet. Click Edit to add details.'}
            </p>
          )}
        </div>

        {/* Objective & Audience */}
        {project.objective && (
          <div className="space-y-1">
            <h3 className="font-semibold text-sm">Objective</h3>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{project.objective}</p>
          </div>
        )}
        {project.target_audience && (
          <div className="space-y-1">
            <h3 className="font-semibold text-sm">Target Audience</h3>
            <p className="text-sm text-muted-foreground">{project.target_audience}</p>
          </div>
        )}
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
          {project.external_ref && (
            <>
              <Separator />
              <div className="flex justify-between">
                <span className="text-muted-foreground">External Ref</span>
                <span>{project.external_ref}</span>
              </div>
            </>
          )}
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


// ──────────────────────────────────────────
// OKR Card (inline in Overview)
// ──────────────────────────────────────────

type SuggestedKr = { title: string; target_value: number; unit: string; linked_kpi_id: number | null }

function OkrCard({ projectId, kpis }: { projectId: number; kpis: MktProjectKpi[] }) {
  const queryClient = useQueryClient()
  const [collapsedIds, setCollapsedIds] = useState<Set<number>>(new Set())
  const [addingObjective, setAddingObjective] = useState(false)
  const [newObjTitle, setNewObjTitle] = useState('')
  const [editingObjId, setEditingObjId] = useState<number | null>(null)
  const [editObjTitle, setEditObjTitle] = useState('')
  const [addingKrForObj, setAddingKrForObj] = useState<number | null>(null)
  const [newKr, setNewKr] = useState({ title: '', target_value: '100', unit: 'number', linked_kpi_id: '' })
  const [editingKrId, setEditingKrId] = useState<number | null>(null)
  const [editKrValue, setEditKrValue] = useState('')
  const [suggestions, setSuggestions] = useState<Record<number, SuggestedKr[]>>({})

  const { data } = useQuery({
    queryKey: ['mkt-objectives', projectId],
    queryFn: () => marketingApi.getObjectives(projectId),
  })
  const objectives = data?.objectives ?? []

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['mkt-objectives', projectId] })

  const createObjMut = useMutation({
    mutationFn: (title: string) => marketingApi.createObjective(projectId, { title }),
    onSuccess: () => { invalidate(); setAddingObjective(false); setNewObjTitle('') },
  })
  const updateObjMut = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) => marketingApi.updateObjective(id, { title }),
    onSuccess: () => { invalidate(); setEditingObjId(null) },
  })
  const deleteObjMut = useMutation({
    mutationFn: (id: number) => marketingApi.deleteObjective(id),
    onSuccess: invalidate,
  })
  const createKrMut = useMutation({
    mutationFn: ({ objId, data: d }: { objId: number; data: { title: string; target_value: number; unit: string; linked_kpi_id?: number | null } }) =>
      marketingApi.createKeyResult(objId, d),
    onSuccess: () => { invalidate(); setAddingKrForObj(null); setNewKr({ title: '', target_value: '100', unit: 'number', linked_kpi_id: '' }) },
  })
  const updateKrMut = useMutation({
    mutationFn: ({ id, data: d }: { id: number; data: Partial<MktKeyResult> }) => marketingApi.updateKeyResult(id, d),
    onSuccess: () => { invalidate(); setEditingKrId(null) },
  })
  const deleteKrMut = useMutation({
    mutationFn: (id: number) => marketingApi.deleteKeyResult(id),
    onSuccess: invalidate,
  })
  const syncMut = useMutation({
    mutationFn: () => marketingApi.syncOkrKpis(projectId),
    onSuccess: invalidate,
  })
  const suggestMut = useMutation({
    mutationFn: (objectiveId: number) => marketingApi.suggestKeyResults(projectId, objectiveId),
    onSuccess: (data, objectiveId) => {
      setSuggestions((prev) => ({ ...prev, [objectiveId]: data.suggestions }))
    },
  })

  const acceptSuggestion = (objId: number, suggestion: SuggestedKr) => {
    createKrMut.mutate({ objId, data: suggestion })
    setSuggestions((prev) => {
      const remaining = (prev[objId] ?? []).filter((s) => s !== suggestion)
      if (remaining.length === 0) { const { [objId]: _, ...rest } = prev; return rest }
      return { ...prev, [objId]: remaining }
    })
  }

  const toggleExpand = (id: number) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const progressColor = (pct: number) =>
    pct >= 100 ? 'bg-green-500' : pct >= 70 ? 'bg-blue-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'

  const hasLinkedKpis = objectives.some((o) => o.key_results.some((kr) => kr.linked_kpi_id))
  const kpiMap = Object.fromEntries(kpis.map((k) => [k.id, k.kpi_name]))

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <h3 className="font-semibold text-sm">Objectives & Key Results</h3>
          <Popover>
            <PopoverTrigger asChild>
              <button className="text-muted-foreground hover:text-foreground">
                <Info className="h-3.5 w-3.5" />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-80 text-xs" side="right" align="start">
              <div className="space-y-2">
                <p className="font-semibold text-sm">OKR Examples</p>
                <div className="space-y-1.5 pl-3 border-l-2 border-muted">
                  <p className="font-medium">Objective: <span className="font-normal italic">"Increase brand awareness in Bucharest"</span></p>
                  <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                    <li>Reach 50,000 FB impressions (target: 50000, Number)</li>
                    <li>Get 500 page followers (target: 500, Number)</li>
                    <li>CTR above 3% (target: 3, Percentage — link to KPI)</li>
                  </ul>
                </div>
                <div className="space-y-1.5 pl-3 border-l-2 border-muted">
                  <p className="font-medium">Objective: <span className="font-normal italic">"Drive dealer traffic from digital"</span></p>
                  <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                    <li>Generate 200 qualified leads (target: 200, Number)</li>
                    <li>Cost per lead under 5,000 RON (target: 5000, Currency)</li>
                  </ul>
                </div>
                <p className="text-[10px] text-muted-foreground">Tip: Link key results to KPIs for auto-sync. Use the Sparkles button to get AI suggestions.</p>
              </div>
            </PopoverContent>
          </Popover>
        </div>
        <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setAddingObjective(true)}>
          <Plus className="h-3 w-3 mr-1" /> Add Objective
        </Button>
      </div>

      {objectives.length === 0 && !addingObjective && (
        <p className="text-sm text-muted-foreground">No objectives yet. Add one to start tracking OKRs.</p>
      )}

      <div className="space-y-2">
        {objectives.map((obj) => {
          const expanded = !collapsedIds.has(obj.id)
          const objSuggestions = suggestions[obj.id]
          return (
            <div key={obj.id} className="rounded-lg border">
              {/* Objective header */}
              <div
                className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-muted/50"
                onClick={() => toggleExpand(obj.id)}
              >
                {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
                {editingObjId === obj.id ? (
                  <Input
                    autoFocus
                    value={editObjTitle}
                    onChange={(e) => setEditObjTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && editObjTitle.trim()) updateObjMut.mutate({ id: obj.id, title: editObjTitle.trim() })
                      if (e.key === 'Escape') setEditingObjId(null)
                    }}
                    onBlur={() => { if (editObjTitle.trim() && editObjTitle.trim() !== obj.title) updateObjMut.mutate({ id: obj.id, title: editObjTitle.trim() }); else setEditingObjId(null) }}
                    onClick={(e) => e.stopPropagation()}
                    className="h-7 text-sm font-medium"
                  />
                ) : (
                  <span
                    className="text-sm font-medium flex-1 truncate"
                    onDoubleClick={(e) => { e.stopPropagation(); setEditingObjId(obj.id); setEditObjTitle(obj.title) }}
                  >
                    {obj.title}
                  </span>
                )}
                <span className="text-xs font-medium tabular-nums ml-auto shrink-0">{Math.round(obj.progress)}%</span>
                <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden shrink-0">
                  <div className={`h-full rounded-full ${progressColor(obj.progress)}`} style={{ width: `${Math.min(obj.progress, 100)}%` }} />
                </div>
                <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                  <Button
                    variant="ghost" size="sm" className="h-6 w-6 p-0"
                    title="AI Suggest Key Results"
                    disabled={suggestMut.isPending}
                    onClick={() => suggestMut.mutate(obj.id)}
                  >
                    {suggestMut.isPending && suggestMut.variables === obj.id
                      ? <Loader2 className="h-3 w-3 animate-spin" />
                      : <Sparkles className="h-3 w-3 text-amber-500" />}
                  </Button>
                  <Button
                    variant="ghost" size="sm" className="h-6 w-6 p-0"
                    onClick={() => { setEditingObjId(obj.id); setEditObjTitle(obj.title) }}
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-destructive hover:text-destructive">
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete Objective</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will delete the objective and all its key results. This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => deleteObjMut.mutate(obj.id)}>Delete</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>

              {/* Key Results */}
              {expanded && (
                <div className="px-3 pb-3 space-y-1.5">
                  {obj.key_results.map((kr) => (
                    <div key={kr.id} className="flex items-center gap-2 group">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 text-xs">
                          {kr.linked_kpi_id && <span title={`Linked to KPI: ${kr.linked_kpi_name}`}><Link2 className="h-3 w-3 text-blue-500 shrink-0" /></span>}
                          <span className="truncate text-muted-foreground">{kr.title}</span>
                          <span className="ml-auto tabular-nums font-medium shrink-0">
                            {editingKrId === kr.id ? (
                              <Input
                                autoFocus
                                type="number"
                                value={editKrValue}
                                onChange={(e) => setEditKrValue(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') { updateKrMut.mutate({ id: kr.id, data: { current_value: parseFloat(editKrValue) || 0 } }); setEditingKrId(null) }
                                  if (e.key === 'Escape') setEditingKrId(null)
                                }}
                                onBlur={() => { updateKrMut.mutate({ id: kr.id, data: { current_value: parseFloat(editKrValue) || 0 } }); setEditingKrId(null) }}
                                className="h-5 w-16 text-xs px-1 inline"
                                onClick={(e) => e.stopPropagation()}
                              />
                            ) : (
                              <button
                                className={cn('hover:underline', kr.linked_kpi_id ? 'cursor-default' : 'cursor-pointer')}
                                onClick={() => { if (!kr.linked_kpi_id) { setEditingKrId(kr.id); setEditKrValue(String(kr.current_value ?? 0)) } }}
                                disabled={!!kr.linked_kpi_id}
                                title={kr.linked_kpi_id ? 'Synced from KPI — click Sync to update' : 'Click to edit value'}
                              >
                                {Number(kr.current_value ?? 0).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}
                              </button>
                            )}
                            <span className="text-muted-foreground">/{Number(kr.target_value ?? 0).toLocaleString('ro-RO')}</span>
                            {kr.unit === 'percentage' && '%'}
                          </span>
                          <span className="text-[10px] tabular-nums w-8 text-right shrink-0">{Math.round(kr.progress)}%</span>
                        </div>
                        <div className="w-full h-1 rounded-full bg-muted overflow-hidden mt-0.5">
                          <div className={`h-full rounded-full ${progressColor(kr.progress)}`} style={{ width: `${Math.min(kr.progress, 100)}%` }} />
                        </div>
                      </div>
                      <Button
                        variant="ghost" size="sm"
                        className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive shrink-0"
                        onClick={() => deleteKrMut.mutate(kr.id)}
                      >
                        <Trash2 className="h-2.5 w-2.5" />
                      </Button>
                    </div>
                  ))}

                  {/* AI Suggestions */}
                  {objSuggestions && objSuggestions.length > 0 && (
                    <div className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20 p-2 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium flex items-center gap-1 text-amber-700 dark:text-amber-400">
                          <Sparkles className="h-3 w-3" /> AI Suggestions
                        </span>
                        <button className="text-muted-foreground hover:text-foreground" onClick={() => setSuggestions((prev) => { const { [obj.id]: _, ...rest } = prev; return rest })}>
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                      {objSuggestions.map((s, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <Button
                            variant="ghost" size="sm" className="h-5 w-5 p-0 shrink-0 text-green-600 hover:text-green-700"
                            onClick={() => acceptSuggestion(obj.id, s)}
                            title="Accept suggestion"
                          >
                            <Check className="h-3 w-3" />
                          </Button>
                          {s.linked_kpi_id && <span title={`Link to: ${kpiMap[s.linked_kpi_id] ?? 'KPI'}`}><Link2 className="h-3 w-3 text-blue-500 shrink-0" /></span>}
                          <span className="flex-1 truncate">{s.title}</span>
                          <span className="tabular-nums text-muted-foreground shrink-0">
                            {s.target_value.toLocaleString('ro-RO')} {s.unit === 'percentage' ? '%' : s.unit === 'currency' ? 'RON' : ''}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Add KR inline form */}
                  {addingKrForObj === obj.id ? (
                    <div className="space-y-2 pt-2 border-t">
                      <Input
                        autoFocus placeholder="Key result title" value={newKr.title}
                        onChange={(e) => setNewKr((p) => ({ ...p, title: e.target.value }))}
                        className="h-9 text-xs"
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') setAddingKrForObj(null)
                        }}
                      />
                      <div className="grid grid-cols-[80px_110px_1fr] gap-2">
                        <Input
                          type="number" placeholder="Target" value={newKr.target_value}
                          onChange={(e) => setNewKr((p) => ({ ...p, target_value: e.target.value }))}
                          className="h-9 text-xs"
                        />
                        <Select value={newKr.unit} onValueChange={(v) => setNewKr((p) => ({ ...p, unit: v }))}>
                          <SelectTrigger className="h-9 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="number">Number</SelectItem>
                            <SelectItem value="currency">Currency</SelectItem>
                            <SelectItem value="percentage">Percentage</SelectItem>
                          </SelectContent>
                        </Select>
                        <Select value={newKr.linked_kpi_id} onValueChange={(v) => setNewKr((p) => ({ ...p, linked_kpi_id: v }))}>
                          <SelectTrigger className="h-9 text-xs">
                            <SelectValue placeholder="Link KPI (optional)" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">No KPI link</SelectItem>
                            {kpis.map((k) => (
                              <SelectItem key={k.id} value={String(k.id)}>{k.kpi_name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex justify-end gap-1.5">
                        <Button variant="outline" size="sm" className="h-7 text-xs px-3" onClick={() => setAddingKrForObj(null)}>Cancel</Button>
                        <Button
                          size="sm" className="h-7 text-xs px-3"
                          disabled={!newKr.title.trim() || createKrMut.isPending}
                          onClick={() => {
                            const linkedId = newKr.linked_kpi_id && newKr.linked_kpi_id !== 'none' ? parseInt(newKr.linked_kpi_id) : null
                            createKrMut.mutate({
                              objId: obj.id,
                              data: { title: newKr.title.trim(), target_value: parseFloat(newKr.target_value) || 100, unit: newKr.unit, linked_kpi_id: linkedId },
                            })
                          }}
                        >
                          Add
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <button
                      className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 pt-1"
                      onClick={() => { setAddingKrForObj(obj.id); setNewKr({ title: '', target_value: '100', unit: 'number', linked_kpi_id: '' }) }}
                    >
                      <Plus className="h-3 w-3" /> Add Key Result
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Add Objective inline */}
      {addingObjective && (
        <div className="flex gap-2">
          <Input
            autoFocus placeholder="Objective title" value={newObjTitle}
            onChange={(e) => setNewObjTitle(e.target.value)}
            className="h-8 text-sm"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && newObjTitle.trim()) createObjMut.mutate(newObjTitle.trim())
              if (e.key === 'Escape') { setAddingObjective(false); setNewObjTitle('') }
            }}
          />
          <Button size="sm" className="h-8" disabled={!newObjTitle.trim() || createObjMut.isPending} onClick={() => createObjMut.mutate(newObjTitle.trim())}>
            Add
          </Button>
          <Button variant="outline" size="sm" className="h-8" onClick={() => { setAddingObjective(false); setNewObjTitle('') }}>
            Cancel
          </Button>
        </div>
      )}

      {/* Sync button */}
      {hasLinkedKpis && (
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => syncMut.mutate()} disabled={syncMut.isPending}>
          <RefreshCw className={cn('h-3 w-3 mr-1', syncMut.isPending && 'animate-spin')} />
          Sync KPI Values
        </Button>
      )}
    </div>
  )
}


// ──────────────────────────────────────────
// Budget Tab
// ──────────────────────────────────────────

function BudgetTab({ projectId, currency }: { projectId: number; currency: string }) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState({ channel: '', planned_amount: '', description: '', period_type: 'campaign' })
  const [linkLineId, setLinkLineId] = useState<number | null>(null)
  const [invoiceSearch, setInvoiceSearch] = useState('')
  const [invoiceResults, setInvoiceResults] = useState<InvoiceSearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [linkedInvoiceIds, setLinkedInvoiceIds] = useState<Set<number>>(new Set())
  const [spendLineId, setSpendLineId] = useState<number | null>(null)
  const [spendForm, setSpendForm] = useState({ amount: '', transaction_date: '', description: '' })
  const [expandedLineId, setExpandedLineId] = useState<number | null>(null)
  const [linkTxId, setLinkTxId] = useState<number | null>(null)
  const [txInvoiceSearch, setTxInvoiceSearch] = useState('')
  const [txInvoiceResults, setTxInvoiceResults] = useState<InvoiceSearchResult[]>([])
  const [isTxSearching, setIsTxSearching] = useState(false)
  const [editTxId, setEditTxId] = useState<number | null>(null)
  const [editTxForm, setEditTxForm] = useState({ amount: '', transaction_date: '', description: '' })

  const { data } = useQuery({
    queryKey: ['mkt-budget-lines', projectId],
    queryFn: () => marketingApi.getBudgetLines(projectId),
  })
  const lines = data?.budget_lines ?? []

  const { data: channelOpts } = useQuery({
    queryKey: ['dropdown-options', 'mkt_channel'],
    queryFn: () => settingsApi.getDropdownOptions('mkt_channel'),
  })

  const addMut = useMutation({
    mutationFn: (d: Record<string, unknown>) => marketingApi.createBudgetLine(projectId, d as Partial<MktBudgetLine>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      setShowAdd(false)
      setAddForm({ channel: '', planned_amount: '', description: '', period_type: 'campaign' })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (lineId: number) => marketingApi.deleteBudgetLine(projectId, lineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
    },
  })

  const spendMut = useMutation({
    mutationFn: () => marketingApi.createTransaction(spendLineId!, {
      amount: Number(spendForm.amount),
      transaction_date: spendForm.transaction_date,
      direction: 'debit',
      source: 'manual',
      description: spendForm.description || undefined,
    } as Record<string, unknown>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions'] })
      setSpendLineId(null)
      setSpendForm({ amount: '', transaction_date: '', description: '' })
    },
  })

  const linkInvoiceMut = useMutation({
    mutationFn: (inv: InvoiceSearchResult) => marketingApi.createTransaction(linkLineId!, {
      amount: inv.invoice_value,
      transaction_date: inv.invoice_date,
      direction: 'debit',
      source: 'invoice',
      invoice_id: inv.id,
      description: `${inv.supplier} #${inv.invoice_number}`,
    } as Record<string, unknown>),
    onSuccess: (_data, inv) => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions'] })
      setLinkedInvoiceIds((prev) => new Set(prev).add(inv.id))
    },
  })

  const { data: txData } = useQuery({
    queryKey: ['mkt-transactions', expandedLineId],
    queryFn: () => marketingApi.getTransactions(expandedLineId!),
    enabled: !!expandedLineId,
  })
  const transactions = txData?.transactions ?? []

  const deleteTxMut = useMutation({
    mutationFn: (txId: number) => marketingApi.deleteTransaction(txId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions', expandedLineId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
    },
  })

  const linkTxInvoiceMut = useMutation({
    mutationFn: ({ txId, invoiceId }: { txId: number; invoiceId: number | null }) =>
      marketingApi.linkTransactionInvoice(txId, invoiceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions', expandedLineId] })
      setLinkTxId(null)
      setTxInvoiceSearch('')
      setTxInvoiceResults([])
    },
  })

  const editTxMut = useMutation({
    mutationFn: () => marketingApi.updateTransaction(editTxId!, {
      amount: Number(editTxForm.amount),
      transaction_date: editTxForm.transaction_date,
      description: editTxForm.description || undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions', expandedLineId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      setEditTxId(null)
    },
  })

  async function searchTxInvoices(q: string) {
    setTxInvoiceSearch(q)
    if (q.length < 2) { setTxInvoiceResults([]); return }
    setIsTxSearching(true)
    try {
      const res = await marketingApi.searchInvoices(q)
      setTxInvoiceResults(res?.invoices ?? [])
    } catch { setTxInvoiceResults([]) }
    setIsTxSearching(false)
  }

  async function searchInvoices(q: string) {
    setInvoiceSearch(q)
    if (q.length < 2) { setInvoiceResults([]); return }
    setIsSearching(true)
    try {
      const res = await marketingApi.searchInvoices(q)
      setInvoiceResults(res?.invoices ?? [])
    } catch { setInvoiceResults([]) }
    setIsSearching(false)
  }

  const totalPlanned = lines.reduce((s, l) => s + (Number(l.planned_amount) || 0), 0)
  const totalApproved = lines.reduce((s, l) => s + (Number(l.approved_amount) || 0), 0)
  const totalSpent = lines.reduce((s, l) => s + (Number(l.spent_amount) || 0), 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-4 text-sm">
          <span>Planned: <strong>{fmt(totalPlanned, currency)}</strong></span>
          <span>Approved: <strong>{fmt(totalApproved, currency)}</strong></span>
          <span>Spent: <strong>{fmt(totalSpent, currency)}</strong></span>
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Line
        </Button>
      </div>

      {lines.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No budget lines yet.</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-6 px-2" />
                <TableHead>Channel</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Period</TableHead>
                <TableHead className="text-right">Planned</TableHead>
                <TableHead className="text-right">Approved</TableHead>
                <TableHead className="text-right">Spent</TableHead>
                <TableHead>Utilization</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => {
                const planned = Number(l.planned_amount) || 0
                const spent = Number(l.spent_amount) || 0
                const util = planned ? Math.round((spent / planned) * 100) : 0
                const isExpanded = expandedLineId === l.id
                return (
                  <>
                    <TableRow
                      key={l.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setExpandedLineId(isExpanded ? null : l.id)}
                    >
                      <TableCell className="w-6 px-2">
                        {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs">{(l.channel ?? '').replace('_', ' ')}</Badge>
                      </TableCell>
                      <TableCell className="text-sm max-w-[200px] truncate">{l.description || '—'}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{l.period_type}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{fmt(l.planned_amount, currency)}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{fmt(l.approved_amount, currency)}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{fmt(l.spent_amount, currency)}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="w-14 h-1.5 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full ${util > 90 ? 'bg-red-500' : util > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                              style={{ width: `${Math.min(util, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">{util}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="Record Spend"
                            onClick={() => { setSpendLineId(l.id); setSpendForm({ amount: '', transaction_date: new Date().toISOString().slice(0, 10), description: '' }) }}>
                            <DollarSign className="h-3.5 w-3.5 text-muted-foreground" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="Link Invoice"
                            onClick={() => { setLinkLineId(l.id); setInvoiceSearch(''); setInvoiceResults([]); setLinkedInvoiceIds(new Set()) }}>
                            <Link2 className="h-3.5 w-3.5 text-muted-foreground" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="Delete" onClick={() => deleteMut.mutate(l.id)}>
                            <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow key={`${l.id}-expand`} className="bg-muted/30 hover:bg-muted/30">
                        <TableCell colSpan={9} className="p-0">
                          <div className="px-6 py-3 space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Transactions</span>
                              <div className="flex gap-1.5">
                                <Button variant="outline" size="sm" className="h-7 text-xs"
                                  onClick={(e) => { e.stopPropagation(); setSpendLineId(l.id); setSpendForm({ amount: '', transaction_date: new Date().toISOString().slice(0, 10), description: '' }) }}>
                                  <DollarSign className="h-3 w-3 mr-1" /> Record Spend
                                </Button>
                                <Button variant="outline" size="sm" className="h-7 text-xs"
                                  onClick={(e) => { e.stopPropagation(); setLinkLineId(l.id); setInvoiceSearch(''); setInvoiceResults([]); setLinkedInvoiceIds(new Set()) }}>
                                  <Link2 className="h-3 w-3 mr-1" /> Link Invoice
                                </Button>
                              </div>
                            </div>
                            {transactions.length === 0 ? (
                              <div className="text-xs text-muted-foreground text-center py-3">No transactions recorded yet.</div>
                            ) : (
                              <div className="rounded-md border bg-background">
                                <Table>
                                  <TableHeader>
                                    <TableRow>
                                      <TableHead className="text-xs">Date</TableHead>
                                      <TableHead className="text-xs text-right">Amount</TableHead>
                                      <TableHead className="text-xs">Direction</TableHead>
                                      <TableHead className="text-xs">Source</TableHead>
                                      <TableHead className="text-xs">Description</TableHead>
                                      <TableHead className="text-xs">Invoice</TableHead>
                                      <TableHead className="text-xs">Recorded By</TableHead>
                                      <TableHead className="w-14" />
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {transactions.map((tx) => (
                                      <TableRow key={tx.id}>
                                        <TableCell className="text-xs">{fmtDate(tx.transaction_date)}</TableCell>
                                        <TableCell className="text-xs text-right tabular-nums font-medium">{fmt(tx.amount, currency)}</TableCell>
                                        <TableCell>
                                          <Badge variant="outline" className={cn('text-[10px]', tx.direction === 'debit' ? 'border-red-300 text-red-600' : 'border-green-300 text-green-600')}>
                                            {tx.direction}
                                          </Badge>
                                        </TableCell>
                                        <TableCell className="text-xs text-muted-foreground">{tx.source}</TableCell>
                                        <TableCell className="text-xs max-w-[200px] truncate">{tx.description || '—'}</TableCell>
                                        <TableCell className="text-xs">
                                          {tx.invoice_id ? (
                                            <div className="flex items-center gap-1">
                                              <Badge variant="secondary" className="text-[10px] gap-0.5 max-w-[160px]">
                                                <span className="truncate">{tx.invoice_supplier || ''} #{tx.invoice_number_ref || tx.invoice_id}</span>
                                                {tx.source !== 'invoice' && (
                                                  <button
                                                    className="ml-0.5 hover:text-destructive"
                                                    onClick={(e) => { e.stopPropagation(); linkTxInvoiceMut.mutate({ txId: tx.id, invoiceId: null }) }}
                                                  >
                                                    <Trash2 className="h-2.5 w-2.5" />
                                                  </button>
                                                )}
                                              </Badge>
                                            </div>
                                          ) : (
                                            <Button variant="ghost" size="sm" className="h-5 text-[10px] px-1.5 text-muted-foreground"
                                              onClick={(e) => { e.stopPropagation(); setLinkTxId(tx.id); setTxInvoiceSearch(''); setTxInvoiceResults([]) }}>
                                              <Link2 className="h-3 w-3 mr-0.5" /> Link
                                            </Button>
                                          )}
                                        </TableCell>
                                        <TableCell className="text-xs text-muted-foreground">{tx.recorded_by_name || '—'}</TableCell>
                                        <TableCell>
                                          <div className="flex items-center gap-0.5">
                                            {tx.source !== 'invoice' && (
                                              <Button variant="ghost" size="icon" className="h-6 w-6" title="Edit"
                                                onClick={(e) => {
                                                  e.stopPropagation()
                                                  setEditTxId(tx.id)
                                                  setEditTxForm({
                                                    amount: String(tx.amount),
                                                    transaction_date: tx.transaction_date?.slice(0, 10) || '',
                                                    description: tx.description || '',
                                                  })
                                                }}>
                                                <Pencil className="h-3 w-3 text-muted-foreground" />
                                              </Button>
                                            )}
                                            {!tx.invoice_id && (
                                              <Button variant="ghost" size="icon" className="h-6 w-6"
                                                onClick={(e) => { e.stopPropagation(); deleteTxMut.mutate(tx.id) }}>
                                                <Trash2 className="h-3 w-3 text-muted-foreground" />
                                              </Button>
                                            )}
                                          </div>
                                        </TableCell>
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                              </div>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Link Invoice Dialog */}
      <Dialog open={!!linkLineId} onOpenChange={(open) => { if (!open) setLinkLineId(null) }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Link Invoices to Budget Line</DialogTitle>
            {linkedInvoiceIds.size > 0 && (
              <p className="text-sm text-muted-foreground">{linkedInvoiceIds.size} invoice{linkedInvoiceIds.size > 1 ? 's' : ''} linked</p>
            )}
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search by supplier or invoice number..."
                value={invoiceSearch}
                onChange={(e) => searchInvoices(e.target.value)}
                autoFocus
              />
            </div>
            {isSearching && <div className="text-center text-xs text-muted-foreground py-2">Searching...</div>}
            {invoiceResults.length > 0 && (
              <div className="rounded-md border max-h-72 overflow-y-auto">
                <Table>
                  <TableHeader className="sticky top-0 bg-background z-10">
                    <TableRow>
                      <TableHead className="text-xs">Supplier</TableHead>
                      <TableHead className="text-xs">Invoice Number</TableHead>
                      <TableHead className="text-xs w-24">Date</TableHead>
                      <TableHead className="text-xs text-right w-28">Value</TableHead>
                      <TableHead className="w-16" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {invoiceResults.map((inv) => {
                      const alreadyLinked = linkedInvoiceIds.has(inv.id)
                      return (
                        <TableRow key={inv.id} className={alreadyLinked ? 'opacity-50' : ''}>
                          <TableCell className="text-xs max-w-[200px] truncate">{inv.supplier}</TableCell>
                          <TableCell className="text-xs font-mono">{inv.invoice_number}</TableCell>
                          <TableCell className="text-xs">{fmtDate(inv.invoice_date)}</TableCell>
                          <TableCell className="text-right text-xs tabular-nums">{fmt(inv.invoice_value, inv.currency)}</TableCell>
                          <TableCell className="text-right">
                            {alreadyLinked ? (
                              <Check className="h-4 w-4 text-green-500 ml-auto" />
                            ) : (
                              <Button size="sm" variant="outline" className="h-6 text-xs px-2"
                                disabled={linkInvoiceMut.isPending}
                                onClick={() => linkInvoiceMut.mutate(inv)}>
                                Link
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
            {invoiceSearch.length >= 2 && !isSearching && invoiceResults.length === 0 && (
              <div className="text-center text-xs text-muted-foreground py-4">No invoices found.</div>
            )}
          </div>
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={() => setLinkLineId(null)}>Done</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Link Invoice to Transaction Dialog */}
      <Dialog open={!!linkTxId} onOpenChange={(open) => { if (!open) { setLinkTxId(null); setTxInvoiceSearch(''); setTxInvoiceResults([]) } }}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Link Invoice to Transaction</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search by supplier or invoice number..."
                value={txInvoiceSearch}
                onChange={(e) => searchTxInvoices(e.target.value)}
                autoFocus
              />
            </div>
            {isTxSearching && <div className="text-center text-xs text-muted-foreground py-2">Searching...</div>}
            {txInvoiceResults.length > 0 && (
              <div className="rounded-md border max-h-72 overflow-y-auto">
                <Table>
                  <TableHeader className="sticky top-0 bg-background z-10">
                    <TableRow>
                      <TableHead className="text-xs min-w-[180px]">Supplier</TableHead>
                      <TableHead className="text-xs min-w-[180px]">Invoice Number</TableHead>
                      <TableHead className="text-xs w-28">Date</TableHead>
                      <TableHead className="text-xs text-right w-28">Value</TableHead>
                      <TableHead className="w-14" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {txInvoiceResults.map((inv) => (
                      <TableRow key={inv.id}>
                        <TableCell className="text-xs">{inv.supplier}</TableCell>
                        <TableCell className="text-xs font-mono">{inv.invoice_number}</TableCell>
                        <TableCell className="text-xs">{fmtDate(inv.invoice_date)}</TableCell>
                        <TableCell className="text-right text-xs tabular-nums whitespace-nowrap">{fmt(inv.invoice_value, inv.currency)}</TableCell>
                        <TableCell className="text-right">
                          <Button size="sm" variant="outline" className="h-6 text-xs px-2"
                            disabled={linkTxInvoiceMut.isPending}
                            onClick={() => linkTxInvoiceMut.mutate({ txId: linkTxId!, invoiceId: inv.id })}>
                            Link
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {txInvoiceSearch.length >= 2 && !isTxSearching && txInvoiceResults.length === 0 && (
              <div className="text-center text-xs text-muted-foreground py-4">No invoices found.</div>
            )}
          </div>
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={() => { setLinkTxId(null); setTxInvoiceSearch(''); setTxInvoiceResults([]) }}>Cancel</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Transaction Dialog */}
      <Dialog open={!!editTxId} onOpenChange={(open) => { if (!open) setEditTxId(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Edit Transaction</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Amount *</Label>
              <Input type="number" value={editTxForm.amount} onChange={(e) => setEditTxForm((f) => ({ ...f, amount: e.target.value }))} autoFocus />
            </div>
            <div className="space-y-1.5">
              <Label>Date *</Label>
              <Input type="date" value={editTxForm.transaction_date} onChange={(e) => setEditTxForm((f) => ({ ...f, transaction_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Input value={editTxForm.description} onChange={(e) => setEditTxForm((f) => ({ ...f, description: e.target.value }))} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setEditTxId(null)}>Cancel</Button>
              <Button
                disabled={!editTxForm.amount || !editTxForm.transaction_date || editTxMut.isPending}
                onClick={() => editTxMut.mutate()}
              >
                {editTxMut.isPending ? 'Saving...' : 'Save'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Record Spend Dialog */}
      <Dialog open={!!spendLineId} onOpenChange={(open) => { if (!open) setSpendLineId(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Record Spend</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Amount *</Label>
              <Input type="number" value={spendForm.amount} onChange={(e) => setSpendForm((f) => ({ ...f, amount: e.target.value }))} autoFocus placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label>Date *</Label>
              <Input type="date" value={spendForm.transaction_date} onChange={(e) => setSpendForm((f) => ({ ...f, transaction_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Input value={spendForm.description} onChange={(e) => setSpendForm((f) => ({ ...f, description: e.target.value }))} placeholder="e.g., Agency fee Q1" />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setSpendLineId(null)}>Cancel</Button>
              <Button
                disabled={!spendForm.amount || !spendForm.transaction_date || spendMut.isPending}
                onClick={() => spendMut.mutate()}
              >
                {spendMut.isPending ? 'Saving...' : 'Record'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Budget Line Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Budget Line</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Channel *</Label>
              <Select value={addForm.channel} onValueChange={(v) => setAddForm((f) => ({ ...f, channel: v }))}>
                <SelectTrigger><SelectValue placeholder="Select channel" /></SelectTrigger>
                <SelectContent>
                  {(channelOpts ?? []).map((o: { value: string; label: string }) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Planned Amount</Label>
              <Input
                type="number"
                value={addForm.planned_amount}
                onChange={(e) => setAddForm((f) => ({ ...f, planned_amount: e.target.value }))}
                placeholder="0"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Input
                value={addForm.description}
                onChange={(e) => setAddForm((f) => ({ ...f, description: e.target.value }))}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button
                disabled={!addForm.channel || addMut.isPending}
                onClick={() => addMut.mutate({
                  channel: addForm.channel,
                  planned_amount: Number(addForm.planned_amount) || 0,
                  description: addForm.description || undefined,
                  period_type: addForm.period_type,
                  currency,
                })}
              >
                {addMut.isPending ? 'Adding...' : 'Add'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}


// ──────────────────────────────────────────
// KPIs Tab
// ──────────────────────────────────────────

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

function KpisTab({ projectId }: { projectId: number }) {
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

  // Budget lines linked to the KPI being edited
  const { data: kpiBLData } = useQuery({
    queryKey: ['mkt-kpi-budget-lines', linkSourcesKpiId],
    queryFn: () => marketingApi.getKpiBudgetLines(linkSourcesKpiId!),
    enabled: !!linkSourcesKpiId,
  })
  const linkedBudgetLines = kpiBLData?.budget_lines ?? []
  const linkedBLIds = new Set(linkedBudgetLines.map((l) => l.budget_line_id))

  // KPI dependencies for the KPI being edited
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
        <DialogContent className="max-w-sm">
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
            {/* Benchmark hint / generate */}
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
              // No benchmarks yet — offer to generate
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
        <DialogContent className="max-w-sm">
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
        <DialogContent className="max-w-lg">
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
        <DialogContent className="max-w-lg">
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
                        {/* Currently linked sources for this variable */}
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
                        {/* Add source buttons */}
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
  // Direction-aware progress: for "lower is better", invert (target/current)
  const pct = target
    ? Math.round(isLowerBetter ? (target / Math.max(current, 0.01)) * 100 : (current / target) * 100)
    : 0
  const warn = Number(k.threshold_warning) || 0
  const crit = Number(k.threshold_critical) || 0
  // Direction-aware thresholds
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
      {/* Benchmark indicator */}
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
      {/* Link indicators */}
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

  // Y-axis labels
  const ySteps = [min, min + range * 0.5, max]

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="text-foreground">
      {/* Grid lines */}
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
      {/* Area fill */}
      <polygon points={fill} fill="currentColor" fillOpacity={0.08} className="text-blue-500" />
      {/* Line */}
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="text-blue-500" />
      {/* Dots */}
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill="currentColor" className="text-blue-500" />
      ))}
      {/* Date labels (first and last) */}
      <text x={pad.l} y={h - 2} className="fill-muted-foreground" fontSize={9}>
        {new Date(values[0].date).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' })}
      </text>
      <text x={w - pad.r} y={h - 2} textAnchor="end" className="fill-muted-foreground" fontSize={9}>
        {new Date(values[values.length - 1].date).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' })}
      </text>
    </svg>
  )
}


// ──────────────────────────────────────────
// Team Tab
// ──────────────────────────────────────────

function TeamTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [addUserId, setAddUserId] = useState('')
  const [addRole, setAddRole] = useState('')

  const { data } = useQuery({
    queryKey: ['mkt-members', projectId],
    queryFn: () => marketingApi.getMembers(projectId),
  })
  const members = data?.members ?? []

  const PROJECT_ROLES = [
    { value: 'stakeholder', label: 'Stakeholder' },
    { value: 'observer', label: 'Observer' },
    { value: 'owner', label: 'Owner' },
    { value: 'manager', label: 'Manager' },
    { value: 'specialist', label: 'Specialist' },
    { value: 'viewer', label: 'Viewer' },
    { value: 'agency', label: 'Agency' },
  ]

  const { data: usersData } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    enabled: showAdd,
  })
  const users: UserDetail[] = (usersData as UserDetail[] | undefined) ?? []
  const existingUserIds = new Set(members.map((m) => m.user_id))

  const addMut = useMutation({
    mutationFn: () => marketingApi.addMember(projectId, { user_id: Number(addUserId), role: addRole }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-members', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      setShowAdd(false)
      setAddUserId('')
    },
  })

  const removeMut = useMutation({
    mutationFn: (memberId: number) => marketingApi.removeMember(projectId, memberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-members', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
    },
  })

  const updateRoleMut = useMutation({
    mutationFn: ({ memberId, role }: { memberId: number; role: string }) =>
      marketingApi.updateMember(projectId, memberId, { role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-members', projectId] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Member
        </Button>
      </div>

      {members.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No team members.</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Added</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">{m.user_name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{m.user_email}</TableCell>
                  <TableCell>
                    <Select
                      value={m.role}
                      onValueChange={(v) => updateRoleMut.mutate({ memberId: m.id, role: v })}
                    >
                      <SelectTrigger className="w-[120px] h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PROJECT_ROLES.map((r) => (
                          <SelectItem key={r.value} value={r.value} className="text-xs">{r.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtDate(m.created_at)}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => removeMut.mutate(m.id)}>
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Add Member Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Add Team Member</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>User *</Label>
              <Select value={addUserId} onValueChange={setAddUserId}>
                <SelectTrigger><SelectValue placeholder="Select user" /></SelectTrigger>
                <SelectContent>
                  {users.filter((u) => u.is_active && !existingUserIds.has(u.id)).map((u) => (
                    <SelectItem key={u.id} value={String(u.id)}>{u.name} ({u.role_name})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Role</Label>
              <Select value={addRole} onValueChange={setAddRole}>
                <SelectTrigger><SelectValue placeholder="Select role" /></SelectTrigger>
                <SelectContent>
                  {PROJECT_ROLES.map((r) => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button disabled={!addUserId || !addRole || addMut.isPending} onClick={() => addMut.mutate()}>
                {addMut.isPending ? 'Adding...' : 'Add'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}


// ──────────────────────────────────────────
// Events Tab (HR Events linked to project)
// ──────────────────────────────────────────

function EventsTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [eventSearch, setEventSearch] = useState('')
  const [eventResults, setEventResults] = useState<HrEventSearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)

  const { data } = useQuery({
    queryKey: ['mkt-project-events', projectId],
    queryFn: () => marketingApi.getProjectEvents(projectId),
  })
  const events = data?.events ?? []

  const linkMut = useMutation({
    mutationFn: (eventId: number) => marketingApi.linkEvent(projectId, eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-events', projectId] })
      setShowLink(false)
      setEventSearch('')
      setEventResults([])
    },
  })

  const unlinkMut = useMutation({
    mutationFn: (eventId: number) => marketingApi.unlinkEvent(projectId, eventId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-project-events', projectId] }),
  })

  async function searchEvents(q: string) {
    setEventSearch(q)
    if (q.length < 2) { setEventResults([]); return }
    setIsSearching(true)
    try {
      const res = await marketingApi.searchHrEvents(q)
      setEventResults(res?.events ?? [])
    } catch { setEventResults([]) }
    setIsSearching(false)
  }

  const linkedIds = new Set(events.map((e) => e.event_id))

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => { setShowLink(true); setEventSearch(''); setEventResults([]) }}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Link Event
        </Button>
      </div>

      {events.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No HR events linked.</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Start</TableHead>
                <TableHead>End</TableHead>
                <TableHead>Linked By</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>
                    <div>
                      <div className="text-sm font-medium">{e.event_name}</div>
                      {e.event_description && (
                        <div className="text-xs text-muted-foreground truncate max-w-[250px]">{e.event_description}</div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{e.event_company ?? '—'}</TableCell>
                  <TableCell className="text-sm">{fmtDate(e.event_start_date)}</TableCell>
                  <TableCell className="text-sm">{fmtDate(e.event_end_date)}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{e.linked_by_name}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => unlinkMut.mutate(e.event_id)}>
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Link Event Dialog */}
      <Dialog open={showLink} onOpenChange={setShowLink}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Link HR Event</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search events by name, company..."
                value={eventSearch}
                onChange={(e) => searchEvents(e.target.value)}
                autoFocus
              />
            </div>
            {isSearching && <div className="text-center text-sm text-muted-foreground py-2">Searching...</div>}
            {eventResults.length > 0 && (
              <div className="rounded-md border max-h-64 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Event</TableHead>
                      <TableHead>Company</TableHead>
                      <TableHead>Dates</TableHead>
                      <TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {eventResults.map((ev) => (
                      <TableRow key={ev.id}>
                        <TableCell>
                          <div className="text-sm font-medium">{ev.name}</div>
                          {ev.description && <div className="text-xs text-muted-foreground truncate max-w-[200px]">{ev.description}</div>}
                        </TableCell>
                        <TableCell className="text-sm">{ev.company ?? '—'}</TableCell>
                        <TableCell className="text-sm">{fmtDate(ev.start_date)} — {fmtDate(ev.end_date)}</TableCell>
                        <TableCell>
                          {linkedIds.has(ev.id) ? (
                            <Badge variant="secondary" className="text-xs">Linked</Badge>
                          ) : (
                            <Button size="sm" variant="outline" className="h-7"
                              disabled={linkMut.isPending}
                              onClick={() => linkMut.mutate(ev.id)}>
                              Link
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {eventSearch.length >= 2 && !isSearching && eventResults.length === 0 && (
              <div className="text-center text-sm text-muted-foreground py-4">No events found.</div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}


// ──────────────────────────────────────────
// Activity Tab
// ──────────────────────────────────────────

function ActivityTab({ projectId }: { projectId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['mkt-activity', projectId],
    queryFn: () => marketingApi.getActivity(projectId, 100),
  })
  const items = data?.activity ?? []

  if (isLoading) return <Skeleton className="h-32 w-full" />

  return (
    <div className="space-y-1">
      {items.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No activity yet.</div>
      ) : (
        <div className="space-y-0">
          {items.map((a) => (
            <div key={a.id} className="flex items-start gap-3 py-2.5 border-b last:border-0">
              <div className="mt-0.5 h-2 w-2 rounded-full bg-primary shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{a.actor_name ?? 'System'}</span>
                  <span className="text-sm text-muted-foreground">{a.action.replace('_', ' ')}</span>
                </div>
                {a.details && Object.keys(a.details).length > 0 && (
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {Object.entries(a.details).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                  </div>
                )}
              </div>
              <span className="text-xs text-muted-foreground shrink-0">{fmtDatetime(a.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// ──────────────────────────────────────────
// Files Tab
// ──────────────────────────────────────────

function FilesTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [showUpload, setShowUpload] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileDesc, setFileDesc] = useState('')
  const [isDragging, setIsDragging] = useState(false)

  const { data } = useQuery({
    queryKey: ['mkt-files', projectId],
    queryFn: () => marketingApi.getFiles(projectId),
  })
  const files = data?.files ?? []

  const uploadMut = useMutation({
    mutationFn: () => marketingApi.uploadFile(projectId, selectedFile!, fileDesc || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-files', projectId] })
      setShowUpload(false)
      setSelectedFile(null)
      setFileDesc('')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (fileId: number) => marketingApi.deleteFile(fileId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-files', projectId] }),
  })

  function fileIcon(name: string) {
    const ext = name.split('.').pop()?.toLowerCase() ?? ''
    if (['pdf'].includes(ext)) return 'PDF'
    if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) return 'IMG'
    if (['doc', 'docx'].includes(ext)) return 'DOC'
    if (['xls', 'xlsx'].includes(ext)) return 'XLS'
    if (['ppt', 'pptx'].includes(ext)) return 'PPT'
    return 'FILE'
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) { setSelectedFile(f); setShowUpload(true) }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) { setSelectedFile(f); setShowUpload(true) }
  }

  const ACCEPT = '.pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx,.ppt,.pptx'

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        className={cn(
          'rounded-lg border-2 border-dashed p-6 text-center transition-colors cursor-pointer',
          isDragging ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/20' : 'border-muted-foreground/25 hover:border-muted-foreground/50',
        )}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('mkt-file-input')?.click()}
      >
        <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
        <div className="text-sm text-muted-foreground">
          Drag & drop a file here, or <span className="text-blue-600 underline">browse</span>
        </div>
        <div className="text-xs text-muted-foreground mt-1">PDF, images, Office documents — max 10 MB</div>
        <input id="mkt-file-input" type="file" accept={ACCEPT} className="hidden" onChange={handleFileSelect} />
      </div>

      {files.length === 0 ? (
        <div className="text-center py-4 text-muted-foreground text-sm">No files attached yet.</div>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <div key={f.id} className="flex items-center gap-3 rounded-lg border p-3">
              <div className="flex h-10 w-10 items-center justify-center rounded bg-muted text-xs font-bold text-muted-foreground">
                {fileIcon(f.file_name)}
              </div>
              <div className="min-w-0 flex-1">
                <a
                  href={f.storage_uri}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium truncate block hover:underline text-blue-600 dark:text-blue-400"
                >
                  {f.file_name}
                </a>
                <div className="text-xs text-muted-foreground">
                  {f.uploaded_by_name ?? 'Unknown'} · {fmtDate(f.created_at)}
                  {f.file_size ? ` · ${(f.file_size / 1024).toFixed(0)} KB` : ''}
                </div>
                {f.description && <div className="text-xs text-muted-foreground mt-0.5">{f.description}</div>}
              </div>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => deleteMut.mutate(f.id)}>
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Upload Confirmation Dialog */}
      <Dialog open={showUpload} onOpenChange={(open) => { if (!open) { setShowUpload(false); setSelectedFile(null); setFileDesc('') } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Upload to Google Drive</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {selectedFile && (
              <div className="rounded-md border p-3 bg-muted/30">
                <div className="text-sm font-medium truncate">{selectedFile.name}</div>
                <div className="text-xs text-muted-foreground">{(selectedFile.size / 1024).toFixed(0)} KB</div>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Description (optional)</Label>
              <Input value={fileDesc} onChange={(e) => setFileDesc(e.target.value)} placeholder="e.g., Campaign brief Q1" />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { setShowUpload(false); setSelectedFile(null); setFileDesc('') }}>Cancel</Button>
              <Button disabled={!selectedFile || uploadMut.isPending} onClick={() => uploadMut.mutate()}>
                <Upload className="h-3.5 w-3.5 mr-1.5" />
                {uploadMut.isPending ? 'Uploading...' : 'Upload'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}


// ──────────────────────────────────────────
// Comments Tab
// ──────────────────────────────────────────

function CommentsTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [newComment, setNewComment] = useState('')
  const [isInternal, setIsInternal] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editContent, setEditContent] = useState('')

  const { data } = useQuery({
    queryKey: ['mkt-comments', projectId],
    queryFn: () => marketingApi.getComments(projectId, true),
  })
  const comments = data?.comments ?? []

  // Fetch approval history to show decision comments
  const { data: approvalHistory } = useQuery({
    queryKey: ['approval-entity-history', 'mkt_project', projectId],
    queryFn: () => approvalsApi.getEntityHistory('mkt_project', projectId),
  })

  // Build unified timeline: project comments + approval decisions with comments
  type TimelineItem =
    | { kind: 'comment'; data: (typeof comments)[0] }
    | { kind: 'decision'; data: { id: string; user_name: string; decision: string; comment: string; decided_at: string; step_name?: string } }

  const timeline: TimelineItem[] = []
  for (const c of comments) {
    timeline.push({ kind: 'comment', data: c })
  }
  for (const req of approvalHistory?.history ?? []) {
    for (const d of req.decisions ?? []) {
      if (d.comment) {
        timeline.push({
          kind: 'decision',
          data: {
            id: `decision-${d.id}`,
            user_name: d.decided_by?.name ?? 'Unknown',
            decision: d.decision,
            comment: d.comment,
            decided_at: d.decided_at ?? '',
            step_name: d.step_name ?? undefined,
          },
        })
      }
    }
  }
  timeline.sort((a, b) => {
    const da = a.kind === 'comment' ? a.data.created_at : a.data.decided_at
    const db = b.kind === 'comment' ? b.data.created_at : b.data.decided_at
    return new Date(db).getTime() - new Date(da).getTime()
  })

  const decisionColors: Record<string, string> = {
    approved: 'border-green-300 bg-green-50/50 dark:border-green-800 dark:bg-green-950/20',
    rejected: 'border-red-300 bg-red-50/50 dark:border-red-800 dark:bg-red-950/20',
    returned: 'border-orange-300 bg-orange-50/50 dark:border-orange-800 dark:bg-orange-950/20',
  }
  const decisionBadgeColors: Record<string, string> = {
    approved: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    rejected: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    returned: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  }

  const addMut = useMutation({
    mutationFn: () => marketingApi.createComment(projectId, { content: newComment, is_internal: isInternal }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-comments', projectId] })
      setNewComment('')
    },
  })

  const updateMut = useMutation({
    mutationFn: () => marketingApi.updateComment(editingId!, { content: editContent }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-comments', projectId] })
      setEditingId(null)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => marketingApi.deleteComment(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-comments', projectId] }),
  })

  return (
    <div className="space-y-4">
      {/* New comment */}
      <div className="space-y-2">
        <Textarea
          placeholder="Write a comment..."
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          rows={3}
        />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isInternal}
              onChange={(e) => setIsInternal(e.target.checked)}
              className="rounded"
            />
            Internal note
          </label>
          <Button
            size="sm"
            disabled={!newComment.trim() || addMut.isPending}
            onClick={() => addMut.mutate()}
          >
            {addMut.isPending ? 'Posting...' : 'Post'}
          </Button>
        </div>
      </div>

      <Separator />

      {/* Unified timeline */}
      {timeline.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No comments yet.</div>
      ) : (
        <div className="space-y-4">
          {timeline.map((item) => {
            if (item.kind === 'decision') {
              const d = item.data
              return (
                <div key={d.id} className={cn('rounded-lg border p-3 space-y-2', decisionColors[d.decision] ?? '')}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <ClipboardCheck className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className="text-sm font-medium">{d.user_name}</span>
                    <Badge className={cn('text-[10px] h-5 px-1.5', decisionBadgeColors[d.decision] ?? '')}>
                      {d.decision}
                    </Badge>
                    {d.step_name && <span className="text-xs text-muted-foreground">Step: {d.step_name}</span>}
                    <span className="text-xs text-muted-foreground ml-auto">{fmtDatetime(d.decided_at)}</span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{d.comment}</p>
                </div>
              )
            }
            const c = item.data
            return (
              <div key={c.id} className={cn('rounded-lg border p-3 space-y-2', c.is_internal && 'border-yellow-300 bg-yellow-50/50 dark:bg-yellow-900/10')}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{c.user_name}</span>
                    <span className="text-xs text-muted-foreground">{fmtDatetime(c.created_at)}</span>
                    {c.is_internal && <Badge variant="outline" className="text-xs text-yellow-600">Internal</Badge>}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={() => { setEditingId(c.id); setEditContent(c.content) }}
                    >
                      <Pencil className="h-3 w-3 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => deleteMut.mutate(c.id)}>
                      <Trash2 className="h-3 w-3 text-muted-foreground" />
                    </Button>
                  </div>
                </div>
                {editingId === c.id ? (
                  <div className="space-y-2">
                    <Textarea value={editContent} onChange={(e) => setEditContent(e.target.value)} rows={2} />
                    <div className="flex justify-end gap-2">
                      <Button variant="outline" size="sm" onClick={() => setEditingId(null)}>Cancel</Button>
                      <Button size="sm" disabled={!editContent.trim() || updateMut.isPending} onClick={() => updateMut.mutate()}>
                        Save
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm whitespace-pre-wrap">{c.content}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
