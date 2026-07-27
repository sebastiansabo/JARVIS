import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Clock, Calendar, FileSpreadsheet } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { sincronApi, type SincronTimesheetData } from '@/api/sincron'

const MONTHS_RO = ['Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie', 'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

const CODE_LABELS: Record<string, { label: string; color: string }> = {
  OZ: { label: 'Ore lucrate', color: 'text-blue-600 dark:text-blue-400' },
  CO: { label: 'Concediu odihnă', color: 'text-green-600 dark:text-green-400' },
  CM: { label: 'Concediu medical', color: 'text-red-600 dark:text-red-400' },
  OS: { label: 'Ore suplimentare', color: 'text-orange-600 dark:text-orange-400' },
  CIC: { label: 'Îngrijire copil', color: 'text-purple-600 dark:text-purple-400' },
  CES: { label: 'Concediu fără plată', color: 'text-gray-600 dark:text-gray-400' },
  DLG: { label: 'Delegație', color: 'text-yellow-600 dark:text-yellow-400' },
  CMS: { label: 'Concediu îngrijire', color: 'text-pink-600 dark:text-pink-400' },
}

/** Per-user Sincron official timesheet for a given month. The parent owns the
 *  year/month (shared between the Hub HR panel and the Profile page). */
export function SincronTimesheetView({ year, month }: { year: number; month: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['sincron', 'my-timesheet', year, month],
    queryFn: () => sincronApi.getMyTimesheet(year, month),
  })

  const ts: SincronTimesheetData | null = data?.data ?? null
  const days = ts?.days ?? {}
  const summary = ts?.summary ?? []
  const employee = ts?.employee

  const allCodes = useMemo(() => {
    const codes = new Set<string>()
    Object.values(days).forEach((entries) => entries.forEach((e) => codes.add(e.short_code)))
    return [...codes].sort((a, b) => (a === 'OZ' ? -1 : b === 'OZ' ? 1 : a.localeCompare(b)))
  }, [days])
  const sortedDays = useMemo(() => Object.keys(days).sort(), [days])
  const stats = useMemo(() => {
    const f = (c: string) => summary.find((s) => s.short_code === c)
    return {
      workHours: f('OZ')?.total_value ?? 0,
      leaveDays: f('CO')?.day_count ?? 0,
      overtime: f('OS')?.total_value ?? 0,
      sickDays: f('CM')?.day_count ?? 0,
    }
  }, [summary])

  if (isLoading) return <Skeleton className="h-64 w-full" />

  if (!employee) {
    return (
      <EmptyState
        icon={<FileSpreadsheet className="h-10 w-10" />}
        title="Sincron neconectat"
        description="Profilul tău nu este mapat la un angajat Sincron. Contactează administratorul pentru mapare."
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard title="Ore lucrate" value={stats.workHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Zile concediu" value={stats.leaveDays} icon={<Calendar className="h-4 w-4" />} />
        <StatCard title="Ore suplimentare" value={stats.overtime.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Zile medicale" value={stats.sickDays} icon={<Calendar className="h-4 w-4" />} />
      </div>

      {summary.length > 0 && (
        <Card><CardContent className="p-4">
          <div className="flex flex-wrap gap-2">
            {summary.map((s) => (
              <Badge key={s.short_code} variant="outline" className="px-2.5 py-1 text-xs">
                <span className={`font-semibold ${CODE_LABELS[s.short_code]?.color ?? ''}`}>{s.short_code}</span>
                <span className="ml-1.5 text-muted-foreground">{CODE_LABELS[s.short_code]?.label ?? s.short_code_en ?? s.short_code}</span>
                <span className="ml-1.5 font-medium">{s.total_value.toFixed(s.unit === 'hour' ? 1 : 0)} ({s.day_count}z)</span>
              </Badge>
            ))}
          </div>
        </CardContent></Card>
      )}

      {sortedDays.length > 0 ? (
        <Card><CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">Data</TableHead>
                  <TableHead className="w-12">Zi</TableHead>
                  {allCodes.map((c) => (
                    <TableHead key={c} className="text-center"><span className={`text-xs font-semibold ${CODE_LABELS[c]?.color ?? ''}`}>{c}</span></TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedDays.map((day) => {
                  const d = new Date(day + 'T00:00:00')
                  const isWeekend = d.getDay() === 0 || d.getDay() === 6
                  const byCode: Record<string, number> = {}
                  days[day].forEach((e) => { byCode[e.short_code] = e.value })
                  return (
                    <TableRow key={day} className={isWeekend ? 'bg-muted/40' : ''}>
                      <TableCell className="text-xs tabular-nums">{day}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{d.toLocaleDateString('ro-RO', { weekday: 'short' })}</TableCell>
                      {allCodes.map((c) => (
                        <TableCell key={c} className="text-center text-sm tabular-nums">
                          {byCode[c] !== undefined
                            ? <span className={CODE_LABELS[c]?.color ?? ''}>{byCode[c].toFixed(byCode[c] % 1 === 0 ? 0 : 1)}</span>
                            : <span className="text-muted-foreground">-</span>}
                        </TableCell>
                      ))}
                    </TableRow>
                  )
                })}
                <TableRow className="border-t-2 font-semibold">
                  <TableCell colSpan={2}>Total</TableCell>
                  {allCodes.map((c) => {
                    const s = summary.find((x) => x.short_code === c)
                    return <TableCell key={c} className="text-center tabular-nums">{s ? s.total_value.toFixed(s.unit === 'hour' ? 1 : 0) : '-'}</TableCell>
                  })}
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </CardContent></Card>
      ) : (
        <EmptyState
          icon={<FileSpreadsheet className="h-8 w-8" />}
          title="Fără date"
          description={`Nicio înregistrare pentru ${MONTHS_RO[month - 1]} ${year}. Datele sunt sincronizate din Sincron HR.`}
        />
      )}
    </div>
  )
}
