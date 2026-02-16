import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, NavLink } from 'react-router-dom'
import { Award, CalendarDays, Building2, Download } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { hrApi } from '@/api/hr'
import { useHrStore } from '@/stores/hrStore'
import { cn } from '@/lib/utils'

const BonusesTab = lazy(() => import('./BonusesTab'))
const EventsTab = lazy(() => import('./EventsTab'))
const StructureTab = lazy(() => import('./StructureTab'))

const tabs = [
  { to: '/app/hr/bonuses', label: 'Bonuses', icon: Award },
  { to: '/app/hr/events', label: 'Events', icon: CalendarDays },
  { to: '/app/hr/structure', label: 'Structure', icon: Building2 },
] as const

const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function TabLoader() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  )
}

export default function Hr() {
  const filters = useHrStore((s) => s.filters)

  const { data: summary } = useQuery({
    queryKey: ['hr-summary', filters.year],
    queryFn: () => hrApi.getSummary({ year: filters.year }),
  })

  const { data: permissions } = useQuery({
    queryKey: ['hr-permissions'],
    queryFn: () => hrApi.getPermissions(),
    staleTime: 5 * 60 * 1000,
  })

  const canExport = permissions?.permissions?.['hr.bonuses.export']?.allowed ?? false
  const canViewAmounts = permissions?.permissions?.['hr.bonuses.view_amounts']?.allowed ?? false

  return (
    <div className="space-y-4">
      <PageHeader
        title="HR Events"
        description={`Bonuses, events & employee management${filters.year ? ` — ${filters.year}` : ''}${filters.month ? ` ${MONTHS[filters.month]}` : ''}`}
        actions={
          canExport ? (
            <Button variant="outline" asChild>
              <a href={hrApi.exportUrl({ year: filters.year, month: filters.month })} download>
                <Download className="mr-1.5 h-4 w-4" />
                Export
              </a>
            </Button>
          ) : undefined
        }
      />

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <StatCard title="Bonuses" value={summary?.total_bonuses ?? 0} icon={<Award className="h-4 w-4" />} />
        <StatCard title="Employees" value={summary?.total_employees ?? 0} icon={<Award className="h-4 w-4" />} />
        <StatCard title="Events" value={summary?.total_events ?? 0} icon={<CalendarDays className="h-4 w-4" />} />
        <StatCard title="Total Days" value={summary?.total_days ?? 0} icon={<CalendarDays className="h-4 w-4" />} />
        <StatCard title="Total Hours" value={summary?.total_hours ?? 0} icon={<CalendarDays className="h-4 w-4" />} />
        {canViewAmounts && (
          <StatCard
            title="Total Amount"
            value={
              summary?.total_bonus_amount != null
                ? new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(
                    summary.total_bonus_amount,
                  ) + ' RON'
                : '—'
            }
            icon={<Award className="h-4 w-4" />}
          />
        )}
      </div>

      {/* Tab nav */}
      <nav className="flex gap-1 border-b">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === '/app/hr/bonuses'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-1.5 border-b-2 px-4 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )
            }
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </NavLink>
        ))}
      </nav>

      {/* Tab content */}
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route index element={<Navigate to="bonuses" replace />} />
          <Route path="bonuses" element={<BonusesTab canViewAmounts={canViewAmounts} />} />
          <Route path="events/*" element={<EventsTab />} />
          <Route path="structure" element={<StructureTab />} />
        </Routes>
      </Suspense>
    </div>
  )
}
