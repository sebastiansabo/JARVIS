import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import CategoryManager from '@/pages/Dms/CategoryManager'
import PartyRoleManager from '@/pages/Dms/PartyRoleManager'

export default function DocumentsTab() {
  return (
    <Tabs defaultValue="categories" className="space-y-4">
      <TabsList>
        <TabsTrigger value="categories">Categories</TabsTrigger>
        <TabsTrigger value="party-roles">Party Roles</TabsTrigger>
      </TabsList>
      <TabsContent value="categories">
        <CategoryManager />
      </TabsContent>
      <TabsContent value="party-roles">
        <PartyRoleManager />
      </TabsContent>
    </Tabs>
  )
}
