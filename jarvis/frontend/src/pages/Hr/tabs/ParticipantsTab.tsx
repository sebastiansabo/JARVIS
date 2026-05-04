import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Plus, Trash2, Search, Loader2, Users, CheckCircle } from 'lucide-react'
import { coursesApi } from '@/api/courses'
import { hrApi } from '@/api/hr'
import { toast } from 'sonner'
import { fmt } from './utils'
import type { Enrollment } from '@/types/courses'
import type { HrEmployee } from '@/types/hr'

export function ParticipantsTab({ courseId, currency = 'RON' }: { courseId: number; currency?: string }) {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<HrEmployee[]>([])
  const [searching, setSearching] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Enrollment | null>(null)

  const { data: enrollments = [], isLoading } = useQuery({
    queryKey: ['course-enrollments', courseId],
    queryFn: () => coursesApi.getEnrollments(courseId),
  })

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['course-enrollments', courseId] })
    queryClient.invalidateQueries({ queryKey: ['course-enrollment-costs', courseId] })
    queryClient.invalidateQueries({ queryKey: ['course', courseId] })
  }, [queryClient, courseId])

  const addMutation = useMutation({
    mutationFn: (employeeIds: number[]) => coursesApi.addEnrollments(courseId, employeeIds),
    onSuccess: (res) => {
      invalidate()
      toast.success(`${res.enrolled} employee(s) enrolled`)
      setSearchQuery('')
      setSearchResults([])
    },
    onError: () => toast.error('Failed to add employees'),
  })

  const completeMutation = useMutation({
    mutationFn: (enrollmentId: number) => coursesApi.completeEnrollment(courseId, enrollmentId),
    onSuccess: () => {
      invalidate()
      toast.success('Marked as completed')
    },
  })

  const removeMutation = useMutation({
    mutationFn: (enrollmentId: number) => coursesApi.deleteEnrollment(courseId, enrollmentId),
    onSuccess: () => {
      invalidate()
      toast.success('Employee removed')
    },
  })

  // Inline field update
  const fieldMutation = useMutation({
    mutationFn: ({ enrollmentId, field, value }: { enrollmentId: number; field: string; value: string }) =>
      coursesApi.updateEnrollmentFields(courseId, enrollmentId, { [field]: value }),
    onSuccess: () => invalidate(),
  })

  // Inline cost update
  const costMutation = useMutation({
    mutationFn: ({ enrollmentId, field, value }: { enrollmentId: number; field: string; value: number }) =>
      coursesApi.upsertEnrollmentCost(courseId, enrollmentId, { [field]: value }),
    onSuccess: () => invalidate(),
  })

  const handleSearch = async (q: string) => {
    setSearchQuery(q)
    if (q.length < 2) { setSearchResults([]); return }
    setSearching(true)
    try {
      const results = await hrApi.searchEmployees(q)
      const existingIds = new Set(enrollments.map((e: Enrollment) => e.employee_id))
      setSearchResults(results.filter((e: HrEmployee) => !existingIds.has(e.id)))
    } catch { setSearchResults([]) }
    finally { setSearching(false) }
  }

  if (isLoading) return <Skeleton className="h-32 w-full" />

  const costFields = ['training_fee', 'per_diem', 'accommodation', 'transport', 'taxi'] as const
  const costLabels: Record<string, string> = {
    training_fee: 'Training',
    per_diem: 'Diurna',
    accommodation: 'Cazare',
    transport: 'Transport',
    taxi: 'Taxi',
  }

  // Totals
  const totals = costFields.reduce((acc, f) => {
    acc[f] = enrollments.reduce((s: number, e: Enrollment) => s + (Number((e as any)[f]) || 0), 0)
    return acc
  }, {} as Record<string, number>)
  const grandTotal = enrollments.reduce((s: number, e: Enrollment) => s + (Number(e.total_cost) || 0), 0)

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input className="pl-8" placeholder="Search employees to add..." value={searchQuery}
          onChange={e => handleSearch(e.target.value)} />
        {searching && <Loader2 className="absolute right-3 top-2.5 h-4 w-4 animate-spin" />}
        {searchResults.length > 0 && (
          <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-lg max-h-48 overflow-y-auto">
            {searchResults.map(emp => (
              <button key={emp.id} type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent text-sm"
                onClick={() => { addMutation.mutate([emp.id]); setSearchResults([]) }}>
                <Plus className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <div>
                  <div className="font-medium">{emp.name}</div>
                  <div className="text-xs text-muted-foreground">{emp.company ?? ''}{emp.departments ? ` — ${emp.departments}` : ''}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {enrollments.length === 0 ? (
        <EmptyState icon={<Users className="h-8 w-8" />} title="No participants" description="Search and add employees above." />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left px-3 py-2 font-medium">Employee</th>
                <th className="text-left px-3 py-2 font-medium">Dept.</th>
                <th className="text-left px-3 py-2 font-medium">Status</th>
                <th className="text-left px-3 py-2 font-medium">Nec. Nr.</th>
                <th className="text-left px-3 py-2 font-medium">OD</th>
                <th className="text-left px-3 py-2 font-medium">Act Adit.</th>
                {costFields.map(f => (
                  <th key={f} className="text-right px-3 py-2 font-medium">{costLabels[f]}</th>
                ))}
                <th className="text-right px-3 py-2 font-medium">Total</th>
                <th className="px-3 py-2 w-20" />
              </tr>
            </thead>
            <tbody>
              {enrollments.map((e: Enrollment) => (
                <tr key={e.id} className="border-b last:border-0 hover:bg-muted/30">
                  <td className="px-3 py-2">
                    <div className="font-medium">{e.employee_name}</div>
                    <div className="text-xs text-muted-foreground">{e.company ?? ''}</div>
                  </td>
                  <td className="px-3 py-2 text-xs">{e.department ?? '—'}</td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className="text-xs">{e.enrollment_status}</Badge>
                  </td>
                  {/* Admin fields — inline editable */}
                  {(['order_number', 'travel_order', 'additional_act'] as const).map(field => (
                    <td key={field} className="px-3 py-2">
                      <Input
                        className="h-7 text-xs w-20 px-1.5"
                        defaultValue={(e as any)[field] ?? ''}
                        onBlur={ev => {
                          const val = ev.target.value
                          if (val !== ((e as any)[field] ?? '')) {
                            fieldMutation.mutate({ enrollmentId: e.id, field, value: val })
                          }
                        }}
                      />
                    </td>
                  ))}
                  {/* Cost fields — inline editable */}
                  {costFields.map(field => (
                    <td key={field} className="px-3 py-2 text-right">
                      <Input
                        type="number"
                        step="0.01"
                        min={0}
                        className="h-7 text-xs w-20 px-1.5 text-right ml-auto"
                        defaultValue={(e as any)[field] ?? 0}
                        onBlur={ev => {
                          const val = Number(ev.target.value) || 0
                          if (val !== (Number((e as any)[field]) || 0)) {
                            costMutation.mutate({ enrollmentId: e.id, field, value: val })
                          }
                        }}
                      />
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right font-semibold tabular-nums text-xs">
                    {fmt(e.total_cost, currency)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 justify-end">
                      {e.enrollment_status === 'enrolled' && (
                        <Button variant="ghost" size="icon" className="h-6 w-6 text-green-600"
                          onClick={() => completeMutation.mutate(e.id)} title="Complete">
                          <CheckCircle className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive"
                        onClick={() => setDeleteTarget(e)} title="Remove">
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {/* Totals row */}
              <tr className="bg-muted/50 font-semibold">
                <td className="px-3 py-2" colSpan={6}>Totals</td>
                {costFields.map(f => (
                  <td key={f} className="px-3 py-2 text-right tabular-nums text-xs">{fmt(totals[f], currency)}</td>
                ))}
                <td className="px-3 py-2 text-right tabular-nums text-xs">{fmt(grandTotal, currency)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title="Remove Employee"
        description={`Remove ${deleteTarget?.employee_name} from this course? Their cost data will also be removed.`}
        onConfirm={() => { if (deleteTarget) removeMutation.mutate(deleteTarget.id); setDeleteTarget(null) }}
        destructive
      />
    </div>
  )
}
