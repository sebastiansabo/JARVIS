import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Search,
  ChevronDown,
  ChevronRight,
  ArrowUpDown,
  Clock,
  LogIn,
  LogOut,
  UserCheck,
  Fingerprint,
  ExternalLink,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/shared/EmptyState'
import { StatCard } from '@/components/shared/StatCard'
import { biostarApi } from '@/api/biostar'
import { cn } from '@/lib/utils'
import type { BioStarDailySummary, BioStarPunchLog } from '@/types/biostar'

type SortField = 'name' | 'group' | 'check_in' | 'check_out' | 'duration' | 'punches'
type SortDir = 'asc' | 'desc'

function formatTime(dt: string | null) {
  if (!dt) return '-'
  return new Date(dt).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
}

function formatDuration(seconds: number | null) {
  if (!seconds || seconds <= 0) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${m}m`
  return `${h}h ${m}m`
}

function netSeconds(durationSec: number | null, lunchMin: number) {
  if (!durationSec || durationSec <= 0) return 0
  const lunchSec = lunchMin * 60
  // Only subtract lunch if duration > lunch (person was there long enough)
  return durationSec > lunchSec ? durationSec - lunchSec : durationSec
}

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

export default function PontajeTab() {
  const navigate = useNavigate()
  const today = todayStr()
  const [search, setSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState<string>('all')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data: status } = useQuery({
    queryKey: ['biostar', 'status'],
    queryFn: biostarApi.getStatus,
  })

  const { data: summary = [], isLoading } = useQuery({
    queryKey: ['biostar', 'daily-summary', today],
    queryFn: () => biostarApi.getDailySummary(today),
    enabled: !!status?.connected,
    refetchInterval: 60_000,
  })

  const groups = useMemo(() => {
    const set = new Set<string>()
    summary.forEach((e) => { if (e.user_group_name) set.add(e.user_group_name) })
    return Array.from(set).sort()
  }, [summary])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const processed = useMemo(() => {
    let list = [...summary]

    if (groupFilter !== 'all') {
      list = list.filter((e) => e.user_group_name === groupFilter)
    }

    if (search) {
      const s = search.toLowerCase()
      list = list.filter(
        (e) =>
          (e.name || '').toLowerCase().includes(s) ||
          (e.email || '').toLowerCase().includes(s) ||
          (e.user_group_name || '').toLowerCase().includes(s) ||
          (e.mapped_jarvis_user_name || '').toLowerCase().includes(s),
      )
    }

    list.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'name':
          cmp = (a.name || '').localeCompare(b.name || '')
          break
        case 'group':
          cmp = (a.user_group_name || '').localeCompare(b.user_group_name || '')
          break
        case 'check_in':
          cmp = (a.first_punch || '').localeCompare(b.first_punch || '')
          break
        case 'check_out':
          cmp = (a.last_punch || '').localeCompare(b.last_punch || '')
          break
        case 'duration':
          cmp = netSeconds(a.duration_seconds, a.lunch_break_minutes ?? 60) - netSeconds(b.duration_seconds, b.lunch_break_minutes ?? 60)
          break
        case 'punches':
          cmp = a.total_punches - b.total_punches
          break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })

    return list
  }, [summary, groupFilter, search, sortField, sortDir])

  // Stats (net = minus lunch break)
  const totalPresent = summary.length
  const totalHours = summary.reduce((acc, e) => acc + netSeconds(e.duration_seconds, e.lunch_break_minutes ?? 60), 0) / 3600
  const avgHours = totalPresent > 0 ? totalHours / totalPresent : 0
  const earlyBirds = summary.filter((e) => {
    if (!e.first_punch) return false
    return new Date(e.first_punch).getHours() < 8
  }).length

  if (!status?.connected) {
    return (
      <EmptyState
        title="BioStar not connected"
        description="Configure the BioStar 2 connection in Settings > Connectors first."
      />
    )
  }

  const SortIcon = ({ field }: { field: SortField }) => (
    <ArrowUpDown className={cn('ml-1 h-3 w-3 inline', sortField === field ? 'opacity-100' : 'opacity-40')} />
  )

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard title="Present Today" value={totalPresent} icon={<UserCheck className="h-4 w-4" />} />
        <StatCard title="Total Hours" value={totalHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Avg Hours" value={avgHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Early (<8:00)" value={earlyBirds} icon={<LogIn className="h-4 w-4" />} />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search by name, email, group..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={groupFilter} onValueChange={setGroupFilter}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All Groups" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Groups ({summary.length})</SelectItem>
            {groups.map((g) => (
              <SelectItem key={g} value={g}>
                {g} ({summary.filter((e) => e.user_group_name === g).length})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : processed.length === 0 ? (
        <EmptyState
          title="No attendance data"
          description={search ? 'Try a different search term.' : 'No punch logs found for today.'}
        />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                  Employee <SortIcon field="name" />
                </TableHead>
                <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                  Group <SortIcon field="group" />
                </TableHead>
                <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_in')}>
                  Check In <SortIcon field="check_in" />
                </TableHead>
                <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_out')}>
                  Check Out <SortIcon field="check_out" />
                </TableHead>
                <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('duration')}>
                  Duration <SortIcon field="duration" />
                </TableHead>
                <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('punches')}>
                  Punches <SortIcon field="punches" />
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {processed.map((emp) => (
                <EmployeeRow
                  key={emp.biostar_user_id}
                  employee={emp}
                  date={today}
                  isExpanded={expandedId === emp.biostar_user_id}
                  onToggle={() =>
                    setExpandedId(expandedId === emp.biostar_user_id ? null : emp.biostar_user_id)
                  }
                  onProfile={() => navigate(`/app/hr/pontaje/${emp.biostar_user_id}`)}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="text-sm text-muted-foreground">
        Showing {processed.length} of {summary.length} employees
      </div>
    </div>
  )
}

// ── Employee Row ──

function EmployeeRow({
  employee,
  date,
  isExpanded,
  onToggle,
  onProfile,
}: {
  employee: BioStarDailySummary
  date: string
  isExpanded: boolean
  onToggle: () => void
  onProfile: () => void
}) {
  const lunch = employee.lunch_break_minutes ?? 60
  const expectedH = employee.working_hours ?? 8
  const net = netSeconds(employee.duration_seconds, lunch)
  const netH = net / 3600
  const isShort = netH > 0 && netH < expectedH

  return (
    <>
      <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onToggle}>
        <TableCell className="w-8 px-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <div className="min-w-0">
              <button
                className="font-medium hover:underline text-left"
                onClick={(e) => { e.stopPropagation(); onProfile() }}
              >
                {employee.name}
              </button>
              {employee.mapped_jarvis_user_name && (
                <Badge variant="outline" className="ml-2 text-[10px] font-normal">
                  {employee.mapped_jarvis_user_name}
                </Badge>
              )}
              {employee.email && (
                <p className="text-xs text-muted-foreground">{employee.email}</p>
              )}
            </div>
          </div>
        </TableCell>
        <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
          {employee.user_group_name || '-'}
        </TableCell>
        <TableCell className="text-center">
          <span className="inline-flex items-center gap-1 text-sm">
            <LogIn className="h-3 w-3 text-green-600" />
            {formatTime(employee.first_punch)}
          </span>
        </TableCell>
        <TableCell className="text-center">
          {employee.total_punches === 1 ? (
            <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
          ) : (
            <span className="inline-flex items-center gap-1 text-sm">
              <LogOut className="h-3 w-3 text-red-500" />
              {formatTime(employee.last_punch)}
            </span>
          )}
        </TableCell>
        <TableCell className="text-center">
          {employee.total_punches === 1 ? (
            <span className="text-sm text-muted-foreground">—</span>
          ) : (
          <span className={cn(
            'text-sm font-medium',
            isShort ? 'text-orange-600' : 'text-foreground',
          )}>
            {formatDuration(net)}
          </span>
          )}
          {net > 0 && lunch > 0 && (
            <span className="block text-[10px] text-muted-foreground">-{lunch}m lunch</span>
          )}
        </TableCell>
        <TableCell className="text-center">
          <Badge variant="secondary" className="text-xs">
            {employee.total_punches}
          </Badge>
        </TableCell>
      </TableRow>
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/30 p-0">
            <TodayPunches biostarUserId={employee.biostar_user_id} date={date} onProfile={onProfile} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

// ── Today's punches inline ──

function TodayPunches({ biostarUserId, date, onProfile }: { biostarUserId: string; date: string; onProfile: () => void }) {
  const { data: punches = [], isLoading } = useQuery({
    queryKey: ['biostar', 'employee-punches', biostarUserId, date],
    queryFn: () => biostarApi.getEmployeePunches(biostarUserId, date),
  })

  if (isLoading) {
    return (
      <div className="p-4 space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-6 animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
          <Fingerprint className="h-3.5 w-3.5" />
          Today — {punches.length} events
        </div>
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onProfile}>
          <ExternalLink className="mr-1 h-3 w-3" />
          Full History
        </Button>
      </div>
      {punches.length === 0 ? (
        <p className="text-sm text-muted-foreground">No punch events found.</p>
      ) : (
        <div className="relative ml-4 border-l-2 border-muted-foreground/20 pl-4 space-y-2">
          {punches.map((p, i) => (
            <PunchEventLine key={p.id} punch={p} isFirst={i === 0} isLast={i === punches.length - 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function PunchEventLine({
  punch,
  isFirst,
  isLast,
}: {
  punch: BioStarPunchLog
  isFirst: boolean
  isLast: boolean
}) {
  const time = new Date(punch.event_datetime).toLocaleTimeString('ro-RO', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

  const dirIcon = punch.direction === 'IN'
    ? <LogIn className="h-3.5 w-3.5 text-green-600" />
    : punch.direction === 'OUT'
      ? <LogOut className="h-3.5 w-3.5 text-red-500" />
      : <Clock className="h-3.5 w-3.5 text-muted-foreground" />

  return (
    <div className="relative flex items-center gap-3">
      <div className={cn(
        'absolute -left-[22px] top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full border-2 border-background',
        isFirst ? 'bg-green-500' : isLast ? 'bg-red-500' : 'bg-muted-foreground/40',
      )} />
      <span className="font-mono font-medium text-sm w-16">{time}</span>
      <span className="flex items-center gap-1">
        {dirIcon}
        <span className={cn(
          'text-xs font-medium',
          punch.direction === 'IN' ? 'text-green-600' : punch.direction === 'OUT' ? 'text-red-500' : 'text-muted-foreground',
        )}>
          {punch.direction || 'ACCESS'}
        </span>
      </span>
      {punch.device_name && (
        <span className="text-xs text-muted-foreground truncate max-w-[200px]" title={punch.device_name}>
          {punch.device_name}
        </span>
      )}
    </div>
  )
}
