import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Users, Car, Upload, BarChart3, PieChart, UserCheck, Ban } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { StatCard } from '@/components/shared/StatCard'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { BrandFilter } from '@/components/shared/BrandFilter'
import { crmApi, type CrmStats } from '@/api/crm'
import DealsTab from './DealsTab'
import StatisticsTab from './StatisticsTab'
import ClientStatsTab from './ClientStatsTab'
import ImportTab from './ImportTab'

export default function Crm() {
  const isMobile = useIsMobile()
  const [tab, setTab] = useState('dashboard')
  const [search, setSearch] = useState('')
  const [statsShowFilters, setStatsShowFilters] = useState(false)
  const [brandFilterKey, setBrandFilterKey] = useState<string | null>(null)
  const [filterBrand, setFilterBrand] = useState('')
  const { data: stats } = useQuery({ queryKey: ['crm-stats'], queryFn: crmApi.getStats })

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <div className="space-y-4 md:space-y-6">
        <PageHeader
          title="Samsaru"
          breadcrumbs={[
            { label: 'Samsaru' },
            { label: tab === 'dashboard' ? 'Dashboard' : tab === 'deals' ? 'Sales' : tab === 'clients' ? 'Clients' : tab === 'statistics' ? 'Statistics' : tab === 'import' ? 'Import' : 'Blacklist' },
          ]}
          search={(tab === 'deals' || tab === 'clients' || tab === 'blacklist') ? (
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder={tab === 'deals' ? 'Search model...' : 'Search name...'}
              className={isMobile ? 'w-40' : 'w-48'}
            />
          ) : undefined}
          actions={
            <div className="flex items-center gap-2">
              {!isMobile && (
                <TabsList className="w-auto">
                  <TabsTrigger value="dashboard"><BarChart3 className="h-4 w-4" />Dashboard</TabsTrigger>
                  <TabsTrigger value="deals"><Car className="h-4 w-4" />Sales</TabsTrigger>
                  <TabsTrigger value="clients"><UserCheck className="h-4 w-4" />Clients</TabsTrigger>
                  <TabsTrigger value="statistics"><PieChart className="h-4 w-4" />Statistics</TabsTrigger>
                  <TabsTrigger value="import"><Upload className="h-4 w-4" />Import</TabsTrigger>
                  <TabsTrigger value="blacklist"><Ban className="h-4 w-4" />Blacklist</TabsTrigger>
                </TabsList>
              )}
            </div>
          }
        />

        {isMobile && (
          <MobileBottomTabs>
            <TabsList className="w-full">
              <TabsTrigger value="dashboard"><BarChart3 className="h-4 w-4" />Dashboard</TabsTrigger>
              <TabsTrigger value="deals"><Car className="h-4 w-4" />Sales</TabsTrigger>
              <TabsTrigger value="clients"><UserCheck className="h-4 w-4" />Clients</TabsTrigger>
              <TabsTrigger value="statistics"><PieChart className="h-4 w-4" />Statistics</TabsTrigger>
              <TabsTrigger value="import"><Upload className="h-4 w-4" />Import</TabsTrigger>
              <TabsTrigger value="blacklist"><Ban className="h-4 w-4" />Blacklist</TabsTrigger>
            </TabsList>
          </MobileBottomTabs>
        )}

        {/* Brand quick-filter */}
        {!isMobile && (tab === 'deals' || tab === 'dashboard') && (
          <BrandFilter
            mode="brand"
            value={brandFilterKey}
            onSelect={(item) => {
              setBrandFilterKey(item?.key ?? null)
              setFilterBrand(item?.brandName ?? '')
            }}
          />
        )}

        <TabsContent value="dashboard" className="space-y-4">
          {stats && <DashboardContent stats={stats} />}
        </TabsContent>

        <TabsContent value="deals"><DealsTab showStats search={search} brandFilter={filterBrand} /></TabsContent>
        <TabsContent value="clients"><ClientStatsTab search={search} /></TabsContent>
        <TabsContent value="statistics"><StatisticsTab showFilters={statsShowFilters} setShowFilters={setStatsShowFilters} showStats /></TabsContent>
        <TabsContent value="import"><ImportTab /></TabsContent>
        <TabsContent value="blacklist"><ClientStatsTab blacklistOnly search={search} /></TabsContent>
      </div>
    </Tabs>
  )
}

function DashboardContent({ stats }: { stats: CrmStats }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <StatCard title="Total Clients" value={stats.clients.total.toLocaleString()} description={`${stats.clients.persons} persons, ${stats.clients.companies} companies`} icon={<Users className="h-4 w-4" />} />
        <StatCard title="Car Deals" value={stats.deals.total.toLocaleString()} description={`${stats.deals.new_cars} NW, ${stats.deals.used_cars} GW`} icon={<Car className="h-4 w-4" />} />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Deal Breakdown</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span>New Cars (NW)</span><Badge variant="secondary">{stats.deals.new_cars.toLocaleString()}</Badge></div>
            <div className="flex justify-between"><span>Used Cars (GW)</span><Badge variant="secondary">{stats.deals.used_cars.toLocaleString()}</Badge></div>
            <div className="flex justify-between"><span>Brands</span><Badge variant="outline">{stats.deals.brands}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Last Imports</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {(['nw', 'gw', 'crm_clients'] as const).map(type => {
              const imp = stats.last_imports[type]
              return (
                <div key={type} className="flex justify-between">
                  <span className="font-medium">{type.toUpperCase()}</span>
                  {imp ? (
                    <span className="text-muted-foreground">{new Date(imp.created_at).toLocaleDateString()} — {imp.total_rows} rows</span>
                  ) : (
                    <Badge variant="outline">Never</Badge>
                  )}
                </div>
              )
            })}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
