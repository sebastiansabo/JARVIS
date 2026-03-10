import { lazy, Suspense, useMemo, useState } from 'react'
import { Routes, Route, Navigate, useMatch, useNavigate } from 'react-router-dom'
import { ClipboardCheck, Download, Fingerprint, LayoutDashboard, BarChart3, SlidersHorizontal, Plus, Users } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { hrApi } from '@/api/hr'
import { useHrStore } from '@/stores/hrStore'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
import { cn } from '@/lib/utils'

const BonusesTab = lazy(() => import('./BonusesTab'))
const PontajeTab = lazy(() => import('./PontajeTab'))
const AdjustmentsTab = lazy(() => import('./AdjustmentsTab'))
const EmployeeProfile = lazy(() => import('./EmployeeProfile'))
const OrganigramTab = lazy(() => import('./OrganigramTab'))

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
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const isProfilePage = useMatch('/app/hr/pontaje/:biostarUserId')
  const isBonusesPage = useMatch('/app/hr/bonuses')
  const isAdjustmentsPage = useMatch('/app/hr/adjustments')
  const isOrganigramPage = useMatch('/app/hr/organigram')
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('hr_summary')
  const filters = useHrStore((s) => s.filters)

  const { data: permissions } = useQuery({
    queryKey: ['hr-permissions'],
    queryFn: () => hrApi.getPermissions(),
    staleTime: 5 * 60 * 1000,
  })

  const [showStats, setShowStats] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [bonusAddTrigger, setBonusAddTrigger] = useState(0)
  const canExport = permissions?.permissions?.['hr.bonuses.export']?.allowed ?? false
  const canViewAmounts = permissions?.permissions?.['hr.bonuses.view_amounts']?.allowed ?? false
  const canViewAdjustments = permissions?.permissions?.['hr.pontaje_adjustments.view']?.allowed ?? false
  const canViewTeamPontaje = permissions?.permissions?.['hr.team_pontaje.view']?.allowed ?? false
  const teamPontajeScope = permissions?.permissions?.['hr.team_pontaje.view']?.scope ?? 'deny'

  // Team filter — lifted here so it renders next to page title
  const [teamFilter, setTeamFilter] = useState<'team' | 'all'>('team')
  const showTeamToggle = canViewTeamPontaje && teamPontajeScope === 'all'
  const managerFilter = showTeamToggle && teamFilter === 'team'

  const tabs = useMemo(() => {
    const t: { to: string; label: string; icon: typeof Fingerprint }[] = [
      { to: '/app/hr/pontaje', label: 'Pontaje', icon: Fingerprint },
    ]
    if (canViewAdjustments) {
      t.push({ to: '/app/hr/adjustments', label: 'Adjustments', icon: ClipboardCheck })
    }
    return t
  }, [canViewAdjustments])

  // Standalone pages — no tabs/stats
  if (isProfilePage) {
    return (
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route path="pontaje/:biostarUserId" element={<EmployeeProfile />} />
        </Routes>
      </Suspense>
    )
  }

  if (isOrganigramPage) {
    return (
      <div className="space-y-4 md:space-y-6">
        <PageHeader
          title="Organigram"
          breadcrumbs={[
            { label: 'HR', href: '/app/hr/pontaje' },
            { label: 'Organigram' },
          ]}
        />
        <Suspense fallback={<TabLoader />}>
          <OrganigramTab />
        </Suspense>
      </div>
    )
  }

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title={
          isBonusesPage ? 'Bonuses' : isAdjustmentsPage ? 'Adjustments' : (
            <span className="flex items-center gap-3">
              Pontaje
              {showTeamToggle && (
                <span className="flex rounded-md border">
                  <button
                    onClick={() => setTeamFilter('team')}
                    className={cn(
                      'flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium transition-colors rounded-l-md',
                      teamFilter === 'team'
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <Users className="h-3.5 w-3.5" />
                    My Team
                  </button>
                  <button
                    onClick={() => setTeamFilter('all')}
                    className={cn(
                      'flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium transition-colors rounded-r-md',
                      teamFilter === 'all'
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    All
                  </button>
                </span>
              )}
            </span>
          )
        }
        breadcrumbs={[
          { label: 'HR', href: '/app/hr/pontaje' },
          ...(isBonusesPage ? [{ label: 'Bonuses' }] : isAdjustmentsPage ? [{ label: 'Adjustments' }] : [{ label: 'Pontaje' }]),
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className={showStats ? 'bg-muted' : ''} onClick={() => setShowStats(s => !s)} title="Toggle stats">
              <BarChart3 className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className={showFilters ? 'bg-muted' : ''} onClick={() => setShowFilters(s => !s)} title="Toggle filters">
              <SlidersHorizontal className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={toggleDashboardWidget} title={isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}>
              <LayoutDashboard className="h-4 w-4" />
            </Button>
            {canExport && (
              <Button variant="ghost" size="icon" className="hidden md:inline-flex" asChild title="Export">
                <a href={hrApi.exportUrl({ year: filters.year, month: filters.month })} download>
                  <Download className="h-4 w-4" />
                </a>
              </Button>
            )}
            {isBonusesPage && (
              <Button size="icon" onClick={() => setBonusAddTrigger(n => n + 1)} title="Add Bonus">
                <Plus className="h-4 w-4" />
              </Button>
            )}
            {!isMobile && !isBonusesPage && tabs.length > 1 && (
              <Tabs value={isAdjustmentsPage ? 'adjustments' : 'pontaje'} onValueChange={(v) => navigate(`/app/hr/${v}`)}>
                <TabsList className="w-auto">
                  {tabs.map((t) => {
                    const val = t.to.split('/').pop()!
                    return (
                      <TabsTrigger key={val} value={val}>
                        <t.icon className="h-4 w-4" />
                        {t.label}
                      </TabsTrigger>
                    )
                  })}
                </TabsList>
              </Tabs>
            )}
          </div>
        }
      />

      {/* Mobile tab nav */}
      {!isBonusesPage && isMobile && tabs.length > 1 && (
        <Tabs value={isAdjustmentsPage ? 'adjustments' : 'pontaje'} onValueChange={(v) => navigate(`/app/hr/${v}`)}>
          <MobileBottomTabs>
            <TabsList className="w-full">
              {tabs.map((t) => {
                const val = t.to.split('/').pop()!
                return (
                  <TabsTrigger key={val} value={val}>
                    <t.icon className="h-4 w-4" />
                    {t.label}
                  </TabsTrigger>
                )
              })}
            </TabsList>
          </MobileBottomTabs>
        </Tabs>
      )}

      {/* Tab content */}
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route index element={<Navigate to="pontaje" replace />} />
          <Route path="pontaje" element={<PontajeTab showStats={showStats} showFilters={showFilters} managerFilter={managerFilter} />} />
          <Route path="bonuses" element={<BonusesTab canViewAmounts={canViewAmounts} showStats={showStats} showFilters={showFilters} addTrigger={bonusAddTrigger} />} />
          {canViewAdjustments && <Route path="adjustments" element={<AdjustmentsTab showStats={showStats} showFilters={showFilters} />} />}
          <Route path="organigram" element={<OrganigramTab />} />
        </Routes>
      </Suspense>
    </div>
  )
}
