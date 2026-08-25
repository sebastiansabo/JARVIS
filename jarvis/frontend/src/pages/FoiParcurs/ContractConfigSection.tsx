import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileText } from 'lucide-react'
import { toast } from 'sonner'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { foiParcursApi } from '@/api/foiParcurs'

// Tokens the Service contract generator substitutes at render time (see
// docs/superpowers/specs/2026-08-24-foi-parcurs-service-courtesy-cars-design.md).
// Every placeholder the backend renderer substitutes. SOURCE OF TRUTH is
// jarvis/foi_parcurs/services/contract_template.py PLACEHOLDERS — keep this in
// sync when tokens are added there. Grouped purely for readability.
const PLACEHOLDER_GROUPS: { label: string; tokens: string[] }[] = [
  { label: 'Client', tokens: [
    '{client_name}', '{client_phone}', '{client_address}', '{client_company}',
    '{client_cui}', '{client_ci_serie}', '{client_email}',
  ] },
  { label: 'Vehicul & rută', tokens: [
    '{brand}', '{vehicle_model}', '{vin}', '{registration_number}',
    '{km_start}', '{km_end}', '{distance_km}',
    '{departure_datetime}', '{return_datetime}', '{service_order_ref}', '{advisor_name}',
  ] },
  { label: 'Companie (date legale)', tokens: [
    '{company_name}', '{company_reg_no}', '{company_vat}', '{company_iban}',
    '{company_bank}', '{company_street}', '{company_city}', '{company_county}',
    '{company_email}', '{company_administrator}', '{dealer_phone}',
  ] },
  { label: 'Preț închiriere (curtoazie)', tokens: [
    '{svc_rate_basis}', '{svc_tariff_eur}', '{svc_units}', '{svc_total_eur}',
    '{svc_garantie_eur}', '{svc_fransiza_eur}', '{svc_limita_km_zi}', '{svc_extra_km_eur}',
  ] },
  { label: 'General', tokens: ['{general_conditions}'] },
]

type ContractConfigItem = Awaited<ReturnType<typeof foiParcursApi.getContractConfigs>>['configs'][number]
type ContractDraft = { title: string; body_template: string; general_conditions: string; is_active: boolean }

/** Per-company+brand Service contract template setup — the source of the
 *  "Mașini de curtoazie" (courtesy car) contract generated for Service
 *  sessions. Configuring an active template here is what unlocks the Service
 *  context for that (company, brand) — mirrors DealerConfigSection but owns
 *  its own company selector since SettingsTab has none. */
export default function ContractConfigSection() {
  const qc = useQueryClient()
  const [selectedCompany, setSelectedCompany] = useState<string>('')
  const companyId = selectedCompany ? Number(selectedCompany) : null

  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
    staleTime: 60_000,
  })
  const companies = companiesData?.companies ?? []

  const { data, isLoading } = useQuery({
    queryKey: ['fp-contract-configs', companyId],
    queryFn: () => foiParcursApi.getContractConfigs(companyId!),
    enabled: !!companyId,
    staleTime: 30_000,
  })
  const configs = data?.configs ?? []

  const saveMut = useMutation({
    mutationFn: ({ brandId, values }: { brandId: number; values: ContractDraft }) =>
      foiParcursApi.putContractConfig(companyId!, brandId, values),
    onSuccess: () => {
      toast.success('Salvat')
      qc.invalidateQueries({ queryKey: ['fp-contract-configs', companyId] })
    },
    onError: (err: any) => {
      toast.error(err?.status === 403 ? 'Nu ai permisiuni de administrator pentru a salva.' : 'Salvarea a eșuat')
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FileText className="h-5 w-5 text-muted-foreground" />
        <h3 className="text-lg font-semibold">Contract Mașini de curtoazie</h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Șablon de contract per brand pentru sesiunile Service (mașini de curtoazie). Un brand cu template activ
        deblochează contextul Service pentru compania selectată.
      </p>

      <div className="max-w-sm space-y-1.5">
        <Label>Company</Label>
        <Select value={selectedCompany} onValueChange={setSelectedCompany}>
          <SelectTrigger>
            <SelectValue placeholder="Selectează o companie..." />
          </SelectTrigger>
          <SelectContent>
            {companies.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card className="p-3 bg-muted/30">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Token-uri disponibile
        </p>
        <div className="space-y-2.5">
          {PLACEHOLDER_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="mb-1 text-[11px] font-medium text-muted-foreground">{group.label}</p>
              <div className="flex flex-wrap gap-1.5">
                {group.tokens.map((p) => (
                  <code key={p} className="rounded border bg-background px-1.5 py-0.5 text-xs">{p}</code>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {!companyId ? null : isLoading ? (
        <p className="py-4 text-sm text-muted-foreground">Se încarcă…</p>
      ) : !configs.length ? (
        <p className="py-4 text-sm text-muted-foreground">Niciun brand găsit pentru această companie.</p>
      ) : (
        <div className="space-y-4">
          {configs.map((c) => (
            <ContractBrandRow
              key={c.brand_id}
              config={c}
              isSaving={saveMut.isPending}
              onSave={(values) => saveMut.mutate({ brandId: c.brand_id, values })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ContractBrandRow({ config, onSave, isSaving }: {
  config: ContractConfigItem
  onSave: (values: ContractDraft) => void
  isSaving: boolean
}) {
  const [draft, setDraft] = useState<ContractDraft>({
    title: config.title ?? '',
    body_template: config.body_template ?? '',
    general_conditions: config.general_conditions ?? '',
    is_active: config.is_active,
  })

  // Re-sync when the underlying query data changes (e.g. after a successful
  // save invalidates + refetches).
  useEffect(() => {
    setDraft({
      title: config.title ?? '',
      body_template: config.body_template ?? '',
      general_conditions: config.general_conditions ?? '',
      is_active: config.is_active,
    })
  }, [config])

  const set = <K extends keyof ContractDraft>(k: K, v: ContractDraft[K]) => setDraft((p) => ({ ...p, [k]: v }))

  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">{config.brand_name}</div>
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground">Activ</Label>
          <Switch checked={draft.is_active} onCheckedChange={(v) => set('is_active', v)} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Titlu contract</Label>
        <Input
          value={draft.title}
          onChange={(e) => set('title', e.target.value)}
          placeholder="Ex: Contract de comodat - mașină de curtoazie"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Conținut contract</Label>
        <Textarea
          className="min-h-[160px] font-mono text-xs"
          value={draft.body_template}
          onChange={(e) => set('body_template', e.target.value)}
          placeholder="Textul contractului, folosind token-urile de mai sus..."
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Condiții generale</Label>
        <Textarea
          className="min-h-[120px] font-mono text-xs"
          value={draft.general_conditions}
          onChange={(e) => set('general_conditions', e.target.value)}
          placeholder="Condiții generale ale contractului..."
        />
      </div>

      <Button size="sm" onClick={() => onSave(draft)} disabled={isSaving}>
        {isSaving ? 'Se salvează...' : `Salvează ${config.brand_name}`}
      </Button>
    </Card>
  )
}
