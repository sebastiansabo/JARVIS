import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Info, Play, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { verificationApi, type VerificationDiscrepancy } from '@/api/verification'
import { sincronApi } from '@/api/sincron'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const TYPE_LABELS: Record<string, string> = {
  leave_but_punched: 'Leave + Punch',
  work_day_no_punch: 'Work, No Punch',
  hours_mismatch: 'Hours Mismatch',
  no_biostar_mapping: 'No BioStar Link',
}

const TYPE_DESC: Record<string, string> = {
  leave_but_punched: 'Sincron shows leave, but BioStar recorded a punch',
  work_day_no_punch: 'Sincron shows work day, but no BioStar punches found',
  hours_mismatch: 'Monthly hours differ by more than 2h between Sincron and BioStar',
  no_biostar_mapping: 'Employee is in Sincron but has no BioStar mapping',
}

function SeverityBadge({ discrepancy }: { discrepancy: VerificationDiscrepancy }) {
  const { severity, discrepancy_type, sincron_value, biostar_value, jarvis_value } = discrepancy

  let label = ''
  if (discrepancy_type === 'hours_mismatch') {
    const delta = (jarvis_value as Record<string, number> | null)?.delta
    const sincronH = (sincron_value as Record<string, number> | null)?.hours ?? 0
    const biostarH = (biostar_value as Record<string, number> | null)?.hours ?? 0
    const dir = sincronH > biostarH ? 'Sincron +' : 'BioStar +'
    label = delta != null ? `${dir}${delta}h` : 'Hours diff'
  } else if (discrepancy_type === 'work_day_no_punch') {
    label = 'No punch'
  } else if (discrepancy_type === 'leave_but_punched') {
    const dur = (biostar_value as Record<string, number> | null)?.duration_seconds
    label = dur ? `Punched ${Math.round(dur / 3600 * 10) / 10}h` : 'Punched on leave'
  } else if (discrepancy_type === 'no_biostar_mapping') {
    label = 'Not linked'
  } else {
    label = severity
  }

  if (severity === 'error') return <Badge variant="destructive" className="gap-1"><XCircle className="h-3 w-3" />{label}</Badge>
  if (severity === 'warning') return <Badge variant="outline" className="gap-1 text-yellow-600 border-yellow-400"><AlertTriangle className="h-3 w-3" />{label}</Badge>
  return <Badge variant="secondary" className="gap-1"><Info className="h-3 w-3" />{label}</Badge>
}

function SyncStatusPanel({ year, month }: { year: number; month: number }) {
  const { data: statuses = [], isLoading } = useQuery({
    queryKey: ['sincron', 'sync-status-per-company', year, month],
    queryFn: () => sincronApi.getSyncStatusPerCompany(year, month),
    staleTime: 60_000,
  })

  if (isLoading) return <Skeleton className="h-8 w-full" />
  if (!statuses.length) return (
    <p className="text-xs text-muted-foreground">No sync runs found for this month.</p>
  )

  return (
    <div className="flex flex-wrap gap-2">
      {statuses.map((s) => {
        const ok = s.status === 'completed'
        const failed = s.status === 'failed'
        const shortName = s.company_name.replace('AUTOWORLD ', 'AW ')
        return (
          <div
            key={s.company_name}
            title={failed ? (s.error_message ?? 'Failed') : `${s.employees_synced ?? 0} employees synced`}
            className={cn(
              'flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
              ok && 'border-green-400/50 bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300',
              failed && 'border-red-400/50 bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
              !ok && !failed && 'border-gray-300 bg-gray-50 text-gray-500',
            )}
          >
            {ok ? <CheckCircle2 className="h-3 w-3" /> : failed ? <XCircle className="h-3 w-3" /> : <Info className="h-3 w-3" />}
            {shortName}
          </div>
        )
      })}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={cn('text-2xl font-bold mt-1', color)}>{value}</p>
      </CardContent>
    </Card>
  )
}

export default function VerificationTab() {
  const queryClient = useQueryClient()
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [severityFilter, setSeverityFilter] = useState<string>('all')
  const [showResolved, setShowResolved] = useState(false)
  const [resolveTarget, setResolveTarget] = useState<VerificationDiscrepancy | null>(null)
  const [resolveNotes, setResolveNotes] = useState('')

  const qKey = ['verification', 'results', year, month, showResolved]

  const { data, isLoading } = useQuery({
    queryKey: qKey,
    queryFn: () => verificationApi.getResults(year, month, showResolved),
  })

  const run = data?.run ?? null
  const allDiscrepancies = data?.data ?? []

  const displayed = allDiscrepancies.filter((d) => {
    if (typeFilter !== 'all' && d.discrepancy_type !== typeFilter) return false
    if (severityFilter !== 'all' && d.severity !== severityFilter) return false
    return true
  })

  const runMut = useMutation({
    mutationFn: () => verificationApi.runVerification(year, month),
    onSuccess: (res) => {
      const count = res.data?.discrepancy_count ?? 0
      toast.success(`Verification complete — ${count} discrepancies found`)
      queryClient.invalidateQueries({ queryKey: ['verification'] })
    },
    onError: () => toast.error('Verification run failed'),
  })

  const resolveMut = useMutation({
    mutationFn: ({ id, notes }: { id: number; notes: string }) =>
      verificationApi.resolveDiscrepancy(id, notes),
    onSuccess: () => {
      toast.success('Marked as resolved')
      setResolveTarget(null)
      setResolveNotes('')
      queryClient.invalidateQueries({ queryKey: ['verification'] })
    },
    onError: () => toast.error('Failed to resolve'),
  })

  const summary = run?.summary ?? {}
  const bySeverity = summary.by_severity ?? {}
  const byType = summary.by_type ?? {}

  const years = Array.from({ length: 3 }, (_, i) => now.getFullYear() - i)

  return (
    <div className="space-y-5">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
          <SelectTrigger className="w-24 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
          </SelectContent>
        </Select>

        <Select value={String(month)} onValueChange={(v) => setMonth(Number(v))}>
          <SelectTrigger className="w-32 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {MONTHS.map((m, i) => <SelectItem key={i + 1} value={String(i + 1)}>{m}</SelectItem>)}
          </SelectContent>
        </Select>

        <Button
          size="sm"
          className="h-8 text-xs"
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
        >
          {runMut.isPending
            ? <><RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />Running…</>
            : <><Play className="mr-1.5 h-3.5 w-3.5" />Run Verification</>
          }
        </Button>

        {run && (
          <span className="text-xs text-muted-foreground ml-auto">
            Last run: {new Date(run.started_at).toLocaleString()} — {run.status}
          </span>
        )}
      </div>

      {/* Sincron sync status */}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5" /> Sincron Sync Status — {MONTHS[month - 1]} {year}
        </p>
        <SyncStatusPanel year={year} month={month} />
      </div>

      {/* Summary cards */}
      {run && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Total" value={summary.total ?? 0} color="text-foreground" />
          <StatCard label="Errors" value={bySeverity['error'] ?? 0} color="text-red-600" />
          <StatCard label="Warnings" value={bySeverity['warning'] ?? 0} color="text-yellow-600" />
          <StatCard label="Info" value={bySeverity['info'] ?? 0} color="text-blue-600" />
        </div>
      )}

      {/* Type breakdown */}
      {run && Object.keys(byType).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(byType).map(([type, count]) => (
            <button
              key={type}
              onClick={() => setTypeFilter(t => t === type ? 'all' : type)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                typeFilter === type
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border hover:bg-muted',
              )}
              title={TYPE_DESC[type]}
            >
              {TYPE_LABELS[type] ?? type}: {count}
            </button>
          ))}
          {typeFilter !== 'all' && (
            <button onClick={() => setTypeFilter('all')} className="text-xs text-muted-foreground hover:text-foreground px-2">
              Clear filter ×
            </button>
          )}
        </div>
      )}

      {/* Filters bar */}
      {allDiscrepancies.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Select value={severityFilter} onValueChange={setSeverityFilter}>
            <SelectTrigger className="w-32 h-7 text-xs"><SelectValue placeholder="All severities" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All severities</SelectItem>
              <SelectItem value="error">Errors</SelectItem>
              <SelectItem value="warning">Warnings</SelectItem>
              <SelectItem value="info">Info</SelectItem>
            </SelectContent>
          </Select>

          <button
            onClick={() => setShowResolved((p) => !p)}
            className={cn(
              'text-xs px-3 py-1 rounded-full border transition-colors',
              showResolved ? 'bg-muted border-border' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {showResolved ? 'Hiding resolved' : 'Show resolved'}
          </button>

          <span className="ml-auto text-xs text-muted-foreground">{displayed.length} items</span>
        </div>
      )}

      {/* Main table */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      ) : !run ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
          <ShieldCheck className="h-10 w-10 opacity-30" />
          <p className="text-sm">No verification run yet for {MONTHS[month - 1]} {year}.</p>
          <Button size="sm" variant="outline" onClick={() => runMut.mutate()} disabled={runMut.isPending}>
            Run now
          </Button>
        </div>
      ) : displayed.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
          <CheckCircle2 className="h-10 w-10 text-green-500 opacity-60" />
          <p className="text-sm">No discrepancies{typeFilter !== 'all' ? ' for this filter' : ''}.</p>
        </div>
      ) : (
        <div className="rounded-md border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-40">Employee</TableHead>
                <TableHead className="w-36">Company</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="w-24">Day</TableHead>
                <TableHead>Sincron</TableHead>
                <TableHead>BioStar</TableHead>
                <TableHead className="w-20">Severity</TableHead>
                <TableHead className="w-20">Status</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayed.map((d) => (
                <TableRow key={d.id} className={cn(d.is_resolved && 'opacity-50')}>
                  <TableCell className="font-medium text-sm">{d.employee_name ?? '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {d.company_name?.replace('AUTOWORLD ', 'AW ') ?? '—'}
                  </TableCell>
                  <TableCell>
                    <span className="text-xs" title={TYPE_DESC[d.discrepancy_type]}>
                      {TYPE_LABELS[d.discrepancy_type] ?? d.discrepancy_type}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs">{d.day ?? '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    <DiscrepancyValue val={d.sincron_value} type={d.discrepancy_type} side="sincron" />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    <DiscrepancyValue val={d.biostar_value} type={d.discrepancy_type} side="biostar" />
                  </TableCell>
                  <TableCell><SeverityBadge discrepancy={d} /></TableCell>
                  <TableCell>
                    {d.is_resolved
                      ? <Badge variant="secondary" className="text-green-600 gap-1"><CheckCircle2 className="h-3 w-3" />Fixed</Badge>
                      : <Badge variant="outline" className="text-muted-foreground">Open</Badge>
                    }
                  </TableCell>
                  <TableCell>
                    {!d.is_resolved && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => { setResolveTarget(d); setResolveNotes('') }}
                      >
                        Resolve
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Resolve dialog */}
      <Dialog open={!!resolveTarget} onOpenChange={(open) => { if (!open) setResolveTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mark as Resolved</DialogTitle>
          </DialogHeader>
          {resolveTarget && (
            <div className="space-y-3 text-sm">
              <p>
                <span className="font-medium">{resolveTarget.employee_name}</span>
                {resolveTarget.day && <span className="text-muted-foreground"> — {resolveTarget.day}</span>}
              </p>
              <p className="text-muted-foreground">{TYPE_LABELS[resolveTarget.discrepancy_type] ?? resolveTarget.discrepancy_type}</p>
              <Textarea
                placeholder="Optional notes (e.g. confirmed correct, data entry error…)"
                value={resolveNotes}
                onChange={(e) => setResolveNotes(e.target.value)}
                rows={3}
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setResolveTarget(null)}>Cancel</Button>
            <Button
              onClick={() => resolveTarget && resolveMut.mutate({ id: resolveTarget.id, notes: resolveNotes })}
              disabled={resolveMut.isPending}
            >
              Mark Resolved
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function DiscrepancyValue({
  val, type, side,
}: {
  val: Record<string, unknown> | null
  type: string
  side: 'sincron' | 'biostar'
}) {
  if (!val) return <span>—</span>

  if (type === 'hours_mismatch') {
    return <span>{val.hours as number}h</span>
  }

  if (type === 'leave_but_punched') {
    if (side === 'sincron') return <span>{(val.codes as string[])?.join(', ')}</span>
    const dur = val.duration_seconds as number
    const h = Math.floor(dur / 3600)
    const m = Math.floor((dur % 3600) / 60)
    return <span>{h}h {m}m</span>
  }

  if (type === 'work_day_no_punch') {
    if (side === 'sincron') return <span>{(val.codes as string[])?.join(', ')}</span>
    return <span>No punches</span>
  }

  return <span>—</span>
}
