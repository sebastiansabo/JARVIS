import { lazy, Suspense, useMemo, useState } from 'react'
import { Routes, Route, Navigate, useMatch, useNavigate } from 'react-router-dom'
import { BarChart3, Download, FileCheck, FileSpreadsheet, Fingerprint, GraduationCap, LayoutDashboard, Pencil, Plus, Users, CalendarClock, Wallet, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { hrApi } from '@/api/hr'
import { useHrStore } from '@/stores/hrStore'
import { useAuthStore } from '@/stores/authStore'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { useIsMobile, useIsTablet } from '@/hooks/useMediaQuery'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'

const BonusesTab = lazy(() => import('./BonusesTab'))
const PontajeTab = lazy(() => import('./PontajeTab'))

const TimesheetTab = lazy(() => import('./TimesheetTab'))
const EmployeeProfile = lazy(() => import('./EmployeeProfile'))
const OrganigramTab = lazy(() => import('./OrganigramTab'))
const SincronOrganigramView = lazy(() => import('./SincronOrganigramView'))
const SincronOrgBuilder = lazy(() => import('./SincronOrgBuilder'))
const EmployeesTab = lazy(() => import('./EmployeesTab'))
const Employee360 = lazy(() => import('./Employee360'))
const LeavePermitsTab = lazy(() => import('./LeavePermitsTab'))
const LeavesTab = lazy(() => import('./LeavesTab'))
const CoursesTab = lazy(() => import('./CoursesTab'))
const CourseDetail = lazy(() => import('./CourseDetail'))
const ReportsTab = lazy(() => import('./ReportsTab'))
const TimeBankTab = lazy(() => import('./TimeBankTab'))
const VerificationTab = lazy(() => import('./VerificationTab'))

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
  const isTablet = useIsTablet()
  const isSmall = isMobile || isTablet
  const isProfilePage = useMatch('/app/hr/pontaje/:biostarUserId')
  const isBonusesPage = useMatch('/app/hr/bonuses')

  const isOrganigramPage = useMatch('/app/hr/organigram')
  const isTimesheetsPage = useMatch('/app/hr/timesheets')
  const isEmployeesPage = useMatch('/app/hr/employees')
  const isLeavePermitsPage = useMatch('/app/hr/leave-permits')
  const isLeavesPage = useMatch('/app/hr/leaves')
  const isCoursesPage = useMatch('/app/hr/courses')
  const isCourseDetailPage = useMatch('/app/hr/courses/:courseId')
  const isReportsPage = useMatch('/app/hr/reports')
  const isTimeBankPage = useMatch('/app/hr/time-bank')
  const isVerificationPage = useMatch('/app/hr/verification')
  const isEmployee360Page = useMatch('/app/hr/employees/:userId')
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('hr_summary')
  const filters = useHrStore((s) => s.filters)

  const user = useAuthStore((s) => s.user)
  const authLoading = useAuthStore((s) => s.isLoading)
  const perms = user?.permissions
  const scopes = user?.permission_scopes

  const showFilters = true
  const [bonusAddTrigger, setBonusAddTrigger] = useState(0)
  const [search, setSearch] = useState('')
  const [orgView, setOrgView] = useState<'structure' | 'sincron'>('structure')
  const [sincronEditMode, setSincronEditMode] = useState(false)
  const isAdmin = user?.can_access_settings ?? false
  const canExport = perms?.['hr.bonuses.export'] ?? false
  const canViewAmounts = perms?.['hr.bonuses.view_amounts'] ?? false

  const canViewTeamPontaje = perms?.['hr.team_pontaje.view'] ?? false
  const teamPontajeScope = scopes?.['hr.team_pontaje.view'] ?? 'deny'
  const canViewStructure = perms?.['hr.structure.view'] ?? false
  const canViewTimesheets = authLoading || !user ? true : (perms?.['hr.timesheets.view'] ?? false)
  const canViewEmployees = authLoading || !user ? true : (perms?.['hr.employees.view'] ?? false)
  // Pontaje view: default true while auth loads; once loaded, gate on view_original
  const canViewPontaje = authLoading || !user ? true : (perms?.['hr.pontaje.view_original'] ?? true)
  const canViewBonuses = authLoading || !user ? true : (perms?.['hr.bonuses.view'] ?? true)
  const canViewLeavePermits = authLoading || !user ? true : (perms?.['hr.leave_permissions.view'] ?? true)
  const canViewLeaves = authLoading || !user ? true : (user?.can_access_hr ?? false)
  const canViewCourses = authLoading || !user ? true : (perms?.['hr.courses.view'] ?? (user?.can_access_hr ?? false))
  const canViewReports = authLoading || !user ? true : (user?.can_access_hr ?? false)
  const canViewTimeBank = authLoading || !user ? true : (user?.can_access_hr ?? false)
  const canViewVerification = authLoading || !user ? true : (user?.can_access_hr ?? false)

  // Manager filter for pontaje route (still accessible via direct URL)
  const forceTeamFilter = canViewTeamPontaje && teamPontajeScope !== 'all' && teamPontajeScope !== 'deny'
  const managerFilter = forceTeamFilter

  const tabs = useMemo(() => {
    const t: { to: string; label: string; icon: typeof Fingerprint }[] = []
    if (canViewEmployees) {
      t.push({ to: '/app/hr/employees', label: 'Employees', icon: Users })
    }
    t.push({ to: '/app/hr/pontaje', label: 'Pontaje', icon: Fingerprint })
    if (canViewTimesheets) {
      t.push({ to: '/app/hr/timesheets', label: 'Timesheets', icon: FileSpreadsheet })
    }

    if (canViewLeavePermits) {
      t.push({ to: '/app/hr/leave-permits', label: 'Bilete Invoire', icon: FileCheck })
    }
    if (canViewLeaves) {
      t.push({ to: '/app/hr/leaves', label: 'Leaves', icon: CalendarClock })
    }
    if (canViewTimeBank) {
      t.push({ to: '/app/hr/time-bank', label: 'Time Bank', icon: Wallet })
    }
    if (canViewCourses) {
      t.push({ to: '/app/hr/courses', label: 'Cursuri', icon: GraduationCap })
    }
    if (canViewReports) {
      t.push({ to: '/app/hr/reports', label: 'Reports', icon: BarChart3 })
    }
    if (canViewVerification) {
      t.push({ to: '/app/hr/verification', label: 'Verification', icon: ShieldCheck })
    }
    return t
  }, [canViewTimesheets, canViewEmployees, canViewLeavePermits, canViewLeaves, canViewTimeBank, canViewCourses, canViewReports, canViewVerification])

  // Standalone pages — no tabs/stats
  if (isCourseDetailPage) {
    return (
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route path="courses/:courseId" element={<CourseDetail />} />
        </Routes>
      </Suspense>
    )
  }

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
            <SearchInput value={search} onChange={setSearch} placeholder="Search..." className={isSmall ? undefined : 'w-56'} collapsible={isSmall} />
          }
        />
        <div className="flex items-center gap-2">
          <Tabs value={orgView} onValueChange={(v) => setOrgView(v as 'structure' | 'sincron')}>
            <TabsList>
              <TabsTrigger value="structure">Structure</TabsTrigger>
              <TabsTrigger value="sincron">Sincron</TabsTrigger>
            </TabsList>
          </Tabs>
          {orgView === 'sincron' && isAdmin && (
            <Button
              variant={sincronEditMode ? 'default' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => setSincronEditMode((p) => !p)}
              title={sincronEditMode ? 'View mode' : 'Edit mode'}
            >
              <Pencil className="h-4 w-4" />
            </Button>
          )}
        </div>
        {authLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : !canViewStructure ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
            You don't have permission to view the organigram.
          </div>
        ) : (
          <Suspense fallback={<TabLoader />}>
            {orgView === 'structure' ? (
              <OrganigramTab search={search} />
            ) : sincronEditMode ? (
              <SincronOrgBuilder />
            ) : (
              <SincronOrganigramView search={search} />
            )}
          </Suspense>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title={
          isBonusesPage ? 'Bonuses' : isTimesheetsPage ? 'Timesheets' : isEmployeesPage ? 'Employees' : isLeavePermitsPage ? 'Bilete de Invoire' : isLeavesPage ? 'Leaves (CO Balance)' : isTimeBankPage ? 'Time Bank' : isCoursesPage ? 'Cursuri' : isReportsPage ? 'Reports' : isVerificationPage ? 'Verification' : 'Pontaje'
        }
        breadcrumbs={[
          { label: 'HR', href: '/app/hr/employees' },
          ...(isBonusesPage ? [{ label: 'Bonuses' }] : isTimesheetsPage ? [{ label: 'Timesheets' }] : isEmployeesPage ? [{ label: 'Employees' }] : isLeavePermitsPage ? [{ label: 'Bilete de Invoire' }] : isLeavesPage ? [{ label: 'Leaves' }] : isTimeBankPage ? [{ label: 'Time Bank' }] : isCoursesPage ? [{ label: 'Cursuri' }] : isReportsPage ? [{ label: 'Reports' }] : isVerificationPage ? [{ label: 'Verification' }] : [{ label: 'Pontaje' }]),
        ]}
        search={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={isBonusesPage ? 'Search employee, event...' : 'Search by name, email, group...'}
            className={isSmall ? undefined : 'w-48'}
            collapsible={isSmall}
          />
        }
        actions={
          <div className="flex items-center gap-2">
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
              <Tabs value={isVerificationPage ? 'verification' : isReportsPage ? 'reports' : isCoursesPage ? 'courses' : isTimeBankPage ? 'time-bank' : isLeavesPage ? 'leaves' : isLeavePermitsPage ? 'leave-permits' : isEmployeesPage ? 'employees' : isTimesheetsPage ? 'timesheets' : 'pontaje'} onValueChange={(v) => navigate(`/app/hr/${v}`)}>
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
        <Tabs value={isVerificationPage ? 'verification' : isReportsPage ? 'reports' : isCoursesPage ? 'courses' : isTimeBankPage ? 'time-bank' : isLeavesPage ? 'leaves' : isLeavePermitsPage ? 'leave-permits' : isEmployeesPage ? 'employees' : isTimesheetsPage ? 'timesheets' : 'pontaje'} onValueChange={(v) => navigate(`/app/hr/${v}`)}>
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
          <Route index element={<Navigate to="employees" replace />} />
          <Route path="pontaje" element={
            canViewPontaje
              ? <PontajeTab showStats={false} showFilters={showFilters} managerFilter={managerFilter} search={search} />
              : <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">You don't have permission to view pontaje.</div>
          } />
          <Route path="bonuses" element={
            canViewBonuses
              ? <BonusesTab canViewAmounts={canViewAmounts} showStats={false} showFilters={showFilters} addTrigger={bonusAddTrigger} search={search} />
              : <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">You don't have permission to view bonuses.</div>
          } />
          {canViewTimesheets && <Route path="timesheets" element={<TimesheetTab search={search} />} />}

          {canViewEmployees && <Route path="employees" element={<EmployeesTab search={search} />} />}
          {canViewLeavePermits && <Route path="leave-permits" element={<LeavePermitsTab search={search} />} />}
          {canViewLeaves && <Route path="leaves" element={<LeavesTab search={search} />} />}
          {canViewTimeBank && <Route path="time-bank" element={<TimeBankTab search={search} />} />}
          {canViewCourses && <Route path="courses" element={<CoursesTab search={search} />} />}
          {canViewReports && <Route path="reports" element={<ReportsTab search={search} />} />}
          {canViewVerification && <Route path="verification" element={<VerificationTab />} />}
        </Routes>
      </Suspense>
    </div>
  )
}
