import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Users, Car, Upload, BarChart3, PieChart, UserCheck, Ban, Filter } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { crmApi, type CrmStats } from '@/api/crm'
import DealsTab from './DealsTab'
import StatisticsTab from './StatisticsTab'
import ClientStatsTab from './ClientStatsTab'
import ImportTab from './ImportTab'

export default function Crm() {
  const isMobile = useIsMobile()
  const [tab, setTab] = useState('dashboard')
  const [showStats, setShowStats] = useState(false)
  const [dealsShowStats, setDealsShowStats] = useState(false)
  const [statsShowFilters, setStatsShowFilters] = useState(false)
  const [statsShowCards, setStatsShowCards] = useState(false)
  const { data: stats } = useQuery({ queryKey: ['crm-stats'], queryFn: crmApi.getStats })

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Samsaru"
        breadcrumbs={[
          { label: 'Samsaru' },
          { label: tab === 'dashboard' ? 'Dashboard' : tab === 'deals' ? 'Sales' : tab === 'clients' ? 'Clients' : tab === 'statistics' ? 'Statistics' : tab === 'import' ? 'Import' : 'Blacklist' },
        ]}
        actions={isMobile ? (
          tab === 'dashboard' ? (
            <Button variant="ghost" size="icon" onClick={() => setShowStats(s => !s)}>
              <BarChart3 className="h-4 w-4" />
            </Button>
          ) : tab === 'deals' ? (
            <Button variant="ghost" size="icon" onClick={() => setDealsShowStats(s => !s)}>
              <BarChart3 className="h-4 w-4" />
            </Button>
          ) : tab === 'statistics' ? (
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setStatsShowCards(s => !s)}>
                <BarChart3 className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setStatsShowFilters(s => !s)}>
                <Filter className="h-4 w-4" />
              </Button>
            </div>
          ) : undefined
        ) : undefined}
      />

      <Tabs value={tab} onValueChange={setTab}>
        {isMobile ? (
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
        ) : (
          <TabsList className="w-auto">
            <TabsTrigger value="dashboard"><BarChart3 className="h-4 w-4" />Dashboard</TabsTrigger>
            <TabsTrigger value="deals"><Car className="h-4 w-4" />Sales</TabsTrigger>
            <TabsTrigger value="clients"><UserCheck className="h-4 w-4" />Clients</TabsTrigger>
            <TabsTrigger value="statistics"><PieChart className="h-4 w-4" />Statistics</TabsTrigger>
            <TabsTrigger value="import"><Upload className="h-4 w-4" />Import</TabsTrigger>
            <TabsTrigger value="blacklist"><Ban className="h-4 w-4" />Blacklist</TabsTrigger>
          </TabsList>
        )}

        <TabsContent value="dashboard" className="space-y-4">
          {stats && <DashboardContent stats={stats} showStats={showStats} />}
        </TabsContent>

        <TabsContent value="deals"><DealsTab showStats={dealsShowStats} /></TabsContent>
        <TabsContent value="clients"><ClientStatsTab /></TabsContent>
        <TabsContent value="statistics"><StatisticsTab showFilters={statsShowFilters} setShowFilters={setStatsShowFilters} showStats={statsShowCards} /></TabsContent>
        <TabsContent value="import"><ImportTab /></TabsContent>
        <TabsContent value="blacklist"><ClientStatsTab blacklistOnly /></TabsContent>
      </Tabs>
    </div>
  )
}

function DashboardContent({ stats, showStats }: { stats: CrmStats; showStats: boolean }) {
  return (
    <div className="space-y-4">
      <div className={`grid grid-cols-2 gap-3 ${showStats ? '' : 'hidden md:grid'}`}>
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
