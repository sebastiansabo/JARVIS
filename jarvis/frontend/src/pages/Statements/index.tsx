import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, FileText, LinkIcon, Download, LayoutDashboard, BarChart3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('statements_summary')
  const [filters] = useState<TransactionFilters>({})
  const [showStats, setShowStats] = useState(false)

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
          { label: 'Bank Statements' },
          { label: activeTab?.label ?? 'Transactions' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setShowStats(s => !s)}>
              <BarChart3 className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="md:size-auto md:px-3" onClick={toggleDashboardWidget}>
              <LayoutDashboard className="h-3.5 w-3.5 md:mr-1.5" />
              <span className="hidden md:inline">{isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}</span>
            </Button>
            <Button variant="outline" size="icon" className="md:size-auto md:px-4" asChild>
              <a href={statementsApi.exportUrl(filters)} download>
                <Download className="h-4 w-4 md:mr-1.5" />
                <span className="hidden md:inline">Export CSV</span>
              </a>
            </Button>
          </div>
        }
      />

      {/* Summary stats */}
      <div className={`grid grid-cols-2 gap-3 lg:grid-cols-4 ${showStats ? '' : 'hidden md:grid'}`}>
        <StatCard
          title="Total Transactions"
          value={totalCount}
          icon={<ArrowLeftRight className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Pending"
          value={summary?.by_status?.pending?.count ?? 0}
          icon={<ArrowLeftRight className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Resolved"
          value={summary?.by_status?.resolved?.count ?? 0}
          icon={<ArrowLeftRight className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Total Amount"
          value={totalAmount !== 0 ? `${fmtAmount(Math.abs(totalAmount))} RON` : '—'}
          icon={<ArrowLeftRight className="h-4 w-4" />}
          isLoading={isLoading}
        />
      </div>

      {/* Tab nav */}
      <Tabs value={location.pathname.split('/').pop() || 'transactions'} onValueChange={(v) => navigate(`/app/statements/${v}`)}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
          <TabsList className="w-max md:w-auto">
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
        </div>
      </Tabs>

      {/* Tab content */}
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route index element={<Navigate to="transactions" replace />} />
          <Route path="transactions" element={<TransactionsTab />} />
          <Route path="files" element={<FilesTab />} />
          <Route path="mappings" element={<MappingsTab />} />
        </Routes>
      </Suspense>
    </div>
  )
}
