import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { settingsApi } from '@/api/settings'
import { toast } from 'sonner'
import CategoryManager from '@/pages/Dms/CategoryManager'
import PartyRoleManager from '@/pages/Dms/PartyRoleManager'
import type { DropdownOption } from '@/types/settings'

const DMS_SETTINGS: { value: string; label: string; description: string; defaultActive: boolean }[] = [
  {
    value: 'require_parent_for_child',
    label: 'Require parent for child documents',
    description: 'When enabled, uploading a child document requires selecting a parent document first.',
    defaultActive: true,
  },
]

export default function DocumentsTab() {
  return (
    <Tabs defaultValue="general" className="space-y-4">
      <TabsList>
        <TabsTrigger value="general">General</TabsTrigger>
        <TabsTrigger value="categories">Categories</TabsTrigger>
        <TabsTrigger value="party-roles">Party Roles</TabsTrigger>
      </TabsList>
      <TabsContent value="general">
        <DmsConfigSection />
      </TabsContent>
      <TabsContent value="categories">
        <CategoryManager />
      </TabsContent>
      <TabsContent value="party-roles">
        <PartyRoleManager />
      </TabsContent>
    </Tabs>
  )
}

function DmsConfigSection() {
  const queryClient = useQueryClient()

  const { data: options = [], isLoading } = useQuery({
    queryKey: ['settings', 'dropdown-options', 'dms_config'],
    queryFn: () => settingsApi.getDropdownOptions('dms_config'),
    staleTime: 5 * 60_000,
  })

  const createMut = useMutation({
    mutationFn: (data: Partial<DropdownOption>) => settingsApi.addDropdownOption(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings', 'dropdown-options', 'dms_config'] }),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DropdownOption> }) =>
      settingsApi.updateDropdownOption(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'dropdown-options', 'dms_config'] })
      toast.success('Setting updated')
    },
    onError: () => toast.error('Failed to update setting'),
  })

  const handleToggle = (setting: typeof DMS_SETTINGS[number], currentValue: boolean) => {
    const existing = options.find((o) => o.value === setting.value)
    if (existing) {
      updateMut.mutate({ id: existing.id, data: { is_active: !currentValue } })
    } else {
      // Create the setting row on first toggle
      createMut.mutate({
        dropdown_type: 'dms_config',
        value: setting.value,
        label: setting.label,
        is_active: !setting.defaultActive,
        sort_order: 0,
      })
    }
  }

  if (isLoading) return <p className="text-sm text-muted-foreground p-4">Loading...</p>

  return (
    <Card>
      <CardHeader>
        <CardTitle>Document Settings</CardTitle>
        <CardDescription>Configure DMS behavior and validation rules.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {DMS_SETTINGS.map((setting) => {
          const existing = options.find((o) => o.value === setting.value)
          const isActive = existing ? existing.is_active : setting.defaultActive

          return (
            <div key={setting.value} className="flex items-center justify-between gap-4 rounded-lg border p-4">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">{setting.label}</Label>
                <p className="text-xs text-muted-foreground">{setting.description}</p>
              </div>
              <Switch
                checked={isActive}
                onCheckedChange={() => handleToggle(setting, isActive)}
                disabled={createMut.isPending || updateMut.isPending}
              />
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
