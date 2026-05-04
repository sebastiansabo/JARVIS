import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { MapPin, Plus, Users, CheckCircle2, Clock, CalendarCheck, Route as RouteIcon, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { DateField } from '@/components/ui/date-field'
import { fieldSalesApi, type FSVisit } from '@/api/fieldSales'
import { usersApi } from '@/api/users'
import { CreateVisitDialog } from './CreateVisitDialog'
import { VisitDetailDialog } from './VisitDetailDialog'

const VISIT_TYPE_LABELS: Record<string, string> = {
  general: 'General',
  fleet_review: 'Fleet Review',
  renewal_discussion: 'Reinnoire',
  test_drive_followup: 'Test Drive',
  service_followup: 'Service',
  new_acquisition: 'Achizitie',
  contract_negotiation: 'Negociere',
  prospecting: 'Prospectare',
}

const STATUS_STYLES: Record<string, string> = {
  planned: 'bg-gray-100 text-gray-700',
  in_progress: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  no_show: 'bg-red-100 text-red-700',
  rescheduled: 'bg-yellow-100 text-yellow-700',
  partial: 'bg-orange-100 text-orange-700',
}

function getMonday(d: Date) {
  const day = d.getDay()
  const diff = d.getDate() - day + (day === 0 ? -6 : 1)
  return new Date(d.getFullYear(), d.getMonth(), diff)
}

function toDateStr(d: Date) {
  return d.toISOString().slice(0, 10)
}

export default function FieldSales() {
  const navigate = useNavigate()
  const today = new Date()
  const monday = getMonday(today)
  const [dateFrom, setDateFrom] = useState(toDateStr(monday))
  const [dateTo, setDateTo] = useState(toDateStr(today))
  const [kamFilter, setKamFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedVisitId, setSelectedVisitId] = useState<number | null>(null)
  const [expandedRoutes, setExpandedRoutes] = useState<Set<number>>(new Set())

  const { data: users = [] } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 5 * 60_000,
  })
  const activeUsers = useMemo(() => users.filter(u => u.is_active), [users])

  const { data, isLoading } = useQuery({
    queryKey: ['fs-manager-overview', dateFrom, dateTo, kamFilter],
    queryFn: () => fieldSalesApi.getManagerOverview(
      dateFrom,
      dateTo,
      kamFilter !== 'all' ? Number(kamFilter) : undefined,
    ),
    enabled: !!dateFrom && !!dateTo,
  })

  const visits = useMemo(() => {
    if (!data?.visits) return []
    if (statusFilter === 'all') return data.visits
    return data.visits.filter(v => v.status === statusFilter)
  }, [data?.visits, statusFilter])

  // Group visits: route groups + standalone visits
  type VisitGroup = { type: 'route'; routeId: number; routeName: string; date: string; kamName: string; visits: FSVisit[] }
                  | { type: 'standalone'; visit: FSVisit }

  const grouped = useMemo<VisitGroup[]>(() => {
    const groups: VisitGroup[] = []
    const routeMap = new Map<number, VisitGroup & { type: 'route' }>()

    for (const v of visits) {
      if (v.route_id) {
        let g = routeMap.get(v.route_id)
        if (!g) {
          g = { type: 'route', routeId: v.route_id, routeName: v.route_name || `Ruta #${v.route_id}`, date: v.planned_date, kamName: v.kam_name, visits: [] }
          routeMap.set(v.route_id, g)
          groups.push(g)
        }
        g.visits.push(v)
      } else {
        groups.push({ type: 'standalone', visit: v })
      }
    }
    return groups
  }, [visits])

  const summary = data?.summary
  const planned = summary?.by_status?.planned ?? 0
  const inProgress = summary?.by_status?.in_progress ?? 0
  const completed = summary?.by_status?.completed ?? 0

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <MapPin className="h-6 w-6 text-red-500" />
          <h1 className="text-2xl font-bold">Field Sales</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            Vizita Rapida
          </Button>
          <Button onClick={() => navigate('/app/sales/field-sales/route-planner')}>
            <RouteIcon className="h-4 w-4 mr-1.5" />
            Planifica Ruta
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">De la</label>
          <DateField value={dateFrom} onChange={setDateFrom} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Pana la</label>
          <DateField value={dateTo} onChange={setDateTo} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">KAM</label>
          <Select value={kamFilter} onValueChange={setKamFilter}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toti</SelectItem>
              {activeUsers.map(u => (
                <SelectItem key={u.id} value={String(u.id)}>{u.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Status</label>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toate</SelectItem>
              <SelectItem value="planned">Planificate</SelectItem>
              <SelectItem value="in_progress">In desfasurare</SelectItem>
              <SelectItem value="completed">Finalizate</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-3">
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <CalendarCheck className="h-8 w-8 text-blue-500" />
            <div>
              <p className="text-2xl font-bold">{summary?.total ?? 0}</p>
              <p className="text-xs text-muted-foreground">Total vizite</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Clock className="h-8 w-8 text-gray-400" />
            <div>
              <p className="text-2xl font-bold">{planned}</p>
              <p className="text-xs text-muted-foreground">Planificate</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Users className="h-8 w-8 text-blue-500" />
            <div>
              <p className="text-2xl font-bold">{inProgress}</p>
              <p className="text-xs text-muted-foreground">In desfasurare</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <CheckCircle2 className="h-8 w-8 text-green-500" />
            <div>
              <p className="text-2xl font-bold">{completed}</p>
              <p className="text-xs text-muted-foreground">Finalizate</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Visit Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Data</TableHead>
                <TableHead>Ora</TableHead>
                <TableHead>Client</TableHead>
                <TableHead>KAM</TableHead>
                <TableHead>Tip</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Rezultat</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 7 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-4 w-20" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : visits.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                    Nicio vizita in perioada selectata
                  </TableCell>
                </TableRow>
              ) : (
                grouped.map((g) => {
                  if (g.type === 'standalone') {
                    const v = g.visit
                    return (
                      <TableRow key={v.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setSelectedVisitId(v.id)}>
                        <TableCell className="font-medium whitespace-nowrap">{v.planned_date}</TableCell>
                        <TableCell>{v.planned_time || '—'}</TableCell>
                        <TableCell>
                          <div>{v.client_name}</div>
                          {v.client_city && <div className="text-xs text-muted-foreground">{v.client_city}</div>}
                        </TableCell>
                        <TableCell>{v.kam_name}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs">
                            {VISIT_TYPE_LABELS[v.visit_type] || v.visit_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[v.status] || 'bg-gray-100 text-gray-700'}`}>
                            {v.status === 'planned' ? 'Planificat' :
                             v.status === 'in_progress' ? 'In desfasurare' :
                             v.status === 'completed' ? 'Finalizat' :
                             v.status === 'no_show' ? 'Absent' :
                             v.status === 'rescheduled' ? 'Reprogramat' :
                             v.status}
                          </span>
                        </TableCell>
                        <TableCell className="text-sm">
                          {v.outcome || '—'}
                        </TableCell>
                      </TableRow>
                    )
                  }
                  // Route group with expand/collapse
                  const isExpanded = expandedRoutes.has(g.routeId)
                  const toggleRoute = () => setExpandedRoutes(prev => {
                    const next = new Set(prev)
                    if (next.has(g.routeId)) next.delete(g.routeId)
                    else next.add(g.routeId)
                    return next
                  })
                  return [
                    <TableRow
                      key={`route-${g.routeId}`}
                      className="bg-blue-50/60 border-t-2 border-blue-200 cursor-pointer hover:bg-blue-100/60"
                      onClick={toggleRoute}
                    >
                      <TableCell className="font-medium whitespace-nowrap">
                        <div className="flex items-center gap-1">
                          <ChevronRight className={`h-4 w-4 text-blue-500 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                          {g.date}
                        </div>
                      </TableCell>
                      <TableCell colSpan={2}>
                        <div className="flex items-center gap-1.5">
                          <RouteIcon className="h-4 w-4 text-blue-600" />
                          <span className="font-semibold text-blue-700">{g.routeName}</span>
                          <span className="text-xs text-blue-500 ml-1">({g.visits.length} opriri)</span>
                        </div>
                      </TableCell>
                      <TableCell className="font-medium">{g.kamName}</TableCell>
                      <TableCell colSpan={3} />
                    </TableRow>,
                    ...(isExpanded ? g.visits.map((v, vi) => (
                      <TableRow
                        key={v.id}
                        className={`cursor-pointer hover:bg-blue-50/40 ${vi < g.visits.length - 1 ? '' : 'border-b-2 border-blue-200'}`}
                        onClick={() => setSelectedVisitId(v.id)}
                      >
                        <TableCell className="pl-8 text-muted-foreground text-xs whitespace-nowrap">
                          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-100 text-blue-700 text-[10px] font-bold mr-1.5">
                            {v.sequence || vi + 1}
                          </span>
                          Stop
                        </TableCell>
                        <TableCell>{v.planned_time || '—'}</TableCell>
                        <TableCell>
                          <div>{v.client_name}</div>
                          {v.client_city && <div className="text-xs text-muted-foreground">{v.client_city}</div>}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs">—</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs">
                            {VISIT_TYPE_LABELS[v.visit_type] || v.visit_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[v.status] || 'bg-gray-100 text-gray-700'}`}>
                            {v.status === 'planned' ? 'Planificat' :
                             v.status === 'in_progress' ? 'In desfasurare' :
                             v.status === 'completed' ? 'Finalizat' :
                             v.status === 'no_show' ? 'Absent' :
                             v.status === 'rescheduled' ? 'Reprogramat' :
                             v.status}
                          </span>
                        </TableCell>
                        <TableCell className="text-sm">
                          {v.outcome || '—'}
                        </TableCell>
                      </TableRow>
                    )) : []),
                  ]
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <CreateVisitDialog open={createOpen} onOpenChange={setCreateOpen} />
      <VisitDetailDialog
        visitId={selectedVisitId}
        open={selectedVisitId !== null}
        onOpenChange={open => { if (!open) setSelectedVisitId(null) }}
      />
    </div>
  )
}
