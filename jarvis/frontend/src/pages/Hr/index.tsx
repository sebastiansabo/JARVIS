import { lazy, Suspense, useMemo, useState } from 'react'
import { Routes, Route, Navigate, useMatch, useNavigate } from 'react-router-dom'
import { ClipboardCheck, Download, FileSpreadsheet, Fingerprint, LayoutDashboard, BarChart3, SlidersHorizontal, Plus, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { hrApi } from '@/api/hr'
import { useHrStore } from '@/stores/hrStore'
import { useAuthStore } from '@/stores/authStore'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
import { cn } from '@/lib/utils'

const BonusesTab = lazy(() => import('./BonusesTab'))
const PontajeTab = lazy(() => import('./PontajeTab'))
const AdjustmentsTab = lazy(() => import('./AdjustmentsTab'))
const TimesheetTab = lazy(() => import('./TimesheetTab'))
const EmployeeProfile = lazy(() => import('./EmployeeProfile'))
const OrganigramTab = lazy(() => import('./OrganigramTab'))
const EmployeesTab = lazy(() => import('./EmployeesTab'))
const Employee360 = lazy(() => import('./Employee360'))

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
  const isTimesheetsPage = useMatch('/app/hr/timesheets')
  const isEmployeesPage = useMatch('/app/hr/employees')
  const isEmployee360Page = useMatch('/app/hr/employees/:userId')
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('hr_summary')
  const filters = useHrStore((s) => s.filters)

  const user = useAuthStore((s) => s.user)
  const authLoading = useAuthStore((s) => s.isLoading)
  const perms = user?.permissions
  const scopes = user?.permission_scopes

  const [showStats, setShowStats] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [bonusAddTrigger, setBonusAddTrigger] = useState(0)
  const [search, setSearch] = useState('')
  const canExport = perms?.['hr.bonuses.export'] ?? false
  const canViewAmounts = perms?.['hr.bonuses.view_amounts'] ?? false
  const canViewAdjustments = perms?.['hr.pontaje_adjustments.view'] ?? false
  const canViewTeamPontaje = perms?.['hr.team_pontaje.view'] ?? false
  const teamPontajeScope = scopes?.['hr.team_pontaje.view'] ?? 'deny'
  const canViewStructure = perms?.['hr.structure.view'] ?? false
  const canViewTimesheets = authLoading || !user ? true : (perms?.['hr.timesheets.view'] ?? false)
  const canViewEmployees = authLoading || !user ? true : (perms?.['hr.employees.view'] ?? false)
  // Pontaje view: default true while auth loads; once loaded, gate on view_original
  const canViewPontaje = authLoading || !user ? true : (perms?.['hr.pontaje.view_original'] ?? true)
  const canViewBonuses = authLoading || !user ? true : (perms?.['hr.bonuses.view'] ?? true)

  // Team filter — lifted here so it renders next to page title
  // scope='all' → Admin: toggle visible, can switch between All/My Team
  // scope='department'/'own' → Manager: always filtered by organigram, no toggle
  const [teamFilter, setTeamFilter] = useState<'team' | 'all'>('all')
  const showTeamToggle = canViewTeamPontaje && teamPontajeScope === 'all'
  const forceTeamFilter = canViewTeamPontaje && teamPontajeScope !== 'all' && teamPontajeScope !== 'deny'
  const managerFilter = forceTeamFilter || (showTeamToggle && teamFilter === 'team')

  const tabs = useMemo(() => {
    const t: { to: string; label: string; icon: typeof Fingerprint }[] = [
      { to: '/app/hr/pontaje', label: 'Pontaje', icon: Fingerprint },
    ]
    if (canViewTimesheets) {
      t.push({ to: '/app/hr/timesheets', label: 'Timesheets', icon: FileSpreadsheet })
    }
    if (canViewAdjustments) {
      t.push({ to: '/app/hr/adjustments', label: 'Adjustments', icon: ClipboardCheck })
    }
    if (canViewEmployees) {
      t.push({ to: '/app/hr/employees', label: 'Employees', icon: Users })
    }
    return t
  }, [canViewTimesheets, canViewAdjustments, canViewEmployees])

  // Standalone pages — no tabs/stats
  if (isEmployee360Page) {
    return (
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route path="employees/:userId" element={<Employee360 />} />
        </Routes>
      </Suspense>
    )
  }

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
          search={
            <SearchInput value={search} onChange={setSearch} placeholder={isMobile ? 'Search...' : 'Search by name, node, company...'} className={isMobile ? 'w-40' : 'w-56'} />
          }
        />
        {authLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : !canViewStructure ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
            You don't have permission to view the organigram.
          </div>
        ) : (
          <Suspense fallback={<TabLoader />}>
            <OrganigramTab search={search} />
          </Suspense>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title={
          isBonusesPage ? 'Bonuses' : isAdjustmentsPage ? 'Adjustments' : isTimesheetsPage ? 'Timesheets' : isEmployeesPage ? 'Employees' : (
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
          ...(isBonusesPage ? [{ label: 'Bonuses' }] : isAdjustmentsPage ? [{ label: 'Adjustments' }] : isTimesheetsPage ? [{ label: 'Timesheets' }] : isEmployeesPage ? [{ label: 'Employees' }] : [{ label: 'Pontaje' }]),
        ]}
        search={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={isBonusesPage ? 'Search employee, event...' : isAdjustmentsPage ? 'Search by name...' : 'Search by name, email, group...'}
            className={isMobile ? 'w-40' : 'w-48'}
          />
        }
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
              <Tabs value={isEmployeesPage ? 'employees' : isAdjustmentsPage ? 'adjustments' : isTimesheetsPage ? 'timesheets' : 'pontaje'} onValueChange={(v) => navigate(`/app/hr/${v}`)}>
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
        <Tabs value={isEmployeesPage ? 'employees' : isAdjustmentsPage ? 'adjustments' : isTimesheetsPage ? 'timesheets' : 'pontaje'} onValueChange={(v) => navigate(`/app/hr/${v}`)}>
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
          <Route path="pontaje" element={
            canViewPontaje
              ? <PontajeTab showStats={showStats} showFilters={showFilters} managerFilter={managerFilter} search={search} />
              : <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">You don't have permission to view pontaje.</div>
          } />
          <Route path="bonuses" element={
            canViewBonuses
              ? <BonusesTab canViewAmounts={canViewAmounts} showStats={showStats} showFilters={showFilters} addTrigger={bonusAddTrigger} search={search} />
              : <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">You don't have permission to view bonuses.</div>
          } />
          {canViewTimesheets && <Route path="timesheets" element={<TimesheetTab search={search} />} />}
          {canViewAdjustments && <Route path="adjustments" element={<AdjustmentsTab showStats={showStats} showFilters={showFilters} search={search} />} />}
          {canViewEmployees && <Route path="employees" element={<EmployeesTab search={search} />} />}
        </Routes>
      </Suspense>
    </div>
  )
}
