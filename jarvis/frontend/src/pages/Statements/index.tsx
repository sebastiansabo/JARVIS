import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, FileText, LinkIcon, Download, LayoutDashboard, BarChart3, Clock, CheckCircle, DollarSign, SlidersHorizontal, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { statementsApi } from '@/api/statements'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
import type { TransactionFilters } from '@/types/statements'
import { useState } from 'react'

const TransactionsTab = lazy(() => import('./TransactionsTab'))
const FilesTab = lazy(() => import('./FilesTab'))
const MappingsTab = lazy(() => import('./MappingsTab'))

const tabs = [
  { to: '/app/statements/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/app/statements/files', label: 'Statements', icon: FileText },
  { to: '/app/statements/mappings', label: 'Mappings', icon: LinkIcon },
] as const

function TabLoader() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  )
}

export default function Statements() {
  const navigate = useNavigate()
  const location = useLocation()
  const isMobile = useIsMobile()
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('statements_summary')
  const [filters] = useState<TransactionFilters>({})
  const [showStats, setShowStats] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [mappingAddOpen, setMappingAddOpen] = useState(false)
  const isOnFilesTab = location.pathname.includes('/files')
  const isOnMappingsTab = location.pathname.includes('/mappings')

  const { data: summary, isLoading } = useQuery({
    queryKey: ['statements-summary', filters],
    queryFn: () => statementsApi.getSummary(filters),
  })

  const fmtAmount = (v: number) =>
    new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(v)

  const bs = summary?.by_status
  const totalCount = (bs?.pending?.count ?? 0) + (bs?.resolved?.count ?? 0) + (bs?.ignored?.count ?? 0) + (bs?.merged?.count ?? 0)
  const totalAmount = (bs?.pending?.total ?? 0) + (bs?.resolved?.total ?? 0) + (bs?.ignored?.total ?? 0) + (bs?.merged?.total ?? 0)

  const activeTab = tabs.find(t => location.pathname.startsWith(t.to))

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Bank Statements"
        breadcrumbs={[
          { label: 'Bank Statements', shortLabel: 'Stmt.' },
          { label: activeTab?.label ?? 'Transactions' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className={showStats ? 'bg-muted' : ''} onClick={() => setShowStats(s => !s)} title="Toggle stats">
              <BarChart3 className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className={`hidden md:inline-flex ${showFilters ? 'bg-muted' : ''}`} onClick={() => setShowFilters(s => !s)} title="Toggle filters">
              <SlidersHorizontal className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={toggleDashboardWidget} title={isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}>
              <LayoutDashboard className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="hidden md:inline-flex" asChild title="Export CSV">
              <a href={statementsApi.exportUrl(filters)} download>
                <Download className="h-4 w-4" />
              </a>
            </Button>
            {isOnFilesTab && (
              <Button size="icon" className="hidden md:inline-flex" onClick={() => setUploadOpen(true)} title="Upload Statement">
                <Plus className="h-4 w-4" />
              </Button>
            )}
            {isOnMappingsTab && (
              <Button size="icon" className="hidden md:inline-flex" onClick={() => setMappingAddOpen(true)} title="Add Mapping">
                <Plus className="h-4 w-4" />
              </Button>
            )}
            {!isMobile && (
              <Tabs value={location.pathname.split('/').pop() || 'transactions'} onValueChange={(v) => navigate(`/app/statements/${v}`)}>
                <TabsList className="w-auto">
                  {tabs.map((tab) => {
                    const val = tab.to.split('/').pop()!
                    return (
                      <TabsTrigger key={val} value={val}>
                        <tab.icon className="h-4 w-4" />
                        {tab.label}
                      </TabsTrigger>
                    )
                  })}
                </TabsList>
              </Tabs>
            )}
          </div>
        }
      />

      {/* Summary stats */}
      <div className={`grid grid-cols-2 gap-3 lg:grid-cols-4 ${showStats ? '' : 'hidden'}`}>
        <StatCard
          title="Total Transactions"
          value={totalCount}
          icon={<ArrowLeftRight className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Pending"
          value={summary?.by_status?.pending?.count ?? 0}
          icon={<Clock className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Resolved"
          value={summary?.by_status?.resolved?.count ?? 0}
          icon={<CheckCircle className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Total Amount"
          value={totalAmount !== 0 ? `${fmtAmount(Math.abs(totalAmount))} RON` : '—'}
          icon={<DollarSign className="h-4 w-4" />}
          isLoading={isLoading}
        />
      </div>

      {/* Mobile tab nav */}
      {isMobile && (
        <Tabs value={location.pathname.split('/').pop() || 'transactions'} onValueChange={(v) => navigate(`/app/statements/${v}`)}>
          <MobileBottomTabs>
            <TabsList className="w-full">
              {tabs.map((tab) => {
                const val = tab.to.split('/').pop()!
                return (
                  <TabsTrigger key={val} value={val}>
                    <tab.icon className="h-4 w-4" />
                    {tab.label}
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
          <Route index element={<Navigate to="transactions" replace />} />
          <Route path="transactions" element={<TransactionsTab showFilters={showFilters} />} />
          <Route path="files" element={<FilesTab showFilters={showFilters} uploadOpen={uploadOpen} onUploadOpenChange={setUploadOpen} />} />
          <Route path="mappings" element={<MappingsTab showFilters={showFilters} addOpen={mappingAddOpen} onAddOpenChange={setMappingAddOpen} />} />
        </Routes>
      </Suspense>
    </div>
  )
}
