import { useState, useMemo, useEffect, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Upload, Download, ChevronLeft, ChevronRight, ChevronDown, Info, MoreHorizontal, Pencil, Archive, Trash2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { connecteamApi } from '@/api/connecteam'
import type { ConnecteamSubmission, ConversionRequest, HrLeaveEdit, LeaveView } from '@/api/connecteam'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'

const TRASH_RETENTION_DAYS = 7
const VIEW_TABS: { key: LeaveView; label: string }[] = [
  { key: 'active', label: 'Active' },
  { key: 'archived', label: 'Arhivate' },
  { key: 'trashed', label: 'Coș' },
]

/** Days remaining before an item in Trash is auto-purged (0 = purges today). */
function trashDaysLeft(deletedAt?: string | null): number {
  if (!deletedAt) return TRASH_RETENTION_DAYS
  const deleted = new Date(deletedAt.replace(' ', 'T')).getTime()
  if (Number.isNaN(deleted)) return TRASH_RETENTION_DAYS
  const elapsedDays = (Date.now() - deleted) / 86_400_000
  return Math.max(0, Math.ceil(TRASH_RETENTION_DAYS - elapsedDays))
}

const now = new Date()

export default function LeavePermitsTab({ search }: { search: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [companyFilter, setCompanyFilter] = useState<string>('all')
  const [collapsedEmployees, setCollapsedEmployees] = useState<Set<string>>(new Set())
  const [view, setView] = useState<LeaveView>('active')
  const [editing, setEditing] = useState<ConnecteamSubmission | null>(null)
  const [exporting, setExporting] = useState(false)

  useQuery({
    queryKey: ['connecteam', 'status'],
    queryFn: () => connecteamApi.getStatus().then(r => r.data),
  })

  const { data: recentData, isLoading } = useQuery({
    queryKey: ['connecteam', 'submissions', year, month, view],
    queryFn: () =>
      fetch(`/connecteam/api/submissions/recent?year=${year}&month=${month}&limit=500&view=${view}`, { credentials: 'include' })
        .then(r => r.json())
        .then(r => r.data as ConnecteamSubmission[]),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['connecteam', 'submissions'] })

  const archiveMut = useMutation({
    mutationFn: ({ source, id }: { source: 'jarvis' | 'connecteam'; id: number }) =>
      connecteamApi.hrArchiveLeave(source, id),
    onSuccess: (_res, vars) => {
      invalidate()
      toast.success('Bilet arhivat', {
        action: { label: 'Anulează', onClick: () => restoreMut.mutate(vars) },
      })
    },
    onError: () => toast.error('Arhivarea a eșuat'),
  })

  const deleteMut = useMutation({
    mutationFn: ({ source, id }: { source: 'jarvis' | 'connecteam'; id: number }) =>
      connecteamApi.hrDeleteLeave(source, id),
    onSuccess: (_res, vars) => {
      invalidate()
      toast.success(`Bilet mutat în Coș · se șterge în ${TRASH_RETENTION_DAYS} zile`, {
        action: { label: 'Anulează', onClick: () => restoreMut.mutate(vars) },
      })
    },
    onError: () => toast.error('Ștergerea a eșuat'),
  })

  const restoreMut = useMutation({
    mutationFn: ({ source, id }: { source: 'jarvis' | 'connecteam'; id: number }) =>
      connecteamApi.hrRestoreLeave(source, id),
    onSuccess: () => { invalidate(); toast.success('Bilet restaurat') },
    onError: () => toast.error('Restaurarea a eșuat'),
  })

  const editMut = useMutation({
    mutationFn: ({ source, id, fields }: { source: 'jarvis' | 'connecteam'; id: number; fields: HrLeaveEdit }) =>
      connecteamApi.hrUpdateLeave(source, id, fields),
    onSuccess: () => { invalidate(); setEditing(null); toast.success('Bilet actualizat') },
    onError: (e: unknown) => {
      const msg = (e as { data?: { error?: string } })?.data?.error
      toast.error(msg || 'Actualizarea a eșuat')
    },
  })

  // Fetch existing conversions for status display
  const { data: conversions } = useQuery({
    queryKey: ['connecteam', 'conversions', year, month],
    queryFn: () => connecteamApi.getConversions(year, month),
  })

  const importMut = useMutation({
    mutationFn: (file: File) => connecteamApi.importExcel(file),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['connecteam', 'submissions'] })
      qc.invalidateQueries({ queryKey: ['connecteam', 'status'] })
      const d = res.data
      if (d.inserted > 0) {
        toast.success(`Imported ${d.inserted} submissions (${d.skipped} skipped)`)
      } else if (d.skipped > 0) {
        toast.info(`All ${d.skipped} submissions already imported`)
      } else {
        toast.info('No data found in file')
      }
    },
    onError: () => toast.error('Import failed'),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      importMut.mutate(file)
      e.target.value = ''
    }
  }

  const companies = useMemo(() => {
    if (!recentData) return []
    const set = new Set<string>()
    for (const s of recentData) {
      if (s.jarvis_user_company) set.add(s.jarvis_user_company)
    }
    return Array.from(set).sort()
  }, [recentData])

  const filtered = useMemo(() => {
    if (!recentData) return []
    return recentData.filter((s) => {
      if (companyFilter !== 'all' && (s.jarvis_user_company || '') !== companyFilter) return false
      if (!search) return true
      const q = search.toLowerCase()
      const name = (s.connecteam_user_name || '').toLowerCase()
      const reason = (s.leave_reason || '').toLowerCase()
      return name.includes(q) || reason.includes(q)
    })
  }, [recentData, search, companyFilter])

  const grouped = useMemo(() => {
    const map = new Map<string, { submissions: ConnecteamSubmission[]; totalHours: number; company: string | null; userId: number | null }>()
    for (const s of filtered) {
      const key = s.connecteam_user_name || `User #${s.connecteam_user_id}`
      if (!map.has(key)) {
        map.set(key, { submissions: [], totalHours: 0, company: s.jarvis_user_company ?? null, userId: s.mapped_jarvis_user_id })
      }
      const group = map.get(key)!
      group.submissions.push(s)
      group.totalHours += s.leave_hours ?? 0
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [filtered])

  const conversionsByUser = useMemo(() => {
    const map = new Map<number, ConversionRequest>()
    if (conversions) {
      for (const c of conversions) {
        map.set(c.employee_user_id, c)
      }
    }
    return map
  }, [conversions])

  const toggleEmployee = (name: string) => {
    setCollapsedEmployees(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const collapseAll = () => setCollapsedEmployees(new Set(grouped.map(([name]) => name)))
  const expandAll = () => setCollapsedEmployees(new Set())

  const monthLabel = new Date(year, month - 1).toLocaleString('ro-RO', { month: 'long', year: 'numeric' })

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(y => y - 1) }
    else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(y => y + 1) }
    else setMonth(m => m + 1)
  }

  const handleExport = async () => {
    if (filtered.length === 0) {
      toast.info('Nu există bilete de exportat')
      return
    }
    setExporting(true)
    try {
      const XLSX = await import('xlsx')
      const header = ['Nume', 'Companie', 'Data', 'Început', 'Sfârșit', 'Ore', 'Motiv', 'Aprobat de', 'Status', 'Sursă']
      const rows: (string | number)[][] = [header]
      // Flat rows, ordered by employee to match the on-screen grouping.
      for (const [employeeName, { submissions }] of grouped) {
        for (const s of submissions) {
          rows.push([
            employeeName,
            s.jarvis_user_company?.replace(' S.R.L.', '') || '',
            s.leave_date ? new Date(s.leave_date + 'T00:00').toLocaleDateString('ro-RO') : '',
            s.leave_start_time?.slice(0, 5) || '',
            s.leave_end_time?.slice(0, 5) || '',
            s.leave_hours != null ? s.leave_hours : '',
            s.leave_reason || '',
            s.approved_by || '',
            s.status || '',
            s.source === 'jarvis' ? 'JARVIS' : 'Connecteam',
          ])
        }
      }
      const ws = XLSX.utils.aoa_to_sheet(rows)
      ws['!cols'] = [
        { wch: 24 }, { wch: 20 }, { wch: 12 }, { wch: 8 }, { wch: 8 },
        { wch: 6 }, { wch: 24 }, { wch: 20 }, { wch: 12 }, { wch: 12 },
      ]
      const wb = XLSX.utils.book_new()
      XLSX.utils.book_append_sheet(wb, ws, 'Bilete')
      const viewSuffix = view === 'archived' ? '_arhivate' : view === 'trashed' ? '_cos' : ''
      const fileName = `bilete_invoire_${year}-${String(month).padStart(2, '0')}${viewSuffix}.xlsx`
      XLSX.writeFile(wb, fileName)
      toast.success('Export finalizat')
    } catch (err) {
      console.error('[LeavePermits Export] failed:', err)
      toast.error('Exportul a eșuat')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* CO Conversion notice */}
      <div className="flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 px-3 py-2">
        <Info className="h-4 w-4 text-blue-600 dark:text-blue-400 shrink-0" />
        <span className="text-xs text-blue-700 dark:text-blue-300">
          CO Conversion has moved to the{' '}
          <button
            type="button"
            className="font-medium underline hover:no-underline"
            onClick={() => navigate('/app/hr/time-bank')}
          >
            Time Bank
          </button>{' '}
          tab.
        </span>
      </div>

      {/* Header bar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={prevMonth}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium capitalize w-40 text-center">{monthLabel}</span>
          <Button variant="ghost" size="icon" onClick={nextMonth}>
            <ChevronRight className="h-4 w-4" />
          </Button>

          {companies.length > 0 && (
            <Select value={companyFilter} onValueChange={setCompanyFilter}>
              <SelectTrigger className="w-[200px] h-8 text-xs">
                <SelectValue placeholder="All Companies" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Companies</SelectItem>
                {companies.map(c => (
                  <SelectItem key={c} value={c}>{c.replace(' S.R.L.', '')}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-md border p-0.5 bg-muted/40">
            {VIEW_TABS.map(t => (
              <button
                key={t.key}
                type="button"
                onClick={() => setView(t.key)}
                className={`h-7 px-2.5 text-xs rounded-[5px] transition-colors ${
                  view === t.key
                    ? 'bg-background shadow-sm font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {grouped.length > 1 && (
            <div className="flex gap-1">
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={expandAll}>Expand All</Button>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={collapseAll}>Collapse All</Button>
            </div>
          )}
          <span className="text-xs text-muted-foreground">
            {filtered.length} permits · {grouped.length} employees
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={handleExport}
            disabled={exporting || filtered.length === 0}
            title="Exportă biletele filtrate în Excel"
          >
            {exporting
              ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              : <Download className="mr-1.5 h-4 w-4" />}
            Export
          </Button>
          <input
            type="file"
            accept=".xlsx"
            className="hidden"
            id="leave-permits-import"
            onChange={handleFileChange}
          />
          <Button
            size="sm"
            onClick={() => document.getElementById('leave-permits-import')?.click()}
            disabled={importMut.isPending}
          >
            {importMut.isPending
              ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              : <Upload className="mr-1.5 h-4 w-4" />}
            {importMut.isPending ? 'Importing...' : 'Import Connecteam'}
          </Button>
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          {view === 'archived' ? `Niciun bilet arhivat pentru ${monthLabel}`
            : view === 'trashed' ? `Coșul este gol pentru ${monthLabel}`
            : `No submissions for ${monthLabel}`}
        </div>
      ) : (
        <div className="rounded-md border overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Name</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Start</TableHead>
                <TableHead>End</TableHead>
                <TableHead>Hours</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Approved By</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {grouped.map(([employeeName, { submissions, totalHours, company, userId }]) => {
                const isCollapsed = collapsedEmployees.has(employeeName)
                const existingConversion = userId ? conversionsByUser.get(userId) : undefined
                return (
                  <Fragment key={employeeName}>
                    {/* Employee group header */}
                    <TableRow
                      className="bg-muted/40 hover:bg-muted/60 cursor-pointer"
                      onClick={() => toggleEmployee(employeeName)}
                    >
                      <TableCell className="w-8 px-2">
                        {isCollapsed
                          ? <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                          : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
                      </TableCell>
                      <TableCell className="font-medium whitespace-nowrap">{employeeName}</TableCell>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{company?.replace(' S.R.L.', '') || '—'}</TableCell>
                      <TableCell colSpan={3} className="text-xs text-muted-foreground">
                        {submissions.length} permit{submissions.length !== 1 ? 's' : ''}
                      </TableCell>
                      <TableCell className="text-xs font-medium tabular-nums">{totalHours}h</TableCell>
                      <TableCell colSpan={2} />
                      <TableCell className="text-center">
                        {existingConversion ? (
                          <ConversionStatusBadge conversion={existingConversion} />
                        ) : null}
                      </TableCell>
                      <TableCell />
                      <TableCell />
                    </TableRow>
                    {/* Submission rows */}
                    {!isCollapsed && submissions.map((s) => (
                      <TableRow
                        key={s.submission_id}
                        className={`hover:bg-muted/20 ${
                          s.deleted_at
                            ? 'opacity-70 bg-red-50/40 dark:bg-red-950/10'
                            : s.archived_at ? 'opacity-60' : ''
                        }`}
                      >
                        <TableCell className="w-8 px-2" />
                        <TableCell className="pl-6 text-xs text-muted-foreground whitespace-nowrap">
                          <span className="inline-flex items-center gap-1.5">
                            <span className="w-1 h-1 rounded-full bg-primary/40 shrink-0" />
                            {s.connecteam_user_name || `User #${s.connecteam_user_id}`}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{s.jarvis_user_company?.replace(' S.R.L.', '') || '—'}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs">
                          {s.leave_date
                            ? new Date(s.leave_date + 'T00:00').toLocaleDateString('ro-RO')
                            : '-'}
                        </TableCell>
                        <TableCell className="text-xs">{s.leave_start_time?.slice(0, 5) || '-'}</TableCell>
                        <TableCell className="text-xs">{s.leave_end_time?.slice(0, 5) || '-'}</TableCell>
                        <TableCell className="text-xs tabular-nums">{s.leave_hours != null ? s.leave_hours : '-'}</TableCell>
                        <TableCell className="max-w-[200px] truncate text-xs">{s.leave_reason || '-'}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs">{s.approved_by || '-'}</TableCell>
                        <TableCell>
                          <StatusBadge
                            status={
                              s.status === 'approved' ? 'active' :
                              s.status === 'rejected' ? 'error' :
                              s.status === 'converted' ? 'info' :
                              s.status
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                            s.source === 'jarvis'
                              ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                              : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                          }`}>
                            {s.source === 'jarvis' ? 'JARVIS' : 'Connecteam'}
                          </span>
                          {s.deleted_at && (
                            <span className="ml-1.5 text-[10px] text-red-600 dark:text-red-400 whitespace-nowrap">
                              se șterge în {trashDaysLeft(s.deleted_at)} {trashDaysLeft(s.deleted_at) === 1 ? 'zi' : 'zile'}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="w-8 px-1">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-7 w-7">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              {s.deleted_at ? (
                                <DropdownMenuItem
                                  onClick={() => restoreMut.mutate({ source: (s.source ?? 'connecteam'), id: s.id })}
                                >
                                  <RotateCcw className="mr-2 h-3.5 w-3.5" /> Restaurează
                                </DropdownMenuItem>
                              ) : (
                                <>
                                  <DropdownMenuItem onClick={() => setEditing(s)}>
                                    <Pencil className="mr-2 h-3.5 w-3.5" /> Editează
                                  </DropdownMenuItem>
                                  {s.archived_at ? (
                                    <DropdownMenuItem
                                      onClick={() => restoreMut.mutate({ source: (s.source ?? 'connecteam'), id: s.id })}
                                    >
                                      <RotateCcw className="mr-2 h-3.5 w-3.5" /> Restaurează
                                    </DropdownMenuItem>
                                  ) : (
                                    <DropdownMenuItem
                                      onClick={() => archiveMut.mutate({ source: (s.source ?? 'connecteam'), id: s.id })}
                                    >
                                      <Archive className="mr-2 h-3.5 w-3.5" /> Arhivează
                                    </DropdownMenuItem>
                                  )}
                                  <DropdownMenuItem
                                    className="text-red-600 focus:text-red-600"
                                    onClick={() => deleteMut.mutate({ source: (s.source ?? 'connecteam'), id: s.id })}
                                  >
                                    <Trash2 className="mr-2 h-3.5 w-3.5" /> Șterge
                                  </DropdownMenuItem>
                                </>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <EditLeaveDialog
        submission={editing}
        onClose={() => setEditing(null)}
        onSave={(fields) => {
          if (!editing) return
          editMut.mutate({ source: (editing.source ?? 'connecteam'), id: editing.id, fields })
        }}
        saving={editMut.isPending}
      />
    </div>
  )
}

function EditLeaveDialog({
  submission, onClose, onSave, saving,
}: {
  submission: ConnecteamSubmission | null
  onClose: () => void
  onSave: (fields: HrLeaveEdit) => void
  saving: boolean
}) {
  const [date, setDate] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [reason, setReason] = useState('')

  // Prefill each time a new submission is opened for editing.
  useEffect(() => {
    if (!submission) return
    setDate(submission.leave_date || '')
    setStart(submission.leave_start_time?.slice(0, 5) || '')
    setEnd(submission.leave_end_time?.slice(0, 5) || '')
    setReason(submission.leave_reason || '')
  }, [submission])

  const valid = date && start && end && end > start

  return (
    <Dialog open={!!submission} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Editează bilet de învoire</DialogTitle>
          <DialogDescription>
            {submission?.connecteam_user_name || ''} · modifici detaliile biletului.
            Statusul aprobării nu se schimbă.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="hr-leave-date" className="text-xs">Data</Label>
            <Input id="hr-leave-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="hr-leave-start" className="text-xs">Început</Label>
              <Input id="hr-leave-start" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="hr-leave-end" className="text-xs">Sfârșit</Label>
              <Input id="hr-leave-end" type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          {!!start && !!end && end <= start && (
            <p className="text-xs text-red-600">Ora de sfârșit trebuie să fie după ora de început.</p>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="hr-leave-reason" className="text-xs">Motiv</Label>
            <Input id="hr-leave-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Personal, Medical…" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Anulează</Button>
          <Button
            disabled={!valid || saving}
            onClick={() => onSave({ leave_date: date, leave_start_time: start, leave_end_time: end, leave_reason: reason })}
          >
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            Salvează
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ConversionStatusBadge({ conversion }: { conversion: ConversionRequest }) {
  switch (conversion.status) {
    case 'pending':
      return (
        <Badge variant="outline" className="text-[10px] border-yellow-300 text-yellow-600 bg-yellow-50 dark:bg-yellow-950/30">
          CO pending ({conversion.co_days_requested}d)
        </Badge>
      )
    case 'approved':
      return (
        <Badge variant="outline" className="text-[10px] border-green-300 text-green-600 bg-green-50 dark:bg-green-950/30">
          {conversion.co_days_requested}d converted
        </Badge>
      )
    case 'rejected':
      return (
        <Badge variant="outline" className="text-[10px] border-red-300 text-red-600 bg-red-50 dark:bg-red-950/30">
          CO rejected
        </Badge>
      )
    default:
      return null
  }
}
