import { PageHeader } from '@/components/shared/PageHeader'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { CampaignsTab } from './CampaignsTab'
import { PulseTab } from './PulseTab'
import { PraiseTab } from './PraiseTab'
import { KpiTab } from './KpiTab'

/**
 * Happy Board — the admin console for the Happy engagement module.
 * Gated at the route level on `can_access_settings` (see App.tsx).
 */
export default function HappyBoard() {
  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader title="Happy Board" description="Consola de administrare Happy" />

      <Tabs defaultValue="campaigns">
        <TabsList>
          <TabsTrigger value="campaigns">Campanii</TabsTrigger>
          <TabsTrigger value="pulse">Pulse</TabsTrigger>
          <TabsTrigger value="praise">Aprecieri</TabsTrigger>
          <TabsTrigger value="kpi">KPI</TabsTrigger>
        </TabsList>

        <TabsContent value="campaigns" className="mt-4">
          <CampaignsTab />
        </TabsContent>
        <TabsContent value="pulse" className="mt-4">
          <PulseTab />
        </TabsContent>
        <TabsContent value="praise" className="mt-4">
          <PraiseTab />
        </TabsContent>
        <TabsContent value="kpi" className="mt-4">
          <KpiTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
