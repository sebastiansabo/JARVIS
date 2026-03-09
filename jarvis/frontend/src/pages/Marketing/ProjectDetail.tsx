import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTabParam } from '@/hooks/useTabParam'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PageHeader } from '@/components/shared/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Pencil, BarChart3, DollarSign, Target, Users,
  PartyPopper, Clock, FileText, MessageSquare, Download, Plus,
} from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import { exportProjectPdf } from './exportProjectPdf'
import ProjectForm from './ProjectForm'
import {
  StatusActions, OverviewTab, BudgetTab, KpisTab, TeamTab,
  EventsTab, ActivityTab, FilesTab, CommentsTab, statusColors,
} from './tabs'

type Tab = 'overview' | 'budget' | 'kpis' | 'team' | 'events' | 'activity' | 'files' | 'comments'

const tabs: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: 'overview', label: 'Overview', icon: BarChart3 },
  { key: 'budget', label: 'Budget', icon: DollarSign },
  { key: 'kpis', label: 'KPIs', icon: Target },
  { key: 'team', label: 'Team', icon: Users },
  { key: 'events', label: 'Events', icon: PartyPopper },
  { key: 'files', label: 'Files', icon: FileText },
  { key: 'comments', label: 'Comments', icon: MessageSquare },
  { key: 'activity', label: 'Activity', icon: Clock },
]

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const id = Number(projectId)

  const [activeTab, setActiveTab] = useTabParam<Tab>('overview')
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showQuickSpend, setShowQuickSpend] = useState(false)
  const [spendLineId, setSpendLineId] = useState('')
  const [spendAmount, setSpendAmount] = useState('')
  const [spendDate, setSpendDate] = useState(new Date().toISOString().slice(0, 10))
  const [spendDesc, setSpendDesc] = useState('')

  const { data: project, isLoading } = useQuery({
    queryKey: ['mkt-project', id],
    queryFn: () => marketingApi.getProject(id),
    enabled: !!id,
  })

  const { data: blData } = useQuery({
    queryKey: ['mkt-budget-lines', id],
    queryFn: () => marketingApi.getBudgetLines(id),
    enabled: !!id,
  })
  const budgetLines = blData?.budget_lines ?? []

  const spendMut = useMutation({
    mutationFn: (data: { lineId: number; amount: number; date: string; desc: string }) =>
      marketingApi.createTransaction(data.lineId, {
        amount: data.amount,
        direction: 'debit',
        source: 'manual',
        transaction_date: data.date,
        description: data.desc || undefined,
      } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', id] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', id] })
      setShowQuickSpend(false)
      setSpendLineId('')
      setSpendAmount('')
      setSpendDesc('')
    },
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
      <PageHeader
        title={project.name}
        breadcrumbs={[
          { label: 'Marketing', shortLabel: 'Mkt.', href: '/app/marketing' },
          { label: 'Campaigns', shortLabel: 'Camp.', href: '/app/marketing?tab=projects' },
          { label: project.name },
        ]}
        description={
          <span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium mr-2 ${statusColors[project.status] ?? ''}`}>
              {(project.status ?? '').replace('_', ' ')}
            </span>
            {project.company_name}{project.brand_name ? ` / ${project.brand_name}` : ''}
            {' · '}
            {(project.project_type ?? '').replace('_', ' ')}
            {project.owner_name ? ` · Owner: ${project.owner_name}` : ''}
          </span>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => exportProjectPdf(project)} title="Export PDF">
              <Download className="h-3.5 w-3.5" />
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setShowEditDialog(true)} title="Edit">
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <StatusActions project={project} onDone={() => queryClient.invalidateQueries({ queryKey: ['mkt-project', id] })} />
          </div>
        }
      />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
          <TabsList className="w-max md:w-auto">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <TabsTrigger key={tab.key} value={tab.key}>
                  <Icon className="h-3.5 w-3.5" />
                  {tab.label}
                </TabsTrigger>
              )
            })}
          </TabsList>
        </div>
      </Tabs>

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
        <DialogContent className="sm:max-w-[1024px] max-h-[90vh] overflow-y-auto" aria-describedby={undefined}>
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

      {/* Quick Spend FAB */}
      {budgetLines.length > 0 && (
        <Button
          className="fixed bottom-6 right-6 h-12 w-12 rounded-full shadow-lg z-40"
          size="icon"
          onClick={() => setShowQuickSpend(true)}
        >
          <Plus className="h-5 w-5" />
        </Button>
      )}

      {/* Quick Spend Dialog */}
      <Dialog open={showQuickSpend} onOpenChange={setShowQuickSpend}>
        <DialogContent className="max-w-sm" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <DollarSign className="h-4 w-4" /> Quick Spend
            </DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (!spendLineId || !spendAmount) return
              spendMut.mutate({
                lineId: Number(spendLineId),
                amount: Number(spendAmount),
                date: spendDate,
                desc: spendDesc,
              })
            }}
          >
            <div className="space-y-1.5">
              <Label>Budget Line</Label>
              <Select value={spendLineId} onValueChange={setSpendLineId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select channel..." />
                </SelectTrigger>
                <SelectContent>
                  {budgetLines.map((bl) => (
                    <SelectItem key={bl.id} value={String(bl.id)}>
                      {bl.channel}{bl.description ? ` – ${bl.description}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Amount ({project.currency || 'RON'})</Label>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                placeholder="0.00"
                value={spendAmount}
                onChange={(e) => setSpendAmount(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input type="date" value={spendDate} onChange={(e) => setSpendDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Description (optional)</Label>
              <Input
                placeholder="e.g. Facebook Ads invoice #123"
                value={spendDesc}
                onChange={(e) => setSpendDesc(e.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setShowQuickSpend(false)}>Cancel</Button>
              <Button type="submit" disabled={!spendLineId || !spendAmount || spendMut.isPending}>
                {spendMut.isPending ? 'Saving...' : 'Record Spend'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
