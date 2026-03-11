import { lazy, Suspense, useState } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  FileStack,
  Import,
  LayoutDashboard,
  Plus,
  RefreshCw,
  SlidersHorizontal,
  Tags,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { efacturaApi } from '@/api/efactura'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { useIsMobile } from '@/hooks/useMediaQuery'
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
  const isMobile = useIsMobile()
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('efactura_status')
  const [syncOpen, setSyncOpen] = useState(false)
  const [showHidden, setShowHidden] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [mappingAddTrigger, setMappingAddTrigger] = useState(0)
  const [mappingImportTrigger, setMappingImportTrigger] = useState(0)
  const [search, setSearch] = useState('')
  const location = useLocation()
  const activeEfTab = tabs.find(t => location.pathname.startsWith(t.to))
  const isOnMappingsTab = location.pathname.includes('/mappings')

  const { data: unallocatedCount } = useQuery({
    queryKey: ['efactura-unallocated-count'],
    queryFn: () => efacturaApi.getUnallocatedCount(),
  })

  const { data: hiddenCount } = useQuery({
    queryKey: ['efactura-hidden-count'],
    queryFn: () => efacturaApi.getHiddenCount(),
  })

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="e-Factura"
        breadcrumbs={[
          { label: 'e-Factura', shortLabel: 'e-Fact.' },
          { label: activeEfTab?.label ?? 'Unallocated' },
        ]}
        search={!isOnMappingsTab ? (
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={isMobile ? 'Search...' : 'Search supplier, invoice#...'}
            className={isMobile ? 'w-40' : 'w-48'}
          />
        ) : undefined}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className={`hidden md:inline-flex ${showFilters ? 'bg-muted' : ''}`} onClick={() => setShowFilters(s => !s)} title="Toggle filters">
              <SlidersHorizontal className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={toggleDashboardWidget} title={isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}>
              <LayoutDashboard className="h-4 w-4" />
            </Button>
            {isOnMappingsTab && (
              <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={() => setMappingImportTrigger(n => n + 1)} title="Import from Invoices">
                <Import className="h-4 w-4" />
              </Button>
            )}
            {isOnMappingsTab && (
              <Button size="icon" className="hidden md:inline-flex" onClick={() => setMappingAddTrigger(n => n + 1)} title="Add Mapping / Type">
                <Plus className="h-4 w-4" />
              </Button>
            )}
            <Button size="icon" onClick={() => setSyncOpen(true)} title="Sync">
              <RefreshCw className="h-4 w-4" />
            </Button>
            {!isMobile && (
              <Tabs value={location.pathname.split('/').pop() || 'unallocated'} onValueChange={(v) => navigate(`/app/efactura/${v}`)}>
                <TabsList className="w-auto">
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
              </Tabs>
            )}
          </div>
        }
      />

      {/* Mobile tab nav */}
      {isMobile && (
        <Tabs value={location.pathname.split('/').pop() || 'unallocated'} onValueChange={(v) => navigate(`/app/efactura/${v}`)}>
          <MobileBottomTabs>
            <TabsList className="w-full">
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
          </MobileBottomTabs>
        </Tabs>
      )}

      {/* Show Hidden filter (unallocated only, behind filter toggle) */}
      {showFilters && !isOnMappingsTab && (
        <div className="flex items-center gap-2">
          <Switch id="show-hidden" checked={showHidden} onCheckedChange={setShowHidden} />
          <Label htmlFor="show-hidden" className="text-xs cursor-pointer text-muted-foreground">
            Show Hidden ({hiddenCount ?? 0})
          </Label>
        </div>
      )}

      {/* Tab content */}
      <Suspense fallback={<TabLoader />}>
        <Routes>
          <Route index element={<Navigate to="unallocated" replace />} />
          <Route path="unallocated" element={<UnallocatedTab showHidden={showHidden} showFilters={showFilters} search={search} />} />
          <Route path="mappings" element={<MappingsTab showFilters={showFilters} addTrigger={mappingAddTrigger} importTrigger={mappingImportTrigger} />} />
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
