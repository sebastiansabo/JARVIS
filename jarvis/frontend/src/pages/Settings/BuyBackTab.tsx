import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { buybackApi } from '@/api/buyback'
import type { BuybackConfig } from '@/types/buyback'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const TOGGLES: { key: keyof BuybackConfig; label: string }[] = [
  { key: 'enabled', label: 'Notificări active (master)' },
  { key: 'channel_email', label: 'Canal: Email' },
  { key: 'channel_in_app', label: 'Canal: În aplicație' },
  { key: 'channel_push', label: 'Canal: Push (mobil)' },
  { key: 'notify_new_request', label: 'Eveniment: Solicitare nouă → Achiziții' },
  { key: 'notify_milestones', label: 'Eveniment: Etape (ofertă, decizie, finalizare) → Creator' },
  { key: 'notify_inspection', label: 'Eveniment: Inspecție → Creator' },
]

export default function BuyBackTab() {
  const queryClient = useQueryClient()
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [form, setForm] = useState<BuybackConfig | null>(null)

  const { data: companiesData } = useQuery({
    queryKey: ['buyback-companies'],
    queryFn: () => buybackApi.getCompanies(),
    staleTime: 60_000,
  })
  const companies = companiesData?.companies ?? []
  useEffect(() => {
    if (companyId == null && companies.length) setCompanyId(companies[0].id)
  }, [companies, companyId])

  const { data: cfgData } = useQuery({
    queryKey: ['buyback-config', companyId],
    queryFn: () => buybackApi.getConfig(companyId as number),
    enabled: companyId != null,
  })
  useEffect(() => { if (cfgData?.config) setForm(cfgData.config) }, [cfgData])

  const save = useMutation({
    mutationFn: () => buybackApi.updateConfig(form as BuybackConfig),
    onSuccess: (res) => {
      if (res.config) setForm(res.config)
      queryClient.invalidateQueries({ queryKey: ['buyback-config', companyId] })
      toast.success('Setări salvate')
    },
    onError: (e) => toast.error((e as { data?: { error?: string } })?.data?.error || 'Salvarea a eșuat'),
  })

  const set = <K extends keyof BuybackConfig>(k: K, v: BuybackConfig[K]) =>
    setForm((f) => (f ? { ...f, [k]: v } : f))

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">BuyBack — Notificări</h2>
        <Select value={companyId != null ? String(companyId) : ''} onValueChange={(v) => setCompanyId(Number(v))}>
          <SelectTrigger className="h-9 w-[220px]"><SelectValue placeholder="Companie" /></SelectTrigger>
          <SelectContent>
            {companies.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {form && (
        <Card>
          <CardHeader><CardTitle className="text-base">Configurare per companie</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Email(uri) Achiziții (separate prin virgulă)</Label>
              <Input
                value={form.acquisition_emails}
                onChange={(e) => set('acquisition_emails', e.target.value)}
                placeholder="achizitii@autoworld.ro"
              />
            </div>
            {TOGGLES.map((t) => (
              <div key={t.key} className="flex items-center justify-between rounded-md border p-2.5">
                <Label className="text-sm">{t.label}</Label>
                <Switch
                  checked={!!form[t.key]}
                  onCheckedChange={(v) => set(t.key, v as BuybackConfig[typeof t.key])}
                />
              </div>
            ))}
            <Button disabled={save.isPending} onClick={() => save.mutate()}>Salvează</Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
