import { PageHeader } from '@/components/shared/PageHeader'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { useTabParam } from '@/hooks/useTabParam'
import { CampaignsTab } from './CampaignsTab'
import { PulseTab } from './PulseTab'
import { PraiseTab } from './PraiseTab'
import { KpiTab } from './KpiTab'

type BoardTab = 'campaigns' | 'pulse' | 'praise' | 'kpi'

/**
 * Happy Board — the admin console for the Happy engagement module.
 * Gated at the route level on `can_access_settings` (see App.tsx).
 * The active tab is persisted in the URL (`?tab=`) so a refresh keeps your place.
 */
export default function HappyBoard() {
  const [tab, setTab] = useTabParam<BoardTab>('campaigns')

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader title="Happy Board" description="Consola de administrare Happy" />

      <Tabs value={tab} onValueChange={(v) => setTab(v as BoardTab)}>
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
