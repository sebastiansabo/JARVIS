import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, Inbox, Clock, CheckCircle2, XCircle } from 'lucide-react'

import { ticketingApi } from '@/api/ticketing'
import type { TicketStatus, TicketPriority } from '@/types/ticketing'

import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { SearchInput } from '@/components/shared/SearchInput'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useIsMobile } from '@/hooks/useMediaQuery'

import CreateTicketDialog from './CreateTicketDialog'

const priorityColors: Record<TicketPriority, string> = {
  low: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  medium: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
  critical: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
}

const statusLabels: Record<TicketStatus, string> = {
  open: 'Open',
  in_progress: 'In Progress',
  resolved: 'Resolved',
  closed: 'Closed',
}

const categoryLabels: Record<string, string> = {
  hardware: 'Hardware',
  software: 'Software',
  network: 'Network',
  access: 'Access',
  other: 'Other',
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function Ticketing() {
  const navigate = useNavigate()
  const isMobile = useIsMobile()

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [priorityFilter, setPriorityFilter] = useState<string>('')
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [createOpen, setCreateOpen] = useState(false)

  const statsQ = useQuery({
    queryKey: ['ticketing', 'stats'],
    queryFn: () => ticketingApi.getStats(),
  })

  const ticketsQ = useQuery({
    queryKey: ['ticketing', 'tickets', statusFilter, priorityFilter, categoryFilter, search],
    queryFn: () =>
      ticketingApi.getTickets({
        status: statusFilter === 'all' ? undefined : statusFilter,
        priority: priorityFilter || undefined,
        category: categoryFilter || undefined,
        search: search || undefined,
        limit: 100,
      }),
  })

  const stats = statsQ.data
  const tickets = ticketsQ.data?.items ?? []

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Tickets"
        breadcrumbs={[{ label: 'Tickets' }]}
        search={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Search tickets..."
            collapsible={isMobile}
          />
        }
        actions={
          <Button onClick={() => setCreateOpen(true)} size={isMobile ? 'sm' : 'default'}>
            <Plus className="mr-1 h-4 w-4" />
            New Ticket
          </Button>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <StatCard
          title="Open"
          value={stats?.open ?? 0}
          icon={<Inbox className="h-4 w-4 text-blue-500" />}
          isLoading={statsQ.isLoading}
        />
        <StatCard
          title="In Progress"
          value={stats?.in_progress ?? 0}
          icon={<Clock className="h-4 w-4 text-amber-500" />}
          isLoading={statsQ.isLoading}
        />
        <StatCard
          title="Resolved"
          value={stats?.resolved ?? 0}
          icon={<CheckCircle2 className="h-4 w-4 text-green-500" />}
          isLoading={statsQ.isLoading}
        />
        <StatCard
          title="Closed"
          value={stats?.closed ?? 0}
          icon={<XCircle className="h-4 w-4 text-gray-500" />}
          isLoading={statsQ.isLoading}
        />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={statusFilter} onValueChange={setStatusFilter}>
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="open">Open</TabsTrigger>
            <TabsTrigger value="in_progress">In Progress</TabsTrigger>
            <TabsTrigger value="resolved">Resolved</TabsTrigger>
            <TabsTrigger value="closed">Closed</TabsTrigger>
          </TabsList>
        </Tabs>

        <Select value={priorityFilter} onValueChange={(v) => setPriorityFilter(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Priorities</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>

        <Select value={categoryFilter} onValueChange={(v) => setCategoryFilter(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-[130px]">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            <SelectItem value="hardware">Hardware</SelectItem>
            <SelectItem value="software">Software</SelectItem>
            <SelectItem value="network">Network</SelectItem>
            <SelectItem value="access">Access</SelectItem>
            <SelectItem value="other">Other</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      {ticketsQ.isLoading ? (
        <Card className="p-4">
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </Card>
      ) : tickets.length === 0 ? (
        <Card className="flex flex-col items-center justify-center p-12 text-center text-muted-foreground">
          <Inbox className="mb-3 h-10 w-10" />
          <p className="text-lg font-medium">No tickets found</p>
          <p className="text-sm">Create a new ticket to get started.</p>
        </Card>
      ) : isMobile ? (
        <div className="space-y-2">
          {tickets.map((t) => (
            <Card
              key={t.id}
              className="cursor-pointer p-3 transition-colors hover:bg-accent"
              onClick={() => navigate(`/app/ticketing/${t.id}`)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">#{t.id} {t.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t.created_by_name} &middot; {formatDate(t.created_at)}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <StatusBadge status={t.status} label={statusLabels[t.status]} />
                  <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${priorityColors[t.priority]}`}>
                    {t.priority}
                  </span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[60px]">#</TableHead>
                <TableHead>Title</TableHead>
                <TableHead className="w-[100px]">Status</TableHead>
                <TableHead className="w-[90px]">Priority</TableHead>
                <TableHead className="w-[90px]">Category</TableHead>
                <TableHead className="w-[140px]">Submitted By</TableHead>
                <TableHead className="w-[140px]">Assigned To</TableHead>
                <TableHead className="w-[100px]">Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tickets.map((t) => (
                <TableRow
                  key={t.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/app/ticketing/${t.id}`)}
                >
                  <TableCell className="font-mono text-muted-foreground">{t.id}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{t.title}</span>
                      {t.comment_count > 0 && (
                        <span className="text-xs text-muted-foreground">
                          ({t.comment_count})
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={t.status} label={statusLabels[t.status]} />
                  </TableCell>
                  <TableCell>
                    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${priorityColors[t.priority]}`}>
                      {t.priority}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {categoryLabels[t.category] ?? t.category}
                  </TableCell>
                  <TableCell className="text-sm">{t.created_by_name}</TableCell>
                  <TableCell className="text-sm">
                    {t.assigned_to_name ?? <span className="text-muted-foreground">Unassigned</span>}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(t.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <CreateTicketDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
