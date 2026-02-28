import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Users, Car, Upload, BarChart3, PieChart, UserCheck, Ban } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { crmApi, type CrmStats } from '@/api/crm'
import DealsTab from './DealsTab'
import StatisticsTab from './StatisticsTab'
import ClientStatsTab from './ClientStatsTab'
import ImportTab from './ImportTab'

function StatsCard({ title, value, sub, icon: Icon }: { title: string; value: number | string; sub?: string; icon: React.ElementType }) {
  return (
    <Card>
      <CardContent className="p-3 flex items-center gap-2.5">
        <div className="rounded-md bg-primary/10 p-1.5">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <div>
          <p className="text-lg font-bold leading-none">{typeof value === 'number' ? value.toLocaleString() : value}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{title}</p>
          {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

export default function Crm() {
  const [tab, setTab] = useState('dashboard')
  const { data: stats } = useQuery({ queryKey: ['crm-stats'], queryFn: crmApi.getStats })

  return (
    <div className="space-y-4">
      <PageHeader
        title="Samsaru"
        breadcrumbs={[
          { label: 'Samsaru' },
          { label: tab === 'dashboard' ? 'Dashboard' : tab === 'deals' ? 'Sales' : tab === 'clients' ? 'Clients' : tab === 'statistics' ? 'Statistics' : tab === 'import' ? 'Import' : 'Blacklist' },
        ]}
      />

      <Tabs value={tab} onValueChange={setTab}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
        <TabsList className="w-max md:w-auto">
          <TabsTrigger value="dashboard" className="gap-1.5"><BarChart3 className="h-4 w-4" />Dashboard</TabsTrigger>
          <TabsTrigger value="deals" className="gap-1.5"><Car className="h-4 w-4" />Sales</TabsTrigger>
          <TabsTrigger value="clients" className="gap-1.5"><UserCheck className="h-4 w-4" />Clients</TabsTrigger>
          <TabsTrigger value="statistics" className="gap-1.5"><PieChart className="h-4 w-4" />Statistics</TabsTrigger>
          <TabsTrigger value="import" className="gap-1.5"><Upload className="h-4 w-4" />Import</TabsTrigger>
          <TabsTrigger value="blacklist" className="gap-1.5"><Ban className="h-4 w-4" />Blacklist</TabsTrigger>
        </TabsList>
        </div>

        <TabsContent value="dashboard" className="space-y-4">
          {stats && <DashboardContent stats={stats} />}
        </TabsContent>

        <TabsContent value="deals"><DealsTab /></TabsContent>
        <TabsContent value="clients"><ClientStatsTab /></TabsContent>
        <TabsContent value="statistics"><StatisticsTab /></TabsContent>
        <TabsContent value="import"><ImportTab /></TabsContent>
        <TabsContent value="blacklist"><ClientStatsTab blacklistOnly /></TabsContent>
      </Tabs>
    </div>
  )
}

function DashboardContent({ stats }: { stats: CrmStats }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <StatsCard title="Total Clients" value={stats.clients.total} sub={`${stats.clients.persons} persons, ${stats.clients.companies} companies`} icon={Users} />
        <StatsCard title="Car Deals" value={stats.deals.total} sub={`${stats.deals.new_cars} NW, ${stats.deals.used_cars} GW`} icon={Car} />
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
