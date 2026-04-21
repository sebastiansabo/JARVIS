import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { FileText, Link2, Search, Unlink, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { coursesApi } from '@/api/courses'
import { invoicesApi } from '@/api/invoices'
import { toast } from 'sonner'
import { useDebounce } from '@/lib/utils'
import type { Course, EnrollmentCost } from '@/types/courses'
import type { Invoice } from '@/types/invoices'
import { fmt, fmtDate } from './utils'

export function CostsTab({ course }: { course: Course }) {
  const queryClient = useQueryClient()
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)

  const { data: costData, isLoading: costsLoading } = useQuery({
    queryKey: ['course-enrollment-costs', course.id],
    queryFn: () => coursesApi.getEnrollmentCosts(course.id),
  })

  const { data: invoices = [], isLoading: invoicesLoading } = useQuery({
    queryKey: ['course-invoices', course.id],
    queryFn: () => coursesApi.getCourseInvoices(course.id),
  })

  const unlinkMutation = useMutation({
    mutationFn: (invoiceId: number) => coursesApi.unlinkInvoice(course.id, invoiceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-invoices', course.id] })
      toast.success('Invoice unlinked')
    },
  })

  const summary = costData?.summary
  const costs: EnrollmentCost[] = costData?.costs ?? []
  const loading = costsLoading || invoicesLoading
  if (loading) return <Skeleton className="h-32 w-full" />

  return (
    <div className="space-y-6">
      {/* Budget overview */}
      <div className="rounded-lg border p-4 space-y-3">
        <h3 className="font-semibold text-sm">Budget Overview</h3>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-xs text-muted-foreground">Planned Budget</div>
            <div className="text-lg font-bold tabular-nums">{course.budget ? fmt(course.budget, course.currency) : '—'}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Actual Cost</div>
            <div className="text-lg font-bold tabular-nums">{summary?.total_cost ? fmt(summary.total_cost, course.currency) : '—'}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Variance</div>
            {course.budget && summary?.total_cost ? (() => {
              const variance = Number(course.budget) - summary.total_cost
              return (
                <div className={`text-lg font-bold tabular-nums ${variance < 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {variance >= 0 ? '+' : ''}{fmt(variance, course.currency)}
                </div>
              )
            })() : <div className="text-lg font-bold">—</div>}
          </div>
        </div>

        {/* Execution bar */}
        {course.budget && Number(course.budget) > 0 && summary?.total_cost != null && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Budget Execution</span>
              <span>{Math.round((summary.total_cost / Number(course.budget)) * 100)}%</span>
            </div>
            <div className="h-2.5 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${summary.total_cost > Number(course.budget) ? 'bg-red-500' : 'bg-primary'}`}
                style={{ width: `${Math.min(100, (summary.total_cost / Number(course.budget)) * 100)}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Cost breakdown table */}
      {summary && summary.total_cost > 0 && (
        <div className="rounded-lg border p-4 space-y-3">
          <h3 className="font-semibold text-sm">Cost Breakdown ({summary.enrollment_count} enrollments)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 font-medium">Category</th>
                  <th className="text-right py-2 font-medium">Amount</th>
                  <th className="text-right py-2 font-medium">% of Total</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { label: 'Training Fee', val: summary.total_training_fee },
                  { label: 'Per Diem (Diurna)', val: summary.total_per_diem },
                  { label: 'Accommodation (Cazare)', val: summary.total_accommodation },
                  { label: 'Transport', val: summary.total_transport },
                  { label: 'Taxi', val: summary.total_taxi },
                ].map(row => (
                  <tr key={row.label} className="border-b last:border-0">
                    <td className="py-2">{row.label}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(row.val, course.currency)}</td>
                    <td className="py-2 text-right tabular-nums text-muted-foreground">
                      {summary.total_cost > 0 ? Math.round((row.val / summary.total_cost) * 100) : 0}%
                    </td>
                  </tr>
                ))}
                <tr className="font-semibold bg-muted/50">
                  <td className="py-2">Total</td>
                  <td className="py-2 text-right tabular-nums">{fmt(summary.total_cost, course.currency)}</td>
                  <td className="py-2 text-right">100%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Per-enrollment cost lines */}
      {costs.length > 0 && (
        <div className="rounded-lg border p-4 space-y-3">
          <h3 className="font-semibold text-sm">Cost Lines by Participant</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 font-medium">Employee</th>
                  <th className="text-left py-2 font-medium">Department</th>
                  <th className="text-right py-2 font-medium">Training</th>
                  <th className="text-right py-2 font-medium">Diurna</th>
                  <th className="text-right py-2 font-medium">Cazare</th>
                  <th className="text-right py-2 font-medium">Transport</th>
                  <th className="text-right py-2 font-medium">Taxi</th>
                  <th className="text-right py-2 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {costs.map(c => (
                  <tr key={c.enrollment_id} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="py-2 font-medium">{c.employee_name}</td>
                    <td className="py-2 text-muted-foreground">{c.enrollment_department ?? c.user_department ?? '—'}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.training_fee, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.per_diem, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.accommodation, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.transport, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.taxi, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums font-semibold">{fmt(c.total_cost, c.currency)}</td>
                  </tr>
                ))}
                {/* Totals row */}
                <tr className="font-semibold bg-muted/50">
                  <td className="py-2" colSpan={2}>Total ({costs.length} participants)</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.training_fee, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.per_diem, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.accommodation, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.transport, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.taxi, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.total_cost, 0), course.currency)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Linked invoices */}
      <div className="rounded-lg border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm">Linked Invoices ({invoices.length})</h3>
          <Button variant="outline" size="sm" onClick={() => setLinkDialogOpen(true)}>
            <Link2 className="h-3.5 w-3.5 mr-1" />
            Link Invoice
          </Button>
        </div>
        {invoices.length === 0 ? (
          <EmptyState icon={<FileText className="h-8 w-8" />} title="No invoices linked" description="Search and link invoices from accounting." />
        ) : (
          <div className="space-y-1.5">
            {invoices.map((inv: any) => (
              <div key={inv.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                <div>
                  <div className="text-sm font-medium">{inv.invoice_number}</div>
                  <div className="text-xs text-muted-foreground">
                    {inv.supplier} — {fmtDate(inv.invoice_date)} — {fmt(inv.invoice_value, inv.currency)}
                  </div>
                </div>
                <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive"
                  onClick={() => unlinkMutation.mutate(inv.id)} title="Unlink">
                  <Unlink className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Link Invoice Dialog */}
      <LinkInvoiceDialog
        open={linkDialogOpen}
        onOpenChange={setLinkDialogOpen}
        courseId={course.id}
        linkedInvoiceIds={invoices.map((i: any) => i.id)}
      />
    </div>
  )
}

function LinkInvoiceDialog({
  open,
  onOpenChange,
  courseId,
  linkedInvoiceIds,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  courseId: number
  linkedInvoiceIds: number[]
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)

  const { data: results = [], isLoading: isSearching } = useQuery({
    queryKey: ['invoice-search', debouncedSearch],
    queryFn: () => invoicesApi.searchInvoices(debouncedSearch),
    enabled: open && debouncedSearch.length >= 2,
  })

  const linkMut = useMutation({
    mutationFn: (invoiceId: number) => coursesApi.linkInvoice(courseId, invoiceId),
    onSuccess: () => {
      toast.success('Invoice linked')
      queryClient.invalidateQueries({ queryKey: ['course-invoices', courseId] })
    },
    onError: () => toast.error('Failed to link invoice'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[900px]" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Link Invoice to Course</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search by supplier or invoice number..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
          </div>

          {isSearching && <div className="text-center text-xs text-muted-foreground py-2">Searching...</div>}

          {(results as Invoice[]).length > 0 && (
            <div className="rounded-md border max-h-72 overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-background z-10">
                  <TableRow>
                    <TableHead className="text-xs">Supplier</TableHead>
                    <TableHead className="text-xs">Invoice Nr</TableHead>
                    <TableHead className="text-xs w-24">Date</TableHead>
                    <TableHead className="text-xs text-right w-28">Value</TableHead>
                    <TableHead className="w-16" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(results as Invoice[]).map((inv) => {
                    const alreadyLinked = linkedInvoiceIds.includes(inv.id)
                    return (
                      <TableRow key={inv.id} className={alreadyLinked ? 'opacity-50' : ''}>
                        <TableCell className="text-xs max-w-[200px] truncate">{inv.supplier}</TableCell>
                        <TableCell className="text-xs font-mono">{inv.invoice_number}</TableCell>
                        <TableCell className="text-xs">{fmtDate(inv.invoice_date)}</TableCell>
                        <TableCell className="text-right text-xs tabular-nums">{fmt(inv.invoice_value, inv.currency)}</TableCell>
                        <TableCell className="text-right">
                          {alreadyLinked ? (
                            <Check className="h-4 w-4 text-green-500 ml-auto" />
                          ) : (
                            <Button size="sm" variant="outline" className="h-6 text-xs px-2"
                              disabled={linkMut.isPending}
                              onClick={() => linkMut.mutate(inv.id)}>
                              Link
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}

          {debouncedSearch.length >= 2 && !isSearching && (results as Invoice[]).length === 0 && (
            <div className="text-center text-xs text-muted-foreground py-4">No invoices found.</div>
          )}
        </div>
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Done</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
