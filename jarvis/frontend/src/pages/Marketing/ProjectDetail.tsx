import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTabParam } from '@/hooks/useTabParam'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PageHeader } from '@/components/shared/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Pencil, BarChart3, DollarSign, Target, Users,
  CalendarDays, Clock, FileText, MessageSquare, Download,
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
      <PageHeader
        title={project.name}
        breadcrumbs={[
          { label: 'Marketing', href: '/app/marketing' },
          { label: 'Campaigns', href: '/app/marketing?tab=projects' },
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
            <Button variant="outline" size="icon" className="h-8 w-8 md:size-auto md:px-3" onClick={() => exportProjectPdf(project)}>
              <Download className="h-3.5 w-3.5 md:mr-1.5" />
              <span className="hidden md:inline">PDF</span>
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8 md:size-auto md:px-3" onClick={() => setShowEditDialog(true)}>
              <Pencil className="h-3.5 w-3.5 md:mr-1.5" />
              <span className="hidden md:inline">Edit</span>
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
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" aria-describedby={undefined}>
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
