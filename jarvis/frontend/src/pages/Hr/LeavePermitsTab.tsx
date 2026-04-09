import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Upload, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { connecteamApi } from '@/api/connecteam'
import type { ConnecteamSubmission } from '@/api/connecteam'
import { toast } from 'sonner'

const now = new Date()

export default function LeavePermitsTab({ search }: { search: string }) {
  const qc = useQueryClient()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const { data: statusData } = useQuery({
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

  // Filter by search only (year/month filtering is server-side)
  const filtered = useMemo(() => {
    if (!recentData) return []
    if (!search) return recentData
    const q = search.toLowerCase()
    return recentData.filter((s) => {
      const name = (s.connecteam_user_name || '').toLowerCase()
      const reason = (s.leave_reason || '').toLowerCase()
      return name.includes(q) || reason.includes(q)
    })
  }, [recentData, search])

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
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={prevMonth}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium capitalize w-40 text-center">{monthLabel}</span>
          <Button variant="ghost" size="icon" onClick={nextMonth}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {statusData?.total_submissions ?? 0} total
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
                <TableHead>Name</TableHead>
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
              {filtered.map((s) => (
                <TableRow key={s.submission_id}>
                  <TableCell className="font-medium whitespace-nowrap">
                    {s.connecteam_user_name || `User #${s.connecteam_user_id}`}
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {s.leave_date
                      ? new Date(s.leave_date + 'T00:00').toLocaleDateString('ro-RO')
                      : '-'}
                  </TableCell>
                  <TableCell>{s.leave_start_time?.slice(0, 5) || '-'}</TableCell>
                  <TableCell>{s.leave_end_time?.slice(0, 5) || '-'}</TableCell>
                  <TableCell>{s.leave_hours != null ? s.leave_hours : '-'}</TableCell>
                  <TableCell className="max-w-[200px] truncate">{s.leave_reason || '-'}</TableCell>
                  <TableCell className="whitespace-nowrap">{s.approved_by || '-'}</TableCell>
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
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
