import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { hrApi } from '@/api/hr'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { CalendarClock, Clock, TrendingUp, Users } from 'lucide-react'

interface Props {
  search: string
}

function StatCard({ title, value, icon, isLoading }: {
  title: string; value: string | number; icon: React.ReactNode; isLoading: boolean
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="rounded-lg bg-blue-50 p-2 text-blue-600">{icon}</div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground truncate">{title}</p>
          {isLoading ? (
            <Skeleton className="h-6 w-16 mt-1" />
          ) : (
            <p className="text-lg font-semibold">{value}</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function TableSkeleton({ rows = 4, cols = 3 }: { rows?: number; cols?: number }) {
  return (
    <Table>
      <TableBody>
        {Array.from({ length: rows }).map((_, i) => (
          <TableRow key={i}>
            {Array.from({ length: cols }).map((_, j) => (
              <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

const PERIOD_OPTIONS = [
  { value: 'today', label: 'Azi' },
  { value: 'week', label: 'Săptămâna curentă' },
  { value: 'month', label: 'Luna curentă' },
  { value: 'quarter', label: 'Trimestrul curent' },
  { value: 'ytd', label: 'YTD' },
]

export default function ReportsTab({ search }: Props) {
  const [company, setCompany] = useState<string>('__all__')
  const [department, setDepartment] = useState<string>('__all__')
  const [period, setPeriod] = useState('ytd')
  const [unit, setUnit] = useState<'hours' | 'days'>('hours')

  const { data, isLoading } = useQuery({
    queryKey: ['hr', 'reports', 'weekly-digest', period],
    queryFn: () => hrApi.getWeeklyDigest({ period }),
    staleTime: 5 * 60 * 1000,
  })

  const d = data?.data
  const q = search.toLowerCase()

  // Build company list from headcount_map
  const companies = useMemo(() => {
    if (!d?.headcount_map) return []
    return Object.keys(d.headcount_map).sort()
  }, [d?.headcount_map])

  // Build department list from organigram (leave_by_department)
  const departments = useMemo(() => {
    if (!d?.leave_by_department) return []
    return d.leave_by_department.map(r => r.department).filter(Boolean).sort()
  }, [d?.leave_by_department])

  // Reset department when company changes
  const handleCompanyChange = (v: string) => {
    setCompany(v)
    setDepartment('__all__')
  }

  // Filter company-level rows
  const filterRows = <T extends { company_name?: string; company?: string }>(rows: T[]) => {
    let filtered = rows
    if (company !== '__all__') {
      filtered = filtered.filter(r => (r.company_name || r.company) === company)
    }
    if (q) {
      filtered = filtered.filter(r => (r.company_name || r.company || '').toLowerCase().includes(q))
    }
    return filtered
  }

  // Filter CO rows by company + department, then take top 10
  const filteredCo = useMemo(() => {
    let rows = d?.all_co_rows ?? []
    if (company !== '__all__') {
      rows = rows.filter(r => r.company === company)
    }
    if (department !== '__all__') {
      rows = rows.filter(r => r.department === department)
    }
    if (q) {
      rows = rows.filter(r => r.company.toLowerCase().includes(q) || r.name.toLowerCase().includes(q))
    }
    return rows.slice(0, 10)
  }, [d?.all_co_rows, company, department, q])

  // Compute filtered totals for stat cards
  const filteredLeave = useMemo(() => filterRows(d?.leave_by_company ?? []), [d?.leave_by_company, company, q])
  const filteredHours = useMemo(() => filterRows(d?.actual_vs_potential ?? []), [d?.actual_vs_potential, company, q])

  const totalLeave = filteredLeave.reduce((s, r) => s + r.total_leave_days, 0)
  const totalActual = filteredHours.reduce((s, r) => s + r.actual_hours, 0)
  const totalPotential = filteredHours.reduce((s, r) => s + r.potential_hours, 0)
  const totalPct = totalPotential > 0 ? Math.round(totalActual / totalPotential * 100) : 0

  return (
    <div className="space-y-4">
      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={company} onValueChange={handleCompanyChange}>
          <SelectTrigger className="h-8 w-56 text-xs">
            <SelectValue placeholder="Toate companiile" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Toate companiile</SelectItem>
            {companies.map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={department} onValueChange={setDepartment}>
          <SelectTrigger className="h-8 w-56 text-xs">
            <SelectValue placeholder="Toate departamentele" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Toate departamentele</SelectItem>
            {departments.map((dep) => (
              <SelectItem key={dep} value={dep}>{dep}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={period} onValueChange={setPeriod}>
          <SelectTrigger className="h-8 w-48 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PERIOD_OPTIONS.map((p) => (
              <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <StatCard
          title="Sold CO"
          value={filteredLeave.reduce((s, r) => s + r.co_remaining, 0)}
          icon={<CalendarClock className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Ore Lucrate"
          value={d ? `${Math.round(totalActual * 10) / 10}h` : '0h'}
          icon={<Clock className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Ore Potențial"
          value={d ? `${Math.round(totalPotential * 10) / 10}h` : '0h'}
          icon={<TrendingUp className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Utilizare"
          value={d ? `${totalPct}%` : '0%'}
          icon={<Users className="h-4 w-4" />}
          isLoading={isLoading}
        />
      </div>

      {d && (
        <p className="text-xs text-muted-foreground">
          {d.period_label} &middot; {d.working_days} zile lucrătoare
        </p>
      )}

      {/* Tables grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Section 1: Leave Days */}
        <Card>
          <CardContent className="p-4">
            <h3 className="text-sm font-semibold mb-2">1. Concedii (zile)</h3>
            {isLoading ? <TableSkeleton cols={5} /> : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Companie</TableHead>
                      <TableHead className="text-right">Angajați</TableHead>
                      <TableHead className="text-right">Concedii</TableHead>
                      <TableHead className="text-right">Sold CO</TableHead>
                      <TableHead className="text-right">Acoperire</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredLeave.map((r) => {
                      const total = r.total_leave_days + r.co_remaining
                      const pct = total > 0 ? Math.round(r.total_leave_days / total * 100) : 0
                      return (
                        <TableRow key={r.company_name}>
                          <TableCell className="text-xs">{r.company_name}</TableCell>
                          <TableCell className="text-right">{r.headcount}</TableCell>
                          <TableCell className="text-right font-medium">{r.total_leave_days}</TableCell>
                          <TableCell className="text-right">{r.co_remaining}</TableCell>
                          <TableCell className="text-right">
                            <span className={
                              pct >= 50 ? 'text-green-600 font-bold' :
                              pct >= 25 ? 'text-yellow-600 font-bold' :
                              'text-red-600 font-bold'
                            }>
                              {pct}%
                            </span>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                    <TableRow className="font-bold bg-muted/50">
                      <TableCell>TOTAL</TableCell>
                      <TableCell className="text-right">{filteredLeave.reduce((s, r) => s + r.headcount, 0)}</TableCell>
                      <TableCell className="text-right">{totalLeave}</TableCell>
                      <TableCell className="text-right">{filteredLeave.reduce((s, r) => s + r.co_remaining, 0)}</TableCell>
                      <TableCell className="text-right">
                        {(() => {
                          const tUsed = totalLeave
                          const tRem = filteredLeave.reduce((s, r) => s + r.co_remaining, 0)
                          const tTotal = tUsed + tRem
                          return tTotal > 0 ? `${Math.round(tUsed / tTotal * 100)}%` : '0%'
                        })()}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            )}
            <p className="text-[10px] text-muted-foreground mt-2 leading-tight">
              Concedii = zile distincte (angajat, zi) din Sincron cu codul CO.
              Sold CO = zile CO disponibile - zile CO folosite. Acoperire = Concedii / (Concedii + Sold CO).
              Angajați = total unici cu contract activ în Sincron. Se ia doar contractul principal (norma cea mai mare).
            </p>
          </CardContent>
        </Card>

        {/* Section 2: Top 10 CO Remaining */}
        <Card>
          <CardContent className="p-4">
            <h3 className="text-sm font-semibold mb-2">
              2. Top 10 — Sold CO ({d?.year ?? new Date().getFullYear()})
              {company !== '__all__' && <span className="font-normal text-muted-foreground"> — {company}</span>}
            </h3>
            {isLoading ? <TableSkeleton cols={5} /> : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8">#</TableHead>
                      <TableHead>Nume</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead className="text-right">Folosit</TableHead>
                      <TableHead className="text-right">Rămas</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredCo.map((r, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                        <TableCell className="font-medium text-xs">{r.name}</TableCell>
                        <TableCell className="text-right">{r.total_available}</TableCell>
                        <TableCell className="text-right">{r.used}</TableCell>
                        <TableCell className="text-right font-bold">{r.remaining}</TableCell>
                      </TableRow>
                    ))}
                    {filteredCo.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center text-muted-foreground py-4">
                          Nu există date CO pentru selecția curentă
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
            <p className="text-[10px] text-muted-foreground mt-2 leading-tight">
              Date din Sincron CO balance. Total CO = zile contractuale pe an.
              Folosit = zile CO luate. Rămas = Total CO - Folosit.
            </p>
          </CardContent>
        </Card>

        {/* Section 3: Actual vs Potential */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold">3. {unit === 'hours' ? 'Ore' : 'Zile'} Lucrate vs Potențial</h3>
              <div className="flex gap-0.5 rounded-md border p-0.5">
                <Button size="sm" variant={unit === 'hours' ? 'secondary' : 'ghost'} className="h-5 px-2 text-[10px]" onClick={() => setUnit('hours')}>Ore</Button>
                <Button size="sm" variant={unit === 'days' ? 'secondary' : 'ghost'} className="h-5 px-2 text-[10px]" onClick={() => setUnit('days')}>Zile</Button>
              </div>
            </div>
            {isLoading ? <TableSkeleton cols={5} /> : (() => {
              const wd = d?.working_days ?? 0
              const suffix = unit === 'hours' ? 'h' : 'z'
              const fmt = (hours: number) => {
                const v = unit === 'hours' ? hours : hours / 8
                return `${Math.round(v * 10) / 10}${suffix}`
              }
              const cal = (headcount: number) => {
                const v = unit === 'hours' ? headcount * wd * 8 : headcount * wd
                return `${Math.round(v * 10) / 10}${suffix}`
              }
              const totalCal = filteredHours.reduce((s, r) => s + (r.headcount ?? 0), 0)
              const calHours = (hc: number) => hc * wd * 8
              const covPct = (actual: number, calH: number) => calH > 0 ? Math.round(actual / calH * 100) : 0
              const totalCalH = calHours(totalCal)
              const totalCovPct = covPct(totalActual, totalCalH)
              return (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Companie</TableHead>
                        <TableHead className="text-right">Lucrate</TableHead>
                        <TableHead className="text-right">Potențial</TableHead>
                        <TableHead className="text-right">Utilizare</TableHead>
                        <TableHead className="text-right">Calendar</TableHead>
                        <TableHead className="text-right">Acoperire</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredHours.map((r) => {
                        const hc = r.headcount ?? 0
                        const rCalH = calHours(hc)
                        const rCov = covPct(r.actual_hours, rCalH)
                        return (
                          <TableRow key={r.company_name}>
                            <TableCell className="text-xs">{r.company_name}</TableCell>
                            <TableCell className="text-right">{fmt(r.actual_hours)}</TableCell>
                            <TableCell className="text-right">{fmt(r.potential_hours)}</TableCell>
                            <TableCell className="text-right">
                              <span className={
                                r.utilization_pct >= 85 ? 'text-green-600 font-bold' :
                                r.utilization_pct >= 70 ? 'text-yellow-600 font-bold' :
                                'text-red-600 font-bold'
                              }>
                                {r.utilization_pct}%
                              </span>
                            </TableCell>
                            <TableCell className="text-right text-muted-foreground" title={`${hc} ang. × ${wd} zile × 8h`}>
                              {cal(hc)}
                            </TableCell>
                            <TableCell className="text-right">
                              <span className={
                                rCov >= 85 ? 'text-green-600 font-bold' :
                                rCov >= 70 ? 'text-yellow-600 font-bold' :
                                'text-red-600 font-bold'
                              }>
                                {rCov}%
                              </span>
                            </TableCell>
                          </TableRow>
                        )
                      })}
                      <TableRow className="font-bold bg-muted/50">
                        <TableCell>TOTAL</TableCell>
                        <TableCell className="text-right">{fmt(totalActual)}</TableCell>
                        <TableCell className="text-right">{fmt(totalPotential)}</TableCell>
                        <TableCell className="text-right">{totalPct}%</TableCell>
                        <TableCell className="text-right text-muted-foreground" title={`${totalCal} ang. × ${wd} zile × 8h`}>
                          {cal(totalCal)}
                        </TableCell>
                        <TableCell className="text-right">{totalCovPct}%</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </div>
              )
            })()}
            <p className="text-[10px] text-muted-foreground mt-2 leading-tight">
              Date din BioStar. Calendar = angajați × {d?.working_days ?? 0} zile lucrătoare × 8h (program standard).
              Lucrate = ore efective din pontaje, minus pauza de masă.
              Potențial = ore program per angajat × zile lucrătoare.
              Acoperire = Lucrate / Calendar. Utilizare = Lucrate / Potențial.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
