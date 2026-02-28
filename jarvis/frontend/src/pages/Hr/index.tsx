import { lazy, Suspense, useMemo } from 'react'
import { Routes, Route, Navigate, NavLink, useMatch } from 'react-router-dom'
import { ClipboardCheck, Download, Fingerprint, LayoutDashboard } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { hrApi } from '@/api/hr'
import { useHrStore } from '@/stores/hrStore'
import { cn } from '@/lib/utils'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'

const BonusesTab = lazy(() => import('./BonusesTab'))
const PontajeTab = lazy(() => import('./PontajeTab'))
const AdjustmentsTab = lazy(() => import('./AdjustmentsTab'))
const EmployeeProfile = lazy(() => import('./EmployeeProfile'))

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
  const isProfilePage = useMatch('/app/hr/pontaje/:biostarUserId')
  const isBonusesPage = useMatch('/app/hr/bonuses')
  const isAdjustmentsPage = useMatch('/app/hr/adjustments')
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('hr_summary')
  const filters = useHrStore((s) => s.filters)

  const { data: permissions } = useQuery({
    queryKey: ['hr-permissions'],
    queryFn: () => hrApi.getPermissions(),
    staleTime: 5 * 60 * 1000,
  })

  const canExport = permissions?.permissions?.['hr.bonuses.export']?.allowed ?? false
  const canViewAmounts = permissions?.permissions?.['hr.bonuses.view_amounts']?.allowed ?? false
  const canViewAdjustments = permissions?.permissions?.['hr.pontaje_adjustments.view']?.allowed ?? false

  const tabs = useMemo(() => {
    const t: { to: string; label: string; icon: typeof Fingerprint }[] = [
      { to: '/app/hr/pontaje', label: 'Pontaje', icon: Fingerprint },
    ]
    if (canViewAdjustments) {
      t.push({ to: '/app/hr/adjustments', label: 'Adjustments', icon: ClipboardCheck })
    }
    return t
  }, [canViewAdjustments])

  // Profile page — standalone, no tabs/stats
  if (isProfilePage) {
    return (
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route path="pontaje/:biostarUserId" element={<EmployeeProfile />} />
        </Routes>
      </Suspense>
    )
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={isBonusesPage ? 'Bonuses' : isAdjustmentsPage ? 'Adjustments' : 'Pontaje'}
        breadcrumbs={[
          { label: 'HR', href: '/app/hr/pontaje' },
          ...(isBonusesPage ? [{ label: 'Bonuses' }] : isAdjustmentsPage ? [{ label: 'Adjustments' }] : [{ label: 'Pontaje' }]),
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={toggleDashboardWidget}>
              <LayoutDashboard className="mr-1.5 h-3.5 w-3.5" />
              {isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}
            </Button>
            {canExport && (
              <Button variant="outline" asChild>
                <a href={hrApi.exportUrl({ year: filters.year, month: filters.month })} download>
                  <Download className="mr-1.5 h-4 w-4" />
                  Export
                </a>
              </Button>
            )}
          </div>
        }
      />

      {/* Tab nav — hidden on Bonuses page */}
      {!isBonusesPage && <nav className="flex gap-1 border-b">
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.to !== '/app/hr/pontaje'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-1.5 border-b-2 px-4 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )
            }
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </NavLink>
        ))}
      </nav>}

      {/* Tab content */}
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route index element={<Navigate to="pontaje" replace />} />
          <Route path="pontaje" element={<PontajeTab />} />
          <Route path="bonuses" element={<BonusesTab canViewAmounts={canViewAmounts} />} />
          {canViewAdjustments && <Route path="adjustments" element={<AdjustmentsTab />} />}
        </Routes>
      </Suspense>
    </div>
  )
}
