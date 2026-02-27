import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Wand2,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { StatCard } from '@/components/shared/StatCard'
import { biostarApi } from '@/api/biostar'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { BioStarOffScheduleRow, BioStarAdjustment } from '@/types/biostar'

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function shiftDate(dateStr: string, days: number) {
  const d = new Date(dateStr + 'T00:00:00')
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

function formatTime(dt: string | null) {
  if (!dt) return '-'
  return new Date(dt).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
}

function fmtScheduleTime(t: string | null) {
  if (!t) return '-'
  return t.slice(0, 5)
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}

function deviationLabel(minutes: number | null) {
  if (minutes === null || minutes === undefined) return '-'
  const abs = Math.abs(Math.round(minutes))
  if (abs < 1) return 'on time'
  const sign = minutes > 0 ? '+' : '-'
  return `${sign}${abs}m`
}

function deviationColor(minutes: number | null) {
  if (minutes === null || minutes === undefined) return ''
  const abs = Math.abs(minutes)
  if (abs < 15) return 'text-muted-foreground'
  if (abs < 30) return 'text-orange-600'
  return 'text-red-600'
}

function formatWorked(durationSeconds: number | null, lunchMinutes: number) {
  if (durationSeconds === null || durationSeconds === undefined) return '-'
  let net = durationSeconds
  if (lunchMinutes > 0 && net > lunchMinutes * 60) net -= lunchMinutes * 60
  const h = Math.floor(net / 3600)
  const m = Math.round((net % 3600) / 60)
  return `${h}h ${m.toString().padStart(2, '0')}m`
}

export default function AdjustmentsTab() {
  const qc = useQueryClient()
  const [date, setDate] = useState(shiftDate(todayStr(), -1)) // yesterday by default
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<'pending' | 'adjusted'>('pending')

  const { data: status } = useQuery({
    queryKey: ['biostar', 'status'],
    queryFn: biostarApi.getStatus,
  })

  const connected = !!status?.connected

  const { data: offSchedule = [], isLoading: loadingOff } = useQuery({
    queryKey: ['biostar', 'off-schedule', date],
    queryFn: () => biostarApi.getOffSchedule(date),
  })

  const { data: adjustments = [], isLoading: loadingAdj } = useQuery({
    queryKey: ['biostar', 'adjustments', date],
    queryFn: () => biostarApi.getAdjustments(date),
  })

  const adjustMut = useMutation({
    mutationFn: (row: BioStarOffScheduleRow) => {
      const dateStr = date
      const datePart = row.first_punch.slice(0, 10)
      const adjFirst = `${datePart}T${fmtScheduleTime(row.schedule_start)}:00`
      const adjLast = `${datePart}T${fmtScheduleTime(row.schedule_end)}:00`
      return biostarApi.adjustEmployee({
        biostar_user_id: row.biostar_user_id,
        date: dateStr,
        adjusted_first_punch: adjFirst,
        adjusted_last_punch: adjLast,
        original_first_punch: row.first_punch,
        original_last_punch: row.last_punch,
        schedule_start: fmtScheduleTime(row.schedule_start),
        schedule_end: fmtScheduleTime(row.schedule_end),
        lunch_break_minutes: row.lunch_break_minutes,
        working_hours: row.working_hours,
        original_duration_seconds: row.duration_seconds ?? undefined,
        deviation_minutes_in: Math.round(row.deviation_in),
        deviation_minutes_out: Math.round(row.deviation_out),
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'off-schedule', date] })
      qc.invalidateQueries({ queryKey: ['biostar', 'adjustments', date] })
      toast.success('Adjustment saved')
    },
    onError: () => toast.error('Failed to save adjustment'),
  })

  const autoAdjustMut = useMutation({
    mutationFn: () => biostarApi.autoAdjustAll(date),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['biostar', 'off-schedule', date] })
      qc.invalidateQueries({ queryKey: ['biostar', 'adjustments', date] })
      toast.success(`Auto-adjusted ${res.data.adjusted} employees`)
    },
    onError: () => toast.error('Auto-adjust failed'),
  })

  const revertMut = useMutation({
    mutationFn: (row: BioStarAdjustment) => biostarApi.revertAdjustment(row.biostar_user_id, date),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'off-schedule', date] })
      qc.invalidateQueries({ queryKey: ['biostar', 'adjustments', date] })
      toast.success('Adjustment reverted')
    },
    onError: () => toast.error('Failed to revert'),
  })

  const filteredOff = useMemo(() => {
    if (!search) return offSchedule
    const s = search.toLowerCase()
    return offSchedule.filter(
      (r) => r.name?.toLowerCase().includes(s) || (r.user_group_name || '').toLowerCase().includes(s),
    )
  }, [offSchedule, search])

  const filteredAdj = useMemo(() => {
    if (!search) return adjustments
    const s = search.toLowerCase()
    return adjustments.filter(
      (r) => r.name?.toLowerCase().includes(s) || (r.user_group_name || '').toLowerCase().includes(s),
    )
  }, [adjustments, search])

  const isLoading = loadingOff || loadingAdj

  return (
    <div className="space-y-4">
      {/* Connection warning */}
      {!connected && (
        <div className="flex items-center gap-2 rounded-md border border-orange-300 bg-orange-50 px-4 py-2 text-sm text-orange-800 dark:border-orange-700 dark:bg-orange-950/30 dark:text-orange-300">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>BioStar not connected — showing cached data. Configure connection in Settings &gt; Connectors.</span>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard title="Off-Schedule" value={offSchedule.length} icon={<AlertTriangle className="h-4 w-4" />} />
        <StatCard title="Adjusted" value={adjustments.length} icon={<CheckCircle2 className="h-4 w-4" />} />
        <StatCard title="Total Flagged" value={offSchedule.length + adjustments.length} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Date" value={formatDate(date)} icon={<Clock className="h-4 w-4" />} />
      </div>

      {/* Date nav + Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setDate(shiftDate(date, -1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Input
            type="date"
            className="h-8 w-40 text-sm"
            value={date}
            max={todayStr()}
            onChange={(e) => setDate(e.target.value)}
          />
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            disabled={date >= todayStr()}
            onClick={() => setDate(shiftDate(date, 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9 h-8"
            placeholder="Search by name, group..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="flex gap-1">
          <Button
            variant={tab === 'pending' ? 'default' : 'outline'}
            size="sm"
            className="h-8"
            onClick={() => setTab('pending')}
          >
            <AlertTriangle className="mr-1.5 h-3.5 w-3.5" />
            Pending ({offSchedule.length})
          </Button>
          <Button
            variant={tab === 'adjusted' ? 'default' : 'outline'}
            size="sm"
            className="h-8"
            onClick={() => setTab('adjusted')}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            Adjusted ({adjustments.length})
          </Button>
        </div>

        {tab === 'pending' && offSchedule.length > 0 && (
          <Button
            size="sm"
            className="h-8"
            onClick={() => autoAdjustMut.mutate()}
            disabled={autoAdjustMut.isPending}
          >
            <Wand2 className="mr-1.5 h-3.5 w-3.5" />
            {autoAdjustMut.isPending ? 'Adjusting...' : 'Auto-Adjust All'}
          </Button>
        )}
      </div>

      {/* Tables */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : tab === 'pending' ? (
        <PendingTable rows={filteredOff} onAdjust={(row) => adjustMut.mutate(row)} adjusting={adjustMut.isPending} />
      ) : (
        <AdjustedTable rows={filteredAdj} onRevert={(row) => revertMut.mutate(row)} reverting={revertMut.isPending} />
      )}
    </div>
  )
}

// ── Pending (Off-Schedule) Table ──

function PendingTable({
  rows,
  onAdjust,
  adjusting,
}: {
  rows: BioStarOffScheduleRow[]
  onAdjust: (row: BioStarOffScheduleRow) => void
  adjusting: boolean
}) {
  if (rows.length === 0) {
    return <EmptyState title="All compliant" description="No off-schedule employees for this date." />
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Employee</TableHead>
            <TableHead className="hidden md:table-cell">Group</TableHead>
            <TableHead className="text-center">Schedule</TableHead>
            <TableHead className="text-center">Actual In</TableHead>
            <TableHead className="text-center">Actual Out</TableHead>
            <TableHead className="text-center">Worked</TableHead>
            <TableHead className="text-center">Dev. In</TableHead>
            <TableHead className="text-center">Dev. Out</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.biostar_user_id}>
              <TableCell>
                <span className="font-medium">{row.name}</span>
                {row.email && <p className="text-xs text-muted-foreground">{row.email}</p>}
              </TableCell>
              <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                {row.user_group_name || '-'}
              </TableCell>
              <TableCell className="text-center text-sm">
                <span className="text-muted-foreground">
                  {fmtScheduleTime(row.schedule_start)} — {fmtScheduleTime(row.schedule_end)}
                </span>
              </TableCell>
              <TableCell className="text-center text-sm font-medium">{formatTime(row.first_punch)}</TableCell>
              <TableCell className="text-center text-sm font-medium">{formatTime(row.last_punch)}</TableCell>
              <TableCell className="text-center text-sm font-medium">
                {formatWorked(row.duration_seconds, row.lunch_break_minutes)}
              </TableCell>
              <TableCell className="text-center">
                <span className={cn('text-sm font-medium', deviationColor(row.deviation_in))}>
                  {deviationLabel(row.deviation_in)}
                </span>
              </TableCell>
              <TableCell className="text-center">
                <span className={cn('text-sm font-medium', deviationColor(row.deviation_out))}>
                  {deviationLabel(row.deviation_out)}
                </span>
              </TableCell>
              <TableCell>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  onClick={() => onAdjust(row)}
                  disabled={adjusting}
                >
                  <CheckCircle2 className="mr-1 h-3 w-3" />
                  Adjust
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

// ── Adjusted Table ──

function AdjustedTable({
  rows,
  onRevert,
  reverting,
}: {
  rows: BioStarAdjustment[]
  onRevert: (row: BioStarAdjustment) => void
  reverting: boolean
}) {
  if (rows.length === 0) {
    return <EmptyState title="No adjustments" description="No adjustments have been made for this date." />
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Employee</TableHead>
            <TableHead className="hidden md:table-cell">Group</TableHead>
            <TableHead className="text-center">Original In</TableHead>
            <TableHead className="text-center">Original Out</TableHead>
            <TableHead className="text-center">Adjusted In</TableHead>
            <TableHead className="text-center">Adjusted Out</TableHead>
            <TableHead className="text-center hidden lg:table-cell">Type</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.biostar_user_id}>
              <TableCell>
                <span className="font-medium">{row.name}</span>
                {row.email && <p className="text-xs text-muted-foreground">{row.email}</p>}
              </TableCell>
              <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                {row.user_group_name || '-'}
              </TableCell>
              <TableCell className="text-center text-sm text-muted-foreground">
                {formatTime(row.original_first_punch)}
              </TableCell>
              <TableCell className="text-center text-sm text-muted-foreground">
                {formatTime(row.original_last_punch)}
              </TableCell>
              <TableCell className="text-center text-sm font-medium text-green-600">
                {formatTime(row.adjusted_first_punch)}
              </TableCell>
              <TableCell className="text-center text-sm font-medium text-green-600">
                {formatTime(row.adjusted_last_punch)}
              </TableCell>
              <TableCell className="text-center hidden lg:table-cell">
                <Badge variant={row.adjustment_type === 'auto' ? 'secondary' : 'outline'} className="text-xs">
                  {row.adjustment_type}
                </Badge>
              </TableCell>
              <TableCell>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs text-muted-foreground"
                  onClick={() => onRevert(row)}
                  disabled={reverting}
                >
                  <RotateCcw className="mr-1 h-3 w-3" />
                  Revert
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
