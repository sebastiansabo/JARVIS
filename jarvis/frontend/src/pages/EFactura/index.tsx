import { lazy, Suspense, useState } from 'react'
import { Routes, Route, Navigate, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  FileStack,
  RefreshCw,
  Tags,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { PageHeader } from '@/components/shared/PageHeader'
import { efacturaApi } from '@/api/efactura'
import { cn } from '@/lib/utils'
import { SyncDialog } from './SyncDialog'

const UnallocatedTab = lazy(() => import('./UnallocatedTab'))
const MappingsTab = lazy(() => import('./MappingsTab'))

const tabs = [
  { to: '/app/efactura/unallocated', label: 'Unallocated', icon: FileStack },
  { to: '/app/efactura/mappings', label: 'Mappings', icon: Tags },
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

export default function EFactura() {
  const [syncOpen, setSyncOpen] = useState(false)
  const [showHidden, setShowHidden] = useState(false)

  const { data: unallocatedCount } = useQuery({
    queryKey: ['efactura-unallocated-count'],
    queryFn: () => efacturaApi.getUnallocatedCount(),
  })

  const { data: hiddenCount } = useQuery({
    queryKey: ['efactura-hidden-count'],
    queryFn: () => efacturaApi.getHiddenCount(),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <PageHeader
          title="e-Factura"
          description="ANAF electronic invoicing — sync, allocate & manage"
        />
        <Button onClick={() => setSyncOpen(true)}>
          <RefreshCw className="mr-1.5 h-4 w-4" />
          Sync
        </Button>
      </div>

      {/* Tab nav */}
      <nav className="flex items-center gap-1 overflow-x-auto border-b">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                'flex shrink-0 items-center gap-1.5 border-b-2 px-4 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )
            }
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
            {tab.label === 'Unallocated' && (unallocatedCount ?? 0) > 0 && (
              <span className="ml-1 rounded-full bg-orange-100 px-1.5 py-0.5 text-xs font-semibold text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
                {unallocatedCount}
              </span>
            )}
          </NavLink>
        ))}
        <div className="ml-auto flex items-center gap-2 pb-0.5">
          <Switch id="show-hidden" checked={showHidden} onCheckedChange={setShowHidden} />
          <Label htmlFor="show-hidden" className="text-xs cursor-pointer text-muted-foreground">
            Show Hidden ({hiddenCount ?? 0})
          </Label>
        </div>
      </nav>

      {/* Tab content */}
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route index element={<Navigate to="unallocated" replace />} />
          <Route path="unallocated" element={<UnallocatedTab showHidden={showHidden} />} />
          <Route path="mappings" element={<MappingsTab />} />
          {/* Redirect removed/old routes */}
          <Route path="fetch" element={<Navigate to="/app/efactura/unallocated" replace />} />
          <Route path="invoices" element={<Navigate to="/app/efactura/unallocated" replace />} />
          <Route path="connections" element={<Navigate to="/app/settings/connectors" replace />} />
          <Route path="sync" element={<Navigate to="/app/efactura/unallocated" replace />} />
        </Routes>
      </Suspense>

      {/* Sync modal */}
      <SyncDialog open={syncOpen} onOpenChange={setSyncOpen} />
    </div>
  )
}
