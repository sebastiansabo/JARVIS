import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { FileText, Unlink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { coursesApi } from '@/api/courses'
import { toast } from 'sonner'
import type { Course } from '@/types/courses'
import { fmt, fmtDate } from './utils'

export function CostsTab({ course }: { course: Course }) {
  const queryClient = useQueryClient()

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

      {/* Linked invoices */}
      <div className="rounded-lg border p-4 space-y-3">
        <h3 className="font-semibold text-sm">Linked Invoices</h3>
        {invoices.length === 0 ? (
          <EmptyState icon={<FileText className="h-8 w-8" />} title="No invoices linked" description="Link invoices from the accounting module." />
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
    </div>
  )
}
