import { useState, useMemo, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Upload, ChevronLeft, ChevronRight, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { connecteamApi } from '@/api/connecteam'
import type { ConnecteamSubmission } from '@/api/connecteam'
import { toast } from 'sonner'

const now = new Date()

export default function LeavePermitsTab({ search }: { search: string }) {
  const qc = useQueryClient()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [companyFilter, setCompanyFilter] = useState<string>('all')
  const [collapsedEmployees, setCollapsedEmployees] = useState<Set<string>>(new Set())

  useQuery({
    queryKey: ['connecteam', 'status'],
    queryFn: () => connecteamApi.getStatus().then(r => r.data),
  })

  // Fetch submissions for the selected month (server-side filtered)
  const { data: recentData, isLoading } = useQuery({
    queryKey: ['connecteam', 'submissions', year, month],
    queryFn: () =>
      fetch(`/connecteam/api/submissions/recent?year=${year}&month=${month}&limit=500`, { credentials: 'include' })
        .then(r => r.json())
        .then(r => r.data as ConnecteamSubmission[]),
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

  // Unique companies for the filter
  const companies = useMemo(() => {
    if (!recentData) return []
    const set = new Set<string>()
    for (const s of recentData) {
      if (s.jarvis_user_company) set.add(s.jarvis_user_company)
    }
    return Array.from(set).sort()
  }, [recentData])

  // Filter by search + company
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

  // Group by employee name
  const grouped = useMemo(() => {
    const map = new Map<string, { submissions: ConnecteamSubmission[]; totalHours: number; company: string | null }>()
    for (const s of filtered) {
      const key = s.connecteam_user_name || `User #${s.connecteam_user_id}`
      if (!map.has(key)) {
        map.set(key, { submissions: [], totalHours: 0, company: s.jarvis_user_company ?? null })
      }
      const group = map.get(key)!
      group.submissions.push(s)
      group.totalHours += s.leave_hours ?? 0
    }
    // Sort by name
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [filtered])

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

  return (
    <div className="space-y-4">
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

          {/* Company filter */}
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
          {grouped.length > 1 && (
            <div className="flex gap-1">
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={expandAll}>Expand All</Button>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={collapseAll}>Collapse All</Button>
            </div>
          )}
          <span className="text-xs text-muted-foreground">
            {filtered.length} permits · {grouped.length} employees
          </span>
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
          No submissions for {monthLabel}
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {grouped.map(([employeeName, { submissions, totalHours, company }]) => {
                const isCollapsed = collapsedEmployees.has(employeeName)
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
                      <TableCell colSpan={4} />
                    </TableRow>
                    {/* Submission rows */}
                    {!isCollapsed && submissions.map((s) => (
                      <TableRow key={s.submission_id} className="hover:bg-muted/20">
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
                            status={s.status === 'approved' ? 'active' : s.status === 'rejected' ? 'error' : s.status}
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
    </div>
  )
}
