import { lazy, Suspense, useState } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  FileStack,
  LayoutDashboard,
  RefreshCw,
  Tags,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { PageHeader } from '@/components/shared/PageHeader'
import { efacturaApi } from '@/api/efactura'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
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
  const navigate = useNavigate()
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('efactura_status')
  const [syncOpen, setSyncOpen] = useState(false)
  const [showHidden, setShowHidden] = useState(false)
  const location = useLocation()
  const activeEfTab = tabs.find(t => location.pathname.startsWith(t.to))

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
      <PageHeader
        title="e-Factura"
        breadcrumbs={[
          { label: 'e-Factura' },
          { label: activeEfTab?.label ?? 'Unallocated' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="md:size-auto md:px-3" onClick={toggleDashboardWidget}>
              <LayoutDashboard className="h-3.5 w-3.5 md:mr-1.5" />
              <span className="hidden md:inline">{isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}</span>
            </Button>
            <Button size="icon" className="md:size-auto md:px-4" onClick={() => setSyncOpen(true)}>
              <RefreshCw className="h-4 w-4 md:mr-1.5" />
              <span className="hidden md:inline">Sync</span>
            </Button>
          </div>
        }
      />

      {/* Tab nav */}
      <Tabs value={location.pathname.split('/').pop() || 'unallocated'} onValueChange={(v) => navigate(`/app/efactura/${v}`)}>
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
            <TabsList className="w-max md:w-auto">
              <TabsTrigger value="unallocated">
                <FileStack className="h-4 w-4" />
                Unallocated
                {(unallocatedCount ?? 0) > 0 && (
                  <span className="ml-1 rounded-full bg-orange-100 px-1.5 py-0.5 text-xs font-semibold text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
                    {unallocatedCount}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="mappings">
                <Tags className="h-4 w-4" />
                Mappings
              </TabsTrigger>
            </TabsList>
          </div>
          <div className="flex items-center gap-2 md:ml-auto">
            <Switch id="show-hidden" checked={showHidden} onCheckedChange={setShowHidden} />
            <Label htmlFor="show-hidden" className="text-xs cursor-pointer text-muted-foreground">
              Show Hidden ({hiddenCount ?? 0})
            </Label>
          </div>
        </div>
      </Tabs>

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
