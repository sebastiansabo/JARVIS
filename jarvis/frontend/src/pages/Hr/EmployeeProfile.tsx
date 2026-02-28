import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Clock,
  Fingerprint,
  LogIn,
  LogOut,
  Mail,
  Phone,
  Users,
  UserCheck,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatCard } from '@/components/shared/StatCard'
import { PageHeader } from '@/components/shared/PageHeader'
import { biostarApi } from '@/api/biostar'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { BioStarDayHistory, BioStarPunchLog } from '@/types/biostar'

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function daysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

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

function formatDate(dateStr: string) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric', month: 'short' })
}

function netSeconds(durationSec: number | null, lunchMin: number) {
  if (!durationSec || durationSec <= 0) return 0
  const lunchSec = lunchMin * 60
  return durationSec > lunchSec ? durationSec - lunchSec : durationSec
}

export default function EmployeeProfile() {
  const { biostarUserId } = useParams<{ biostarUserId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const today = todayStr()

  // Employee profile
  const { data: employee, isLoading: loadingProfile } = useQuery({
    queryKey: ['biostar', 'employee-profile', biostarUserId],
    queryFn: () => biostarApi.getEmployeeProfile(biostarUserId!),
    enabled: !!biostarUserId,
  })

  // Last 90 days history for chart
  const start90 = daysAgo(90)
  const { data: history = [], isLoading: loadingHistory } = useQuery({
    queryKey: ['biostar', 'employee-history', biostarUserId, start90, today],
    queryFn: () => biostarApi.getEmployeeDailyHistory(biostarUserId!, start90, today),
    enabled: !!biostarUserId,
  })

  // Today's punches
  const { data: todayPunches = [] } = useQuery({
    queryKey: ['biostar', 'employee-punches', biostarUserId, today],
    queryFn: () => biostarApi.getEmployeePunches(biostarUserId!, today),
    enabled: !!biostarUserId,
  })

  const scheduleMut = useMutation({
    mutationFn: (data: { lunch_break_minutes: number; working_hours: number; schedule_start?: string; schedule_end?: string }) =>
      biostarApi.updateSchedule(biostarUserId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'employee-profile', biostarUserId] })
      qc.invalidateQueries({ queryKey: ['biostar', 'employees'] })
      toast.success('Schedule updated')
    },
    onError: () => toast.error('Failed to update schedule'),
  })

  const fmtTime = (t: string | null) => (t ? t.slice(0, 5) : '08:00')

  // Stats from history (net = minus lunch break)
  const stats = useMemo(() => {
    if (!history.length) return { daysPresent: 0, avgHours: 0, totalHours: 0, maxHours: 0 }
    const nets = history.map((d) => netSeconds(d.duration_seconds, d.lunch_break_minutes ?? 60))
    const totalSec = nets.reduce((acc, s) => acc + s, 0)
    const maxSec = Math.max(...nets)
    const daysPresent = history.length
    return {
      daysPresent,
      avgHours: totalSec / daysPresent / 3600,
      totalHours: totalSec / 3600,
      maxHours: maxSec / 3600,
    }
  }, [history])

  // Daily chart data — build full range including absent days
  const [chartView, setChartView] = useState<'week' | 'month' | '3m'>('week')
  const chartDays = chartView === 'week' ? 7 : chartView === 'month' ? 30 : 90

  const dailyChartData = useMemo(() => {
    const data: { date: string; label: string; hours: number; expected: number }[] = []
    for (let i = chartDays - 1; i >= 0; i--) {
      const dateStr = daysAgo(i)
      const d = new Date(dateStr + 'T00:00:00')
      const dow = d.getDay()
      if (dow === 0 || dow === 6) continue // skip weekends
      const found = history.find((h) => h.date === dateStr)
      const net = found ? netSeconds(found.duration_seconds, found.lunch_break_minutes ?? 60) : 0
      const expected = found?.working_hours ?? employee?.working_hours ?? 8
      data.push({
        date: dateStr,
        label: chartView === 'week'
          ? d.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric' })
          : d.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' }),
        hours: net / 3600,
        expected: Number(expected),
      })
    }
    return data
  }, [history, chartDays, chartView, employee?.working_hours])

  // Last 7 days
  const last7 = useMemo(() => {
    const days: BioStarDayHistory[] = []
    for (let i = 0; i < 7; i++) {
      const dateStr = daysAgo(i)
      const found = history.find((h) => h.date === dateStr)
      if (found) {
        days.push(found)
      } else {
        days.push({ date: dateStr, first_punch: '', last_punch: '', total_punches: 0, duration_seconds: null })
      }
    }
    return days
  }, [history])

  if (loadingProfile) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (!employee) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/app/hr/pontaje')}>
          Back to Pontaje
        </Button>
        <p className="text-muted-foreground">Employee not found.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={employee.name}
        breadcrumbs={[
          { label: 'HR', href: '/app/hr/pontaje' },
          { label: 'Pontaje', href: '/app/hr/pontaje' },
          { label: employee.name },
        ]}
        description={
          <span className="flex flex-wrap items-center gap-2">
            {employee.email && (
              <span className="inline-flex items-center gap-1">
                <Mail className="h-3.5 w-3.5" />
                {employee.email}
              </span>
            )}
            {employee.phone && (
              <span className="inline-flex items-center gap-1">
                <Phone className="h-3.5 w-3.5" />
                {employee.phone}
              </span>
            )}
            {employee.user_group_name && (
              <span className="inline-flex items-center gap-1">
                <Users className="h-3.5 w-3.5" />
                {employee.user_group_name}
              </span>
            )}
            {employee.mapped_jarvis_user_name && (
              <Badge variant="outline" className="text-xs">
                <UserCheck className="mr-1 h-3 w-3" />
                Mapped: {employee.mapped_jarvis_user_name}
              </Badge>
            )}
          </span>
        }
      />

      {/* Work Schedule */}
      <div className="rounded-lg border p-4">
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Work Schedule</h3>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-14">Lunch</span>
            <Select
              value={String(employee.lunch_break_minutes ?? 60)}
              onValueChange={(v) => scheduleMut.mutate({
                lunch_break_minutes: Number(v),
                working_hours: employee.working_hours ?? 8,
              })}
            >
              <SelectTrigger className="h-8 w-24 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">None</SelectItem>
                <SelectItem value="15">15 min</SelectItem>
                <SelectItem value="30">30 min</SelectItem>
                <SelectItem value="45">45 min</SelectItem>
                <SelectItem value="60">60 min</SelectItem>
                <SelectItem value="90">90 min</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-14">Hours/Day</span>
            <Select
              value={String(Number(employee.working_hours ?? 8))}
              onValueChange={(v) => scheduleMut.mutate({
                lunch_break_minutes: employee.lunch_break_minutes ?? 60,
                working_hours: Number(v),
              })}
            >
              <SelectTrigger className="h-8 w-24 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="4">4h</SelectItem>
                <SelectItem value="6">6h</SelectItem>
                <SelectItem value="7">7h</SelectItem>
                <SelectItem value="7.5">7.5h</SelectItem>
                <SelectItem value="8">8h</SelectItem>
                <SelectItem value="8.5">8.5h</SelectItem>
                <SelectItem value="9">9h</SelectItem>
                <SelectItem value="10">10h</SelectItem>
                <SelectItem value="12">12h</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-14">From</span>
            <Select
              value={fmtTime(employee.schedule_start)}
              onValueChange={(v) => scheduleMut.mutate({
                lunch_break_minutes: employee.lunch_break_minutes ?? 60,
                working_hours: employee.working_hours ?? 8,
                schedule_start: v,
              })}
            >
              <SelectTrigger className="h-8 w-24 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['05:00','05:30','06:00','06:30','07:00','07:30','08:00','08:30','09:00','09:30','10:00'].map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-14">To</span>
            <Select
              value={fmtTime(employee.schedule_end)}
              onValueChange={(v) => scheduleMut.mutate({
                lunch_break_minutes: employee.lunch_break_minutes ?? 60,
                working_hours: employee.working_hours ?? 8,
                schedule_end: v,
              })}
            >
              <SelectTrigger className="h-8 w-24 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['14:00','14:30','15:00','15:30','16:00','16:30','17:00','17:30','18:00','18:30','19:00','20:00','22:00'].map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          title="Days Present (90d)"
          value={stats.daysPresent}
          icon={<Fingerprint className="h-4 w-4" />}
        />
        <StatCard
          title="Avg Hours/Day"
          value={stats.avgHours.toFixed(1)}
          icon={<Clock className="h-4 w-4" />}
        />
        <StatCard
          title="Total Hours (90d)"
          value={stats.totalHours.toFixed(0)}
          icon={<Clock className="h-4 w-4" />}
        />
        <StatCard
          title="Max Hours"
          value={stats.maxHours.toFixed(1)}
          icon={<Clock className="h-4 w-4" />}
        />
      </div>

      {/* Daily bar chart */}
      <div className="rounded-lg border p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-medium text-muted-foreground">Hours per Day</h3>
          <div className="flex gap-1">
            {([['week', 'Week'], ['month', 'Month'], ['3m', '3 Months']] as const).map(([key, label]) => (
              <Button
                key={key}
                variant={chartView === key ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setChartView(key)}
              >
                {label}
              </Button>
            ))}
          </div>
        </div>
        {loadingHistory ? (
          <Skeleton className="h-40 w-full" />
        ) : dailyChartData.length === 0 ? (
          <p className="text-sm text-muted-foreground">No attendance data in this period.</p>
        ) : (
          <DailyChart data={dailyChartData} compact={chartView !== 'week'} />
        )}
      </div>

      {/* Last 7 days */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Last 7 Days</h3>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Day</TableHead>
                <TableHead className="text-center">Check In</TableHead>
                <TableHead className="text-center">Check Out</TableHead>
                <TableHead className="text-center">Duration</TableHead>
                <TableHead className="text-center">Punches</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {last7.map((day) => {
                const isToday = day.date === today
                const lunch = day.lunch_break_minutes ?? 60
                const net = netSeconds(day.duration_seconds, lunch)
                const netH = net / 3600
                const expectedH = day.working_hours ?? 8
                const isShort = netH > 0 && netH < expectedH
                const isAbsent = day.total_punches === 0
                return (
                  <TableRow key={day.date} className={cn(isToday && 'bg-muted/30')}>
                    <TableCell className="font-medium">
                      {formatDate(day.date)}
                      {isToday && <Badge variant="secondary" className="ml-2 text-[10px]">Today</Badge>}
                    </TableCell>
                    <TableCell className="text-center">
                      {isAbsent ? (
                        <span className="text-sm text-muted-foreground">—</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-sm">
                          <LogIn className="h-3 w-3 text-green-600" />
                          {formatTime(day.first_punch)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-center">
                      {isAbsent ? (
                        <span className="text-sm text-muted-foreground">—</span>
                      ) : day.total_punches === 1 ? (
                        <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-sm">
                          <LogOut className="h-3 w-3 text-red-500" />
                          {formatTime(day.last_punch)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-center">
                      {isAbsent ? (
                        <Badge variant="outline" className="text-xs text-muted-foreground">Absent</Badge>
                      ) : day.total_punches === 1 ? (
                        <span className="text-sm text-muted-foreground">—</span>
                      ) : (
                        <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
                          {formatDuration(net)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-center">
                      {isAbsent ? (
                        <span className="text-sm text-muted-foreground">—</span>
                      ) : (
                        <Badge variant="secondary" className="text-xs">{day.total_punches}</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Today's punch timeline */}
      {todayPunches.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-medium text-muted-foreground">
            Today's Punches ({todayPunches.length})
          </h3>
          <div className="rounded-lg border p-4">
            <div className="relative ml-4 border-l-2 border-muted-foreground/20 pl-4 space-y-2">
              {todayPunches.map((p, i) => (
                <PunchLine key={p.id} punch={p} isFirst={i === 0} isLast={i === todayPunches.length - 1} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Daily Bar Chart (SVG) ──

function DailyChart({ data, compact }: { data: { date: string; label: string; hours: number; expected: number }[]; compact: boolean }) {
  const maxHours = Math.max(...data.map((d) => d.hours), ...data.map((d) => d.expected), 1)
  const w = Math.max(700, data.length * (compact ? 14 : 50))
  const h = 180
  const pad = { t: 16, b: compact ? 30 : 28, l: 32, r: 10 }
  const iw = w - pad.l - pad.r
  const ih = h - pad.t - pad.b

  const barWidth = Math.min(iw / data.length - (compact ? 2 : 4), compact ? 10 : 32)
  const gap = (iw - barWidth * data.length) / (data.length + 1)

  // Y-axis: 0, expected, max
  const yMax = Math.ceil(maxHours + 1)
  const ySteps = [0, Math.floor(yMax / 2), yMax]
  const expectedLine = data[0]?.expected ?? 8

  return (
    <div className="overflow-x-auto">
      <svg width={w} viewBox={`0 0 ${w} ${h}`} className="text-foreground" style={{ minWidth: w }}>
        {/* Grid lines */}
        {ySteps.map((v, i) => {
          const y = pad.t + ih - (v / yMax) * ih
          return (
            <g key={i}>
              <line x1={pad.l} x2={w - pad.r} y1={y} y2={y} stroke="currentColor" strokeOpacity={0.08} />
              <text x={pad.l - 4} y={y + 3} textAnchor="end" className="fill-muted-foreground" fontSize={9}>
                {v}h
              </text>
            </g>
          )
        })}

        {/* Expected hours reference line */}
        {expectedLine > 0 && (
          <line
            x1={pad.l}
            x2={w - pad.r}
            y1={pad.t + ih - (expectedLine / yMax) * ih}
            y2={pad.t + ih - (expectedLine / yMax) * ih}
            stroke="hsl(142, 76%, 36%)"
            strokeOpacity={0.3}
            strokeDasharray="4 3"
          />
        )}

        {/* Bars */}
        {data.map((d, i) => {
          const x = pad.l + gap + i * (barWidth + gap)
          const barH = (d.hours / yMax) * ih
          const y = pad.t + ih - barH
          const color = d.hours === 0
            ? 'hsl(0, 0%, 80%)'
            : d.hours >= d.expected
              ? 'hsl(142, 76%, 36%)'
              : d.hours >= d.expected * 0.75
                ? 'hsl(38, 92%, 50%)'
                : 'hsl(0, 72%, 51%)'

          return (
            <g key={i}>
              {/* Absent placeholder */}
              {d.hours === 0 && (
                <rect x={x} y={pad.t + ih - 2} width={barWidth} height={2} rx={1} fill="currentColor" fillOpacity={0.1} />
              )}
              {d.hours > 0 && (
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={Math.max(barH, 1)}
                  rx={2}
                  fill={color}
                  fillOpacity={0.8}
                />
              )}
              {/* Hours label on top (skip for compact with 0) */}
              {(!compact || d.hours > 0) && (
                <text
                  x={x + barWidth / 2}
                  y={d.hours > 0 ? y - 3 : pad.t + ih - 6}
                  textAnchor="middle"
                  className="fill-muted-foreground"
                  fontSize={compact ? 7 : 9}
                >
                  {d.hours > 0 ? d.hours.toFixed(1) : ''}
                </text>
              )}
              {/* Day label */}
              <text
                x={x + barWidth / 2}
                y={h - (compact ? 4 : 4)}
                textAnchor="middle"
                className="fill-muted-foreground"
                fontSize={compact ? 6.5 : 8}
                transform={compact ? `rotate(-45, ${x + barWidth / 2}, ${h - 4})` : undefined}
              >
                {d.label}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// ── Punch Timeline Line ──

function PunchLine({ punch, isFirst, isLast }: { punch: BioStarPunchLog; isFirst: boolean; isLast: boolean }) {
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
