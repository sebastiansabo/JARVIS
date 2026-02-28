import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, FileText, LinkIcon, Download, LayoutDashboard } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { statementsApi } from '@/api/statements'
import { cn } from '@/lib/utils'
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
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('statements_summary')
  const [filters] = useState<TransactionFilters>({})

  const { data: summary, isLoading } = useQuery({
    queryKey: ['statements-summary', filters],
    queryFn: () => statementsApi.getSummary(filters),
  })

  const fmtAmount = (v: number) =>
    new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(v)

  const bs = summary?.by_status
  const totalCount = (bs?.pending?.count ?? 0) + (bs?.resolved?.count ?? 0) + (bs?.ignored?.count ?? 0) + (bs?.merged?.count ?? 0)
  const totalAmount = (bs?.pending?.total ?? 0) + (bs?.resolved?.total ?? 0) + (bs?.ignored?.total ?? 0) + (bs?.merged?.total ?? 0)

  return (
    <div className="space-y-4">
      <PageHeader
        title="Bank Statements"
        breadcrumbs={[{ label: 'Bank Statements' }]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={toggleDashboardWidget}>
              <LayoutDashboard className="mr-1.5 h-3.5 w-3.5" />
              {isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}
            </Button>
            <Button variant="outline" asChild>
              <a href={statementsApi.exportUrl(filters)} download>
                <Download className="mr-1.5 h-4 w-4" />
                Export CSV
              </a>
            </Button>
          </div>
        }
      />

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
      <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
        <nav className="flex w-max gap-1 border-b md:w-auto">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.to === '/app/statements/transactions'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium transition-colors',
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
      </div>

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
