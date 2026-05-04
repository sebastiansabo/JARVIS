import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { BookOpen, Users, DollarSign, Calendar } from 'lucide-react'
import { coursesApi } from '@/api/courses'
import { fmt } from './tabs/utils'
import type { CompanyCostSummary, MonthlyCost } from '@/types/courses'

function StatCard({ icon: Icon, label, value, sub }: { icon: React.ElementType; label: string; value: string | number; sub?: string }) {
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-4">
        <div className="rounded-lg bg-primary/10 p-2.5">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="text-xl font-bold tabular-nums">{value}</div>
          {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
        </div>
      </CardContent>
    </Card>
  )
}

const MONTH_NAMES = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun', 'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function MonthlyCostChart({ data, currency }: { data: MonthlyCost[]; currency: string }) {
  if (data.length === 0) return null
  const maxCost = Math.max(...data.map(d => d.total_cost), 1)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Monthly Cost Distribution</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-2 h-40">
          {Array.from({ length: 12 }, (_, i) => {
            const m = data.find(d => d.month === i + 1)
            const cost = m?.total_cost ?? 0
            const pct = maxCost > 0 ? (cost / maxCost) * 100 : 0
            return (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <div className="w-full flex flex-col items-center justify-end h-28">
                  {cost > 0 && (
                    <div className="text-[9px] text-muted-foreground tabular-nums mb-0.5">
                      {fmt(cost, currency)}
                    </div>
                  )}
                  <div
                    className="w-full rounded-t bg-primary/80 transition-all"
                    style={{ height: `${Math.max(pct, cost > 0 ? 4 : 0)}%` }}
                  />
                </div>
                <span className="text-[10px] text-muted-foreground">{MONTH_NAMES[i]}</span>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

interface Props {
  year: number
  onYearChange: (year: number) => void
}

export default function CoursesOverview({ year, onYearChange }: Props) {
  const { data: years = [] } = useQuery({
    queryKey: ['course-years'],
    queryFn: () => coursesApi.getAvailableYears(),
    staleTime: 60_000,
  })

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['courses-dashboard', year],
    queryFn: () => coursesApi.getDashboardStats({ year }),
  })

  const { data: companyCosts = [], isLoading: costsLoading } = useQuery({
    queryKey: ['courses-cost-summary', year],
    queryFn: () => coursesApi.getCostSummary({ year }),
  }) as { data: CompanyCostSummary[]; isLoading: boolean }

  const { data: monthlyCosts = [] } = useQuery({
    queryKey: ['courses-cost-by-month', year],
    queryFn: () => coursesApi.getCostByMonth({ year }),
  }) as { data: MonthlyCost[]; isLoading: boolean }

  const loading = statsLoading || costsLoading

  // Ensure current year is in the list
  const allYears = [...new Set([...years, new Date().getFullYear()])].sort((a, b) => b - a)

  return (
    <div className="space-y-6">
      {/* Year selector */}
      <div className="flex items-center gap-3">
        <Select value={String(year)} onValueChange={v => onYearChange(Number(v))}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {allYears.map(y => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-20" />)}
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard icon={BookOpen} label="Total Courses" value={stats?.total_courses ?? 0} />
            <StatCard icon={Users} label="Participants" value={stats?.total_participants ?? 0} />
            <StatCard icon={DollarSign} label="Total Cost" value={fmt(stats?.total_cost ?? 0)} />
            <StatCard icon={Calendar} label="Total Days" value={stats?.total_days ?? 0} />
          </div>

          {/* Status breakdown */}
          {stats?.by_status && stats.by_status.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">By Status</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {stats.by_status.map((s: any) => (
                    <div key={s.status} className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5">
                      <span className="text-sm font-medium">{s.count}</span>
                      <span className="text-xs text-muted-foreground">{(s.status ?? 'unknown').replace(/_/g, ' ')}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Monthly chart */}
          <MonthlyCostChart data={monthlyCosts} currency="RON" />

          {/* Cost by Company table */}
          {companyCosts.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Cost by Company</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2 px-2 font-medium">Company</th>
                        <th className="text-right py-2 px-2 font-medium">Courses</th>
                        <th className="text-right py-2 px-2 font-medium">Participants</th>
                        <th className="text-right py-2 px-2 font-medium">Days</th>
                        <th className="text-right py-2 px-2 font-medium">Training</th>
                        <th className="text-right py-2 px-2 font-medium">Diurna</th>
                        <th className="text-right py-2 px-2 font-medium">Cazare</th>
                        <th className="text-right py-2 px-2 font-medium">Transport</th>
                        <th className="text-right py-2 px-2 font-medium">Total RON</th>
                      </tr>
                    </thead>
                    <tbody>
                      {companyCosts.map((c: CompanyCostSummary) => (
                        <tr key={c.company_id} className="border-b last:border-0 hover:bg-muted/30">
                          <td className="py-2 px-2 font-medium">{c.company_name ?? 'Unassigned'}</td>
                          <td className="py-2 px-2 text-right tabular-nums">{c.course_count}</td>
                          <td className="py-2 px-2 text-right tabular-nums">{c.participant_count}</td>
                          <td className="py-2 px-2 text-right tabular-nums">{c.total_days}</td>
                          <td className="py-2 px-2 text-right tabular-nums">{fmt(c.training_fee)}</td>
                          <td className="py-2 px-2 text-right tabular-nums">{fmt(c.per_diem)}</td>
                          <td className="py-2 px-2 text-right tabular-nums">{fmt(c.accommodation)}</td>
                          <td className="py-2 px-2 text-right tabular-nums">{fmt(c.transport + c.taxi)}</td>
                          <td className="py-2 px-2 text-right tabular-nums font-semibold">{fmt(c.total_cost)}</td>
                        </tr>
                      ))}
                      {/* Grand totals */}
                      <tr className="bg-muted/50 font-semibold">
                        <td className="py-2 px-2">Total</td>
                        <td className="py-2 px-2 text-right tabular-nums">{companyCosts.reduce((s, c) => s + c.course_count, 0)}</td>
                        <td className="py-2 px-2 text-right tabular-nums">{companyCosts.reduce((s, c) => s + c.participant_count, 0)}</td>
                        <td className="py-2 px-2 text-right tabular-nums">{companyCosts.reduce((s, c) => s + c.total_days, 0)}</td>
                        <td className="py-2 px-2 text-right tabular-nums">{fmt(companyCosts.reduce((s, c) => s + c.training_fee, 0))}</td>
                        <td className="py-2 px-2 text-right tabular-nums">{fmt(companyCosts.reduce((s, c) => s + c.per_diem, 0))}</td>
                        <td className="py-2 px-2 text-right tabular-nums">{fmt(companyCosts.reduce((s, c) => s + c.accommodation, 0))}</td>
                        <td className="py-2 px-2 text-right tabular-nums">{fmt(companyCosts.reduce((s, c) => s + c.transport + c.taxi, 0))}</td>
                        <td className="py-2 px-2 text-right tabular-nums">{fmt(companyCosts.reduce((s, c) => s + c.total_cost, 0))}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
