import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { coursesApi } from '@/api/courses'
import type { Course } from '@/types/courses'
import { courseStatusColors, fmt, fmtDate } from './utils'

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg border p-4 space-y-1">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  )
}

export function CourseOverviewTab({ course }: { course: Course }) {
  const { data: costData } = useQuery({
    queryKey: ['course-enrollment-costs', course.id],
    queryFn: () => coursesApi.getEnrollmentCosts(course.id),
  })
  const summary = costData?.summary

  const { data: txData } = useQuery({
    queryKey: ['course-transactions', course.id],
    queryFn: () => coursesApi.getTransactions(course.id),
  })
  const netCost = txData?.totals?.net_cost ?? 0

  const days = course.start_date && course.end_date
    ? Math.max(1, Math.round((new Date(course.end_date).getTime() - new Date(course.start_date).getTime()) / 86400000) + 1)
    : 0

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left: Main info */}
      <div className="lg:col-span-2 space-y-6">
        {/* Cost summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Participants" value={course.enrollment_count} />
          <StatCard label="Days" value={days} sub={course.duration_hours ? `${course.duration_hours}h total` : undefined} />
          <StatCard label="Budget" value={course.budget ? fmt(course.budget, course.currency) : '—'} />
          <StatCard label="Actual Cost" value={fmt(netCost, course.currency)}
            sub={txData?.totals?.transaction_count ? `${txData.totals.transaction_count} transactions` : undefined} />
        </div>

        {/* Cost breakdown */}
        {summary && summary.total_cost > 0 && (
          <div className="rounded-lg border p-4 space-y-3">
            <h3 className="font-semibold text-sm">Cost Breakdown</h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[
                { label: 'Training Fee', val: summary.total_training_fee },
                { label: 'Per Diem', val: summary.total_per_diem },
                { label: 'Accommodation', val: summary.total_accommodation },
                { label: 'Transport', val: summary.total_transport },
                { label: 'Taxi', val: summary.total_taxi },
              ].map(item => (
                <div key={item.label} className="text-center">
                  <div className="text-xs text-muted-foreground">{item.label}</div>
                  <div className="text-sm font-semibold tabular-nums">{fmt(item.val, course.currency)}</div>
                </div>
              ))}
            </div>

            {/* Budget vs actual bar */}
            {course.budget && Number(course.budget) > 0 && (() => {
              const bgt = Number(course.budget)
              const pct = Math.round((netCost / bgt) * 100)
              return (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Budget Execution</span>
                    <span>{pct}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full rounded-full ${netCost > bgt ? 'bg-red-500' : 'bg-primary'}`}
                      style={{ width: `${Math.min(100, pct)}%` }}
                    />
                  </div>
                </div>
              )
            })()}
          </div>
        )}

        {/* Description */}
        {course.description && (
          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="font-semibold text-sm">Description</h3>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{course.description}</p>
          </div>
        )}
      </div>

      {/* Right: Metadata sidebar */}
      <div className="space-y-4">
        <div className="rounded-lg border p-4 space-y-3">
          <h3 className="font-semibold text-sm">Details</h3>

          <div className="space-y-2.5 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Status</span>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${courseStatusColors[course.status ?? 'draft'] ?? ''}`}>
                {(course.status ?? 'draft').replace(/_/g, ' ')}
              </span>
            </div>

            <Separator />

            <div className="flex justify-between">
              <span className="text-muted-foreground">Type</span>
              <span>{course.course_type_name ?? '—'}</span>
            </div>

            {course.course_code && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Code</span>
                <span className="font-mono text-xs">{course.course_code}</span>
              </div>
            )}

            <div className="flex justify-between">
              <span className="text-muted-foreground">Period</span>
              <span>{fmtDate(course.start_date)} — {fmtDate(course.end_date)}</span>
            </div>

            {course.duration_hours && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Duration</span>
                <span>{course.duration_hours}h</span>
              </div>
            )}

            {course.location && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Location</span>
                <span className="text-right max-w-[180px] truncate">{course.location}</span>
              </div>
            )}

            {course.travel_mode && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Travel</span>
                <span>{course.travel_mode}</span>
              </div>
            )}

            <Separator />

            <div className="flex justify-between">
              <span className="text-muted-foreground">Company</span>
              <span>{course.company_name ?? '—'}</span>
            </div>

            <div className="flex justify-between">
              <span className="text-muted-foreground">Supplier</span>
              <span>{course.supplier_name ?? '—'}</span>
            </div>

            {course.trainer_name && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Trainer</span>
                <span>{course.trainer_name}</span>
              </div>
            )}

            <Separator />

            <div className="flex justify-between">
              <span className="text-muted-foreground">Created by</span>
              <span>{course.created_by_name ?? '—'}</span>
            </div>

            <div className="flex justify-between">
              <span className="text-muted-foreground">Created</span>
              <span>{fmtDate(course.created_at)}</span>
            </div>

            {course.requires_certification && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Certification</span>
                <Badge variant="outline" className="text-xs">Required</Badge>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
